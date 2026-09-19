"""Load the existing benchmark dataset into PostgreSQL.

This is an import, not a generator. It reads `data/out/records.csv` — the same
46,567 rows the prototype has always used — and nothing in here invents a
material, a CPSE, a plant, a quantity or a legacy code. If the CSV is absent the
importer fails rather than fabricating a substitute, because a seeded database
that quietly differs from the evaluated dataset is how measured numbers stop
meaning anything.

Idempotent: re-running upserts on the natural keys rather than duplicating.

    python -m app.seed.import_dataset --split all
    python -m app.seed.import_dataset --split test --truncate
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal, engine
from ..matching import category_of, extract, normalize
from ..matching.attributes import HARD_KEYS
from ..models import (
    Cpse, MaterialAttribute, MaterialRecord, Plant,
)

RECORDS_CSV = settings.DATA_DIR / "out" / "records.csv"

# Plant kind is inferable from the name the generator already produced; this is
# a label for the UI, never used in matching.
def _plant_kind(name: str) -> str:
    n = (name or "").lower()
    for key, kind in (("refinery", "refinery"), ("terminal", "terminal"),
                      ("depot", "depot"), ("petrochemical", "petrochemical"),
                      ("plant", "plant"), ("station", "pipeline_station")):
        if key in n:
            return kind
    return "site"


CPSE_NAMES = {
    "IOCL": "Indian Oil Corporation Limited",
    "BPCL": "Bharat Petroleum Corporation Limited",
    "HPCL": "Hindustan Petroleum Corporation Limited",
    "ONGC": "Oil and Natural Gas Corporation",
    "GAIL": "GAIL (India) Limited",
    "CPCL": "Chennai Petroleum Corporation Limited",
}


def _sap_plant_code(name: str, seen: dict[str, str]) -> str:
    """Four characters, SAP WERKS width, stable and collision-free."""
    if name in seen:
        return seen[name]
    base = "".join(w[0] for w in str(name).split()[:2]).upper() or "PL"
    code, n = (base + "00")[:4], 1
    while code in seen.values():
        code = f"{base[:2]}{n:02d}"
        n += 1
    seen[name] = code
    return code


def load_org(db: Session, df: pd.DataFrame) -> tuple[dict, dict]:
    cpse_ids: dict[str, int] = {}
    for code in sorted(df.cpse.dropna().unique()):
        row = db.execute(select(Cpse).where(Cpse.code == code)).scalar_one_or_none()
        if row is None:
            row = Cpse(code=code, name=CPSE_NAMES.get(code, code),
                       sector="Petroleum & Natural Gas")
            db.add(row)
            db.flush()
        cpse_ids[code] = row.id

    plant_ids: dict[tuple[str, str], int] = {}
    seen_codes: dict[str, str] = {}
    pairs = df[["cpse", "plant"]].dropna().drop_duplicates().itertuples(index=False)
    for cpse_code, plant_name in sorted(pairs):
        key = (cpse_code, plant_name)
        row = db.execute(
            select(Plant).where(Plant.cpse_id == cpse_ids[cpse_code],
                                Plant.name == plant_name)
        ).scalar_one_or_none()
        if row is None:
            row = Plant(cpse_id=cpse_ids[cpse_code], name=plant_name,
                        sap_plant_code=_sap_plant_code(plant_name, seen_codes),
                        kind=_plant_kind(plant_name))
            db.add(row)
            db.flush()
        plant_ids[key] = row.id
    db.commit()
    return cpse_ids, plant_ids


def load_records(db: Session, df: pd.DataFrame, cpse_ids: dict, plant_ids: dict,
                 batch: int = 2000) -> int:
    """Normalise, extract attributes, and upsert. Attributes become rows."""
    total = 0
    t0 = time.time()
    for start in range(0, len(df), batch):
        chunk = df.iloc[start:start + batch]
        rec_rows, attr_rows = [], []
        for r in chunk.itertuples(index=False):
            norm = normalize(r.description)
            attrs = extract(norm)
            rec_rows.append(dict(
                source_record_id=int(r.record_id),
                cpse_id=cpse_ids[r.cpse],
                plant_id=plant_ids.get((r.cpse, r.plant)),
                legacy_code=str(r.legacy_code),
                description=str(r.description),
                normalised_description=norm,
                uom=(str(r.uom) if pd.notna(r.uom) else None),
                category=category_of(norm) or None,
                qty=(float(r.qty) if pd.notna(r.qty) else None),
                unit_value=(float(r.unit_value) if pd.notna(r.unit_value) else None),
                split=(str(r.split) if pd.notna(r.split) else None),
                cluster_id=(int(r.cluster_id) if pd.notna(r.cluster_id) else None),
                family_id=(int(r.family_id) if pd.notna(r.family_id) else None),
                recipe=(str(r.recipe) if pd.notna(r.recipe) else None),
                attrs_payload=attrs,
            ))
            attr_rows.append((int(r.record_id), attrs))

        stmt = insert(MaterialRecord).values(rec_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[MaterialRecord.source_record_id],
            set_={c: stmt.excluded[c] for c in (
                "description", "normalised_description", "category", "qty",
                "unit_value", "split", "attrs_payload", "plant_id")},
        )
        db.execute(stmt)
        db.flush()

        # map source ids -> db ids for the attribute rows
        src_ids = [s for s, _ in attr_rows]
        id_map = dict(db.execute(
            select(MaterialRecord.source_record_id, MaterialRecord.id)
            .where(MaterialRecord.source_record_id.in_(src_ids))
        ).all())

        payload = []
        for src, attrs in attr_rows:
            rid = id_map.get(src)
            if rid is None:
                continue
            for k, v in attrs.items():
                payload.append(dict(record_id=rid, key=k, value=str(v),
                                    is_hard_key=k in HARD_KEYS,
                                    source="RULE", confidence=None,
                                    provenance="MEASURED"))
        if payload:
            astmt = insert(MaterialAttribute).values(payload)
            astmt = astmt.on_conflict_do_update(
                index_elements=[MaterialAttribute.record_id, MaterialAttribute.key],
                set_={"value": astmt.excluded.value,
                      "is_hard_key": astmt.excluded.is_hard_key,
                      "source": astmt.excluded.source},
            )
            db.execute(astmt)

        db.commit()
        total += len(chunk)
        print(f"  {total:>6,}/{len(df):,} records "
              f"({time.time() - t0:.0f}s)", end="\r", flush=True)
    print()
    return total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Import the benchmark dataset into PostgreSQL")
    ap.add_argument("--split", default="all",
                    help="dev | val | test | all (default all)")
    ap.add_argument("--limit", type=int, default=0, help="import at most N rows")
    ap.add_argument("--truncate", action="store_true",
                    help="clear material tables before importing")
    a = ap.parse_args(argv)

    if not RECORDS_CSV.exists():
        print(f"ERROR: {RECORDS_CSV} not found.\n"
              f"This importer will not invent a dataset. Run `make data` to "
              f"regenerate the benchmark, or restore the file.", file=sys.stderr)
        return 2

    df = pd.read_csv(RECORDS_CSV)
    if a.split != "all":
        df = df[df.split == a.split]
    if a.limit:
        df = df.head(a.limit)
    if df.empty:
        print("nothing to import", file=sys.stderr)
        return 2

    print(f"importing {len(df):,} records from {RECORDS_CSV.name} "
          f"(split={a.split})")

    with SessionLocal() as db:
        if a.truncate:
            db.execute(text(
                "TRUNCATE material_attributes, identity_members, material_identities, "
                "match_evidence, material_matches, material_records "
                "RESTART IDENTITY CASCADE"))
            db.commit()
            print("  truncated material tables")

        cpse_ids, plant_ids = load_org(db, df)
        print(f"  {len(cpse_ids)} CPSEs, {len(plant_ids)} plants")
        n = load_records(db, df, cpse_ids, plant_ids)

        counts = db.execute(text(
            "SELECT (SELECT count(*) FROM material_records), "
            "(SELECT count(*) FROM material_attributes), "
            "(SELECT count(*) FROM material_attributes WHERE is_hard_key)"
        )).one()
    print(f"done: {n:,} imported | {counts[0]:,} records, {counts[1]:,} attributes "
          f"({counts[2]:,} hard keys) in the database")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
