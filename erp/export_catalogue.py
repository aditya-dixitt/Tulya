"""The deliverable: the national catalogue, as files a CPSE can actually use.

Everything else in this repo is machinery. This is the thing a materials
manager is handed at the end of the exercise, and it is deliberately three
files rather than one, because three different people need three different
cuts of it:

    national_catalogue.csv   one row per national code - the standard itself,
                             with its class, its defining specification and how
                             many legacy codes across how many CPSEs collapsed
                             into it. For the materials head and for GeM.
    legacy_mapping.csv       one row per *legacy* code - the lookup a purchase
                             officer runs, and the file that loads into the
                             ERP. Carries the confirmation level, so a
                             provisional mapping cannot be mistaken for a
                             settled one.
    open_items.csv           what is NOT done: groups refused a code, and rows
                             mapped provisionally. Shipping the exceptions in
                             the same envelope as the results is the difference
                             between a report and a hand-over.
"""
import argparse
import csv
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from engine import registry

OUT = ROOT / "data/out"


def _write(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path


def export(conn, out_dir):
    out_dir = pathlib.Path(out_dir)
    cat = registry.catalogue(conn)

    catalogue_rows, mapping_rows = [], []
    for c in cat:
        confirmed = sum(1 for m in c["members"] if m["link_status"] == "CONFIRMED")
        catalogue_rows.append(dict(
            national_code=c["nmc"], class_code=c["class_code"],
            segment=c["segment_name"], family=c["family_name"], item_class=c["class_name"],
            description=c["description"], uom=c["uom"],
            defining_specification=c["signature"],
            legacy_codes=len(c["members"]), confirmed_links=confirmed,
            provisional_links=len(c["members"]) - confirmed,
            cpses=";".join(c["cpses"]), plants=";".join(c["plants"]),
            unspsc=c["unspsc"] or "", status=c["status"],
            superseded_by=c["superseded_by"] or ""))
        for m in c["members"]:
            mapping_rows.append(dict(
                cpse=m["cpse"], plant=m["plant"], legacy_code=m["legacy_code"],
                national_code=c["nmc"], item_class=c["class_name"],
                confirmation="CONFIRMED" if m["link_status"] == "CONFIRMED" else "PROVISIONAL",
                unconfirmed_specs=";".join(m["unknown_keys"]),
                defining_specification=c["signature"], description=c["description"]))

    open_rows = [dict(kind="refused", detail=r["reason"], note=r["detail"],
                      reference=r["group_key"])
                 for r in registry.refusals(conn, 100_000)]
    open_rows += [dict(kind="provisional", detail=f"{q['cpse']} {q['legacy_code']}",
                       note="could not confirm: " + ";".join(q["unknown_keys"]),
                       reference=q["nmc"])
                  for q in registry.provisional_queue(conn, 100_000)]

    paths = [
        _write(out_dir / "national_catalogue.csv", list(catalogue_rows[0]) if catalogue_rows
               else ["national_code"], catalogue_rows),
        _write(out_dir / "legacy_mapping.csv", list(mapping_rows[0]) if mapping_rows
               else ["legacy_code"], mapping_rows),
        _write(out_dir / "open_items.csv", ["kind", "detail", "note", "reference"], open_rows),
    ]
    summary = dict(national_codes=len(catalogue_rows), legacy_codes=len(mapping_rows),
                   open_items=len(open_rows),
                   confirmed=sum(r["confirmed_links"] for r in catalogue_rows),
                   provisional=sum(r["provisional_links"] for r in catalogue_rows),
                   files=[str(p) for p in paths], **registry.stats(conn))
    (out_dir / "catalogue_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default=str(OUT / "registry.db"))
    ap.add_argument("--out", default=str(ROOT / "reports" / "catalogue"))
    a = ap.parse_args()
    if not pathlib.Path(a.registry).exists():
        print(f"no registry at {a.registry}. Run `make erp-demo` or approve some pairs "
              f"in the console first.")
        return 1
    conn = registry.init_registry(sqlite3.connect(a.registry))
    s = export(conn, a.out)
    print(f"\nNational catalogue exported to {a.out}")
    print(f"  {s['national_codes']:,} national codes")
    print(f"  {s['legacy_codes']:,} legacy codes mapped "
          f"({s['confirmed']:,} confirmed, {s['provisional']:,} provisional)")
    print(f"  {s['open_items']:,} open items shipped alongside, not hidden")
    for f in s["files"]:
        print(f"    {pathlib.Path(f).name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
