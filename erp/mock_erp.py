"""A stand-in SAP client: exports an extract, and consumes a write-back.

There is no SAP system in this build and there will not be one before the
finale, so the honest way to prove the connector is to write the other end of
it too - and to make that other end strict rather than accommodating. This
mock enforces what a real system enforces: MATNR and MAKTX length limits,
MANDT on every row, a Z_NMC_MAP that rejects a national code failing its own
check digit, and a refusal to accept a row whose material does not exist.

The truncation is the part to watch. Descriptions are cut at 40 characters on
export because that is what MAKT does, so the extract the engine reads back is
degraded in exactly the way a real one is - the benchmark's own corruption
recipes and this limit are two different mechanisms producing the same class
of damage, and the engine is not told which is which.
"""
import pathlib

import pandas as pd

from erp import sap
from engine import codegen


def export_extract(records_df, out_dir, cpse=None, truncate=True):
    """Benchmark records -> MARA / MAKT / MARC / MARD, one folder per CPSE."""
    out_dir = pathlib.Path(out_dir)
    df = records_df if cpse is None else records_df[records_df.cpse == cpse]
    plants = {}
    mara, makt, marc, mard = [], [], [], []
    for r in df.itertuples():
        matnr = str(r.legacy_code)[:sap.MATNR_LIMIT]
        werks = sap.plant_code(getattr(r, "plant", "") or "", plants)
        desc = str(r.description)
        mara.append(dict(MANDT=sap.CLIENT, MATNR=matnr, MTART="ERSA",
                         MATKL=str(getattr(r, "category_true", ""))[:9].upper(),
                         MEINS=str(r.uom).upper()[:3], ERSDA="20180401", ERNAM="LEGACY",
                         ZZ_CPSE=r.cpse))
        makt.append(dict(MANDT=sap.CLIENT, MATNR=matnr, SPRAS="EN",
                         MAKTX=sap.truncate_maktx(desc) if truncate else desc))
        marc.append(dict(MANDT=sap.CLIENT, MATNR=matnr, WERKS=werks,
                         ZZ_PLANT_NAME=getattr(r, "plant", "")))
        mard.append(dict(MANDT=sap.CLIENT, MATNR=matnr, WERKS=werks,
                         LABST=getattr(r, "qty", 0), STPRS=getattr(r, "unit_value", 0)))

    sap.write_table(out_dir / "MARA.csv", sap.MARA_FIELDS + ["ZZ_CPSE"], mara)
    sap.write_table(out_dir / "MAKT.csv", sap.MAKT_FIELDS, makt)
    sap.write_table(out_dir / "MARC.csv", sap.MARC_FIELDS + ["ZZ_PLANT_NAME"], marc)
    sap.write_table(out_dir / "MARD.csv", sap.MARD_FIELDS, mard)

    full = [str(x) for x in df.description]
    return dict(folder=str(out_dir), materials=len(mara), plants=len(plants),
                truncated=truncate,
                maktx_before=sap.maktx_pressure(full),
                maktx_after=sap.maktx_pressure([m["MAKTX"] for m in makt]))


def apply_batch(extract_dir, batch_payload):
    """Consume a Z_NMC_MAP load the way a real system would: validate first.

    Returns (applied_rows, rejects). Rejects are *not* an edge case to smooth
    over - if this ever rejects a row in the demo, the write-back is wrong and
    we want to see it, not have it quietly absorbed.
    """
    extract_dir = pathlib.Path(extract_dir)
    known = {(r["MATNR"], r["WERKS"]) for r in sap.read_table(extract_dir / "MARC.csv")}
    rows = sap.read_table(batch_payload) if not isinstance(batch_payload, list) else batch_payload

    applied, rejects = [], []
    for r in rows:
        key = (r.get("MATNR", ""), r.get("WERKS", ""))
        if r.get("MANDT") != sap.CLIENT:
            rejects.append(dict(**r, _reason="wrong client (MANDT)"))
        elif key not in known:
            rejects.append(dict(**r, _reason="material/plant not in material master"))
        elif not codegen.is_valid_code(r.get("ZZNMC", "")):
            rejects.append(dict(**r, _reason="national code fails its check digit"))
        elif len(r.get("MATNR", "")) > sap.MATNR_LIMIT:
            rejects.append(dict(**r, _reason="MATNR too long"))
        else:
            applied.append(r)
    return applied, rejects


def material_master_after(extract_dir, applied_rows):
    """What a buyer now sees: their own code, and the national code beside it.

    The point of the table is that the left-hand column is unchanged. Nothing
    was renumbered; a column was added.
    """
    extract_dir = pathlib.Path(extract_dir)
    makt = {r["MATNR"]: r["MAKTX"] for r in sap.read_table(extract_dir / "MAKT.csv")}
    by_key = {(r["MATNR"], r["WERKS"]): r for r in applied_rows}
    out = []
    for r in sap.read_table(extract_dir / "MARC.csv"):
        key = (r["MATNR"], r["WERKS"])
        z = by_key.get(key)
        out.append(dict(MATNR=r["MATNR"], WERKS=r["WERKS"],
                        PLANT=r.get("ZZ_PLANT_NAME", ""),
                        MAKTX=makt.get(r["MATNR"], ""),
                        ZZNMC=(z or {}).get("ZZNMC", ""),
                        ZZNMC_STATUS=(z or {}).get("ZZNMC_STATUS", ""),
                        ZZNMC_CONF=(z or {}).get("ZZNMC_CONF", "")))
    return pd.DataFrame(out)
