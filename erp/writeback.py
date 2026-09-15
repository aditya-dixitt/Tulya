"""Write approved national codes back into the ERP - the half that makes this
a system rather than a report.

A deduplication exercise that ends in a spreadsheet changes nothing. The code
has to arrive in the system where material is actually requisitioned, and it
has to arrive in a form the CPSE's SAP basis team will accept:

  * into `Z_NMC_MAP`, a customer-namespace table, keyed MATNR + WERKS
  * MATNR itself untouched - every open PO, GRN and reservation stays valid
  * one file per batch, with a manifest carrying counts, a SHA-256 of the
    payload, the engine revision and the threshold that produced it
  * **idempotent**: re-running a load emits an identical payload, and a delta
    load emits only what changed since the last batch

The manifest matters more than it looks. A CPSE's change board will ask "what
exactly did this write, on what evidence, and can we reverse it". The manifest
answers all three from one file, and `revoke_batch` exists so the third answer
is yes.
"""
import datetime as dt
import json
import pathlib
import time

from erp import sap
from engine import registry

STATUS_ACTIVE = "A"
STATUS_SUPERSEDED = "S"


def _batch_id(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    return "NMC" + now.strftime("%Y%m%d%H%M%S")


def build_payload(conn, records_df, approver="samanvay", only_records=None):
    """One Z_NMC_MAP row per (material, plant) that now carries a national code.

    Rows are emitted in a stable order (MATNR, WERKS) so two runs over the same
    registry state are byte-identical and their checksums match - which is what
    makes 'has anything actually changed' answerable without a diff tool.
    """
    idx = records_df.set_index("record_id") if "record_id" in records_df.columns else records_df
    valid_from = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    link = {r[0]: (r[1], r[2]) for r in conn.execute(
        "SELECT record_id, link_status, unknown_keys FROM nmc_members")}
    rows = []
    for rid in idx.index:
        if only_records is not None and int(rid) not in only_records:
            continue
        nmc = registry.code_for_record(conn, int(rid))
        if not nmc:
            continue
        live, hops = registry.resolve(conn, nmc)
        entry = registry.get(conn, live or nmc)
        r = idx.loc[rid]
        status, unknown = link.get(int(rid), ("CONFIRMED", ""))
        rows.append({
            "MANDT": sap.CLIENT,
            "MATNR": str(r.get("matnr", r.get("legacy_code", ""))),
            "WERKS": str(r.get("werks", "")),
            "ZZNMC": live or nmc,
            "ZZNMC_CLASS": (entry or {}).get("class_code", ""),
            "ZZNMC_STATUS": STATUS_SUPERSEDED if hops else STATUS_ACTIVE,
            "ZZNMC_CONF": "P" if status == "PROVISIONAL" else "C",
            "ZZ_UNCONFIRMED": unknown or "",
            "ZZ_VALID_FROM": valid_from,
            "ZZ_SOURCE": "SAMANVAY",
            "ZZ_APPROVER": approver,
        })
    rows.sort(key=lambda r: (r["MATNR"], r["WERKS"]))
    return rows


def last_batch(out_dir):
    out_dir = pathlib.Path(out_dir)
    manifests = sorted(out_dir.glob("*.manifest.json"))
    if not manifests:
        return None
    return json.loads(manifests[-1].read_text())


def emit_batch(conn, records_df, out_dir, approver="samanvay", mode="full",
               engine_rev="rev3", threshold=None, note=""):
    """Write Z_NMC_MAP.csv + manifest for this batch. mode: 'full' | 'delta'.

    A delta batch carries only rows whose national code or status differs from
    the previous batch, plus rows that are new. Unchanged rows are omitted
    rather than re-sent, because an SAP load of 400,000 unchanged rows is an
    outage waiting for a maintenance window.
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = build_payload(conn, records_df, approver=approver)

    previous = last_batch(out_dir)
    emitted, unchanged = rows, 0
    if mode == "delta" and previous:
        prev_path = out_dir / previous["payload_file"]
        prev = {(r["MATNR"], r["WERKS"]): r for r in sap.read_table(prev_path)} \
            if prev_path.exists() else {}
        emitted = []
        for r in rows:
            old = prev.get((r["MATNR"], r["WERKS"]))
            if old and old.get("ZZNMC") == r["ZZNMC"] and \
                    old.get("ZZNMC_STATUS") == r["ZZNMC_STATUS"] and \
                    old.get("ZZNMC_CONF") == r["ZZNMC_CONF"]:
                unchanged += 1
                continue
            emitted.append(r)

    batch = _batch_id()
    payload_name = f"{batch}.Z_NMC_MAP.csv"
    payload = sap.write_table(out_dir / payload_name, sap.ZNMC_FIELDS, emitted)

    reg_stats = registry.stats(conn)
    manifest = dict(
        batch_id=batch,
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        mode=mode,
        payload_file=payload_name,
        payload_sha256=sap.sha256_of(payload),
        rows=len(emitted),
        rows_unchanged_suppressed=unchanged,
        target_table="Z_NMC_MAP",
        matnr_modified=False,
        distinct_national_codes=len({r["ZZNMC"] for r in emitted}),
        rows_confirmed=sum(1 for r in emitted if r["ZZNMC_CONF"] == "C"),
        rows_provisional=sum(1 for r in emitted if r["ZZNMC_CONF"] == "P"),
        legacy_codes_mapped=reg_stats["legacy_codes_mapped"],
        active_codes=reg_stats["active_codes"],
        superseded_codes=reg_stats["superseded_codes"],
        engine_revision=engine_rev,
        decision_threshold=threshold,
        approver=approver,
        previous_batch=(previous or {}).get("batch_id"),
        note=note,
        reversible=True,
        revoke_hint=f"delete from Z_NMC_MAP where ZZ_SOURCE='SAMANVAY' and ZZ_VALID_FROM='{batch[3:11]}'",
    )
    (out_dir / f"{batch}.manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def verify_batch(out_dir, batch_id):
    """Re-hash the payload and compare to the manifest.

    Called before an SAP load. A payload edited between generation and load -
    by a well-meaning person 'just fixing one row' - is the failure mode this
    catches, and it is not hypothetical.
    """
    out_dir = pathlib.Path(out_dir)
    manifest = json.loads((out_dir / f"{batch_id}.manifest.json").read_text())
    payload = out_dir / manifest["payload_file"]
    if not payload.exists():
        return dict(ok=False, reason="payload file missing", batch_id=batch_id)
    actual = sap.sha256_of(payload)
    return dict(ok=actual == manifest["payload_sha256"], batch_id=batch_id,
                expected=manifest["payload_sha256"], actual=actual,
                rows=manifest["rows"])


def revoke_batch(out_dir, batch_id, reason=""):
    """Mark a batch revoked. The payload stays on disk - a revoked batch that
    vanishes is a batch nobody can audit."""
    out_dir = pathlib.Path(out_dir)
    path = out_dir / f"{batch_id}.manifest.json"
    manifest = json.loads(path.read_text())
    manifest["revoked"] = True
    manifest["revoked_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    manifest["revoked_reason"] = reason
    path.write_text(json.dumps(manifest, indent=2))
    return manifest
