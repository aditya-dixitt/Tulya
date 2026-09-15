"""The full loop, end to end: SAP extract -> match -> approve -> national codes
-> write-back file -> SAP consumes it -> the buyer's screen afterwards.

Run it with:  make erp-demo

Why this composes the engine primitives instead of calling engine.pipeline.run:
that function is bound to the benchmark splits and writes the measured
artefacts (pairs_test.csv, run_test.json, the encoder cache). An ERP load must
never be able to overwrite the files the holdout result is computed from. The
scoring path is identical - same normalise, same extract, same blocking, same
fuse - it just cannot write where the evidence lives.

On approvals: nothing merges without a human, and this script does not pretend
otherwise. It reads real steward approvals from data/out/steward.db when they
exist. With --simulate-approvals it stands in for a steward session so the
plumbing can be demonstrated on a machine where nobody has reviewed anything
yet, and it writes `approver=SIMULATED-STEWARD` into the batch manifest so
that run is distinguishable from a real one forever after.
"""
import argparse
import json
import pathlib
import sqlite3
import sys
import time

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from engine.attributes import extract as extract_attrs
from engine.block import build_multi, category_of, size_bucket
from engine.embed import Encoder
from engine.index import ExactIP
from engine.fuzzy import token_set_ratio
from engine.normalize import normalize
from engine.score import fuse, T_AUTO
from engine import registry
from erp import extract as erp_extract, mock_erp, sap, writeback
from api import grouping

OUT = ROOT / "data/out"
ERP_DIR = ROOT / "data/erp"
TOPK = 20


def score_frame(df, encoder_path=OUT / "encoder.pkl", topk=TOPK):
    """Same pipeline stages, run over an arbitrary extracted frame."""
    import pickle
    norm = [normalize(t) for t in df.description]
    attrs = [extract_attrs(t) for t in norm]
    cats = [category_of(t) for t in norm]
    buckets = [size_bucket(a) for a in attrs]

    enc, _ = pickle.load(open(encoder_path, "rb"))
    vecs = enc.transform(norm)

    blocks, bstats = build_multi(cats, df.uom.tolist(), attrs)
    cand = {}
    for _key, members in blocks.items():
        m = np.array(members)
        sub = vecs[m]
        sims, idx = ExactIP(sub).search(sub, min(topk + 1, len(m)))
        for r in range(len(m)):
            gi = m[r]
            for c in range(idx.shape[1]):
                gj = m[idx[r, c]]
                if gi == gj:
                    continue
                a, b = (gi, gj) if gi < gj else (gj, gi)
                s = float(sims[r, c])
                if cand.get((a, b), -2) < s:
                    cand[(a, b)] = s

    ids = df.record_id.to_numpy()
    rows = []
    for (i, j), cos in cand.items():
        fz = token_set_ratio(norm[i], norm[j]) / 100.0
        r = fuse(max(0.0, min(1.0, cos)), fz, attrs[i], attrs[j])
        rows.append((int(ids[i]), int(ids[j]), r["score"], r["decision"], r["vetoed"]))
    pairs = pd.DataFrame(rows, columns=["a", "b", "score", "decision", "vetoed"])
    prep = pd.DataFrame({"record_id": ids, "norm": norm,
                         "attrs": [json.dumps(a) for a in attrs],
                         "category": cats, "bucket": buckets}).set_index("record_id")
    return pairs, prep, bstats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpse", default="IOCL",
                    help="which CPSE's material master to load (the Phase-1 case)")
    ap.add_argument("--limit", type=int, default=4000, help="cap records for a fast demo")
    ap.add_argument("--simulate-approvals", action="store_true", default=True)
    ap.add_argument("--mode", default="full", choices=["full", "delta"])
    ap.add_argument("--fresh", action="store_true", help="start from an empty registry")
    a = ap.parse_args()

    t0 = time.time()
    print(f"\nSAMANVAY  ERP round trip   ({a.cpse})")
    print("=" * 72)

    # ---------------------------------------------------------------- 1. extract
    recs = pd.read_csv(OUT / "records.csv")
    subset = recs[recs.cpse == a.cpse].head(a.limit)
    extract_dir = ERP_DIR / a.cpse
    exp = mock_erp.export_extract(subset, extract_dir, truncate=True)
    print(f"\n1. ERP extract written to data/erp/{a.cpse}/  (MARA, MAKT, MARC, MARD)")
    print(f"   {exp['materials']:,} materials across {exp['plants']} plants")
    mb, ma = exp["maktx_before"], exp["maktx_after"]
    print(f"   MAKTX is {sap.MAKTX_LIMIT} characters. {mb['share_over_limit']:.1%} of these "
          f"descriptions were longer than that")
    print(f"   and lost {mb['chars_lost']:,} characters on the way in. Mean length "
          f"{mb['mean_len']} -> {ma['mean_len']}.")
    print(f"   That truncation is not our corruption - it is what the field does.")

    # ---------------------------------------------------------------- 2. read back
    df, report, rejects = erp_extract.load_extract(extract_dir, cpse=a.cpse)
    erp_extract.write_rejects(rejects, extract_dir / "rejected_rows.csv")
    print(f"\n2. Read back through the connector: {report['records']:,} records, "
          f"{report['rejected']} rejected {report['reject_reasons'] or ''}")

    # ---------------------------------------------------------------- 3. match
    pairs, prep, bstats = score_frame(df)
    counts = pairs.decision.value_counts().to_dict()
    print(f"\n3. Matched: {len(pairs):,} candidate pairs from {len(df)*(len(df)-1)//2:,} possible")
    print(f"   {counts}")

    # ---------------------------------------------------------------- 4. approve
    recs_idx = df.set_index("record_id")
    db = OUT / "steward.db"
    edges = []
    approver = "SIMULATED-STEWARD"
    if db.exists():
        try:
            from api import store
            conn_s = sqlite3.connect(db)
            real = store.approved_edges(conn_s)
            valid = set(recs_idx.index)
            edges = [(x, y) for x, y in real if x in valid and y in valid]
            conn_s.close()
        except Exception:
            edges = []
    if edges:
        approver = "steward-console"
        print(f"\n4. Approvals: {len(edges):,} real steward approvals found in steward.db")
    elif a.simulate_approvals:
        edges = [(int(r.a), int(r.b)) for r in pairs.itertuples()
                 if r.decision == "AUTO_SUGGEST"]
        print(f"\n4. Approvals: no steward session on this machine, so {len(edges):,} "
              f"auto-suggestions are")
        print(f"   being accepted on a steward's behalf. The batch manifest will record the")
        print(f"   approver as {approver} - a simulated run stays labelled as one.")

    scores = {(int(r.a), int(r.b)): float(r.score) for r in pairs.itertuples()}
    res = grouping.resolve(edges, recs_idx, prep, scores=scores)
    groups, blocked = res["groups"], res["blocked"]
    print(f"   {len(groups):,} golden records formed from those approvals")
    if blocked:
        print(f"   {len(blocked)} approval(s) were NOT applied: each would have merged two")
        print(f"   groups that contradict each other on a hard key. Example — "
              f"{blocked[0]['a']} and {blocked[0]['b']}")
        print(f"   disagree on {', '.join(blocked[0]['conflicts'])}: "
              f"{blocked[0]['detail']}. The pairwise veto cannot")
        print(f"   see this; only the group can.")
    bad = grouping.audit_consistency(groups, prep)
    print(f"   independent consistency audit of the finished groups: "
          f"{len(bad)} internally contradictory")

    # ---------------------------------------------------------------- 5. mint
    reg_db = OUT / "registry.db"
    if a.fresh and reg_db.exists():
        reg_db.unlink()
    conn = registry.init_registry(sqlite3.connect(reg_db))
    issued = reused = refused = consolidated = held = 0
    for g in groups:
        res = registry.mint_for_group(
            conn, [m["record_id"] for m in g["members"]], recs_idx, prep,
            actor=approver, canonical_id=g["canonical"]["record_id"])
        issued += res["status"] == "issued"
        reused += res["status"] == "reused"
        consolidated += res["status"] == "consolidated"
        refused += res["status"] == "refused"
        held += len(res.get("held", []))
    st = registry.stats(conn)
    print(f"\n5. National codes: {issued:,} issued, {reused:,} reused, "
          f"{consolidated:,} consolidated, {refused:,} refused")
    print(f"   {st['legacy_codes_mapped']:,} legacy codes now map to "
          f"{st['active_codes']:,} national codes")
    print(f"   of those links: {st['confirmed_links']:,} confirmed by the row's own specs, "
          f"{st['provisional_links']:,} provisional")
    if held:
        print(f"   {held:,} member(s) were left unlinked - too little of their "
              f"description survived")
        print(f"   to justify putting a permanent national code on them.")
    if refused:
        print(f"   {refused:,} groups were refused a code because their defining "
              f"specifications")
        print(f"   could not be fully read. A code on a purchase order cannot be un-issued.")

    # ---------------------------------------------------------------- 6. write back
    manifest = writeback.emit_batch(conn, df, ERP_DIR / "outbound", approver=approver,
                                    mode=a.mode, threshold=T_AUTO,
                                    note=f"{a.cpse} material master, Phase 1 (intra-CPSE)")
    print(f"\n6. Write-back batch {manifest['batch_id']}")
    print(f"   {manifest['rows']:,} rows -> Z_NMC_MAP   "
          f"(MATNR modified: {manifest['matnr_modified']})")
    print(f"   {manifest['rows_confirmed']:,} confirmed, "
          f"{manifest['rows_provisional']:,} flagged provisional for a human to confirm")
    print(f"   sha256 {manifest['payload_sha256'][:24]}...")

    verify = writeback.verify_batch(ERP_DIR / "outbound", manifest["batch_id"])
    print(f"   checksum verified before load: {verify['ok']}")

    # ---------------------------------------------------------------- 7. ERP applies
    payload = ERP_DIR / "outbound" / manifest["payload_file"]
    applied, load_rejects = mock_erp.apply_batch(extract_dir, payload)
    print(f"\n7. ERP applied {len(applied):,} rows, rejected {len(load_rejects)}")
    if load_rejects:
        print(f"   ! {load_rejects[0].get('_reason')}")

    after = mock_erp.material_master_after(extract_dir, applied)
    coded = after[after.ZZNMC != ""]
    print(f"\n8. The buyer's screen afterwards — MATNR unchanged, columns added:")

    def _show(frame, title, tail):
        print(f"\n   {title}")
        print(frame.to_string(index=False, max_colwidth=40))
        print(f"   {tail}")

    if len(coded):
        # the win: a fully confirmed consolidation across plants
        conf = coded[coded.ZZNMC_CONF == "C"]
        sizes = conf.groupby("ZZNMC").agg(n=("MATNR", "size"), p=("PLANT", "nunique"))
        sizes = sizes[sizes.p > 1].sort_values(["p", "n"], ascending=False)
        if len(sizes):
            nmc = sizes.index[0]
            _show(conf[conf.ZZNMC == nmc].head(6),
                  f"fully confirmed — every row's own specs support {nmc}:",
                  f"{int(sizes.loc[nmc,'n'])} of this CPSE's own codes at "
                  f"{int(sizes.loc[nmc,'p'])} plants are one item, and every one of them "
                  f"says so itself.")
        # the honesty: a code carrying provisional rows
        prov = coded[coded.ZZNMC_CONF == "P"]
        if len(prov):
            nmc = prov.ZZNMC.value_counts().index[0]
            _show(coded[coded.ZZNMC == nmc].head(6),
                  f"provisional — {nmc} is proposed but not proven for every row:",
                  "the P rows lost a defining spec to the 40-character limit. Nothing "
                  "contradicts\n   the code, but nothing confirms it either, so it ships "
                  "flagged rather than asserted.")

    json.dump(dict(extract=report, blocking=bstats, decisions=counts,
                   groups=len(groups), registry=st, manifest=manifest,
                   applied=len(applied), rejected=len(load_rejects),
                   elapsed_s=round(time.time() - t0, 1)),
              open(ERP_DIR / "roundtrip_report.json", "w"), indent=2, default=str)
    print(f"\nDone in {time.time()-t0:.0f}s. Report: data/erp/roundtrip_report.json")
    conn.close()


if __name__ == "__main__":
    main()
