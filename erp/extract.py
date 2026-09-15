"""Read a SAP MM extract into the frame the engine already understands.

The engine's contract is a table of
    record_id, cpse, plant, legacy_code, description, uom, qty, unit_value
and nothing in engine/ knows where those came from. This module is the only
place that knows about MARA, MAKT and MARC, which is what makes the same
pipeline usable against a different ERP by writing a sibling of this file.

Two behaviours here exist because real extracts are not clean:

**A material with three plant rows is three records, not one.** MARC is
per-plant, and the same MATNR can carry a different description per plant
once someone has maintained it locally. Collapsing them at import would hide
exactly the intra-CPSE duplication the Phase-1 rollout is meant to find.

**Rows that cannot be used are rejected loudly, into a file.** A silent drop
during import is indistinguishable from a matching failure later, and the
team will spend a day looking in the wrong place for it.
"""
import pathlib

import pandas as pd

from erp import sap


def load_extract(folder, cpse=None):
    """folder containing MARA.csv / MAKT.csv / MARC.csv (MARD.csv optional).

    Returns (records_df, report). `records_df` carries `matnr` and `werks`
    alongside the engine columns so write-back can find its way home.
    """
    folder = pathlib.Path(folder)
    mara = {r["MATNR"]: r for r in sap.read_table(folder / "MARA.csv")}
    marc = sap.read_table(folder / "MARC.csv")
    mard = {}
    if (folder / "MARD.csv").exists():
        for r in sap.read_table(folder / "MARD.csv"):
            mard[(r["MATNR"], r["WERKS"])] = r

    # MAKT is keyed by material AND language; prefer EN, fall back to whatever exists.
    makt = {}
    for r in sap.read_table(folder / "MAKT.csv"):
        key = r["MATNR"]
        if key not in makt or r.get("SPRAS") == "EN":
            makt[key] = r

    rows, rejects = [], []
    for m in marc:
        matnr, werks = m.get("MATNR", ""), m.get("WERKS", "")
        general = mara.get(matnr)
        text = makt.get(matnr)
        if not general:
            rejects.append(dict(matnr=matnr, werks=werks, reason="no MARA row"))
            continue
        if not text or not str(text.get("MAKTX", "")).strip():
            rejects.append(dict(matnr=matnr, werks=werks, reason="no MAKTX description"))
            continue
        stock = mard.get((matnr, werks), {})
        rows.append(dict(
            cpse=cpse or general.get("ZZ_CPSE", "") or folder.name,
            plant=m.get("ZZ_PLANT_NAME", "") or werks,
            legacy_code=matnr,
            description=str(text["MAKTX"]).strip(),
            uom=str(general.get("MEINS", "")).strip().lower(),
            qty=_num(stock.get("LABST", 0)),
            unit_value=_num(stock.get("STPRS", 0)),
            matnr=matnr,
            werks=werks,
            matkl=general.get("MATKL", ""),
            mtart=general.get("MTART", ""),
        ))

    df = pd.DataFrame(rows)
    if not df.empty:
        df.insert(0, "record_id", range(len(df)))
    report = dict(
        source=str(folder),
        marc_rows=len(marc), materials=len(mara), descriptions=len(makt),
        records=len(df), rejected=len(rejects),
        reject_reasons=pd.Series([r["reason"] for r in rejects]).value_counts().to_dict()
        if rejects else {},
        maktx=sap.maktx_pressure(df.description.tolist() if not df.empty else []),
    )
    return df, report, rejects


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def write_rejects(rejects, path):
    if not rejects:
        return None
    return sap.write_table(path, ["matnr", "werks", "reason"], rejects)
