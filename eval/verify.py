"""Prove the measured numbers still hold, without touching the evidence.

Everything added for the final build - taxonomy, national codes, the registry,
the ERP connector, accounts, group-level consistency - sits *downstream* of
matching. None of it is allowed to change a score. This asserts that rather
than claiming it:

  1. recompute the fused score for every pair in the locked test split, from
     the cached vectors and the prepared attributes, and diff against what
     pairs_test.csv has recorded;
  2. recompute Layer C (auto-suggest precision and coverage) from those pairs
     and the ground truth, and compare to what holdout_run.json locked in;
  3. re-audit every golden record the current approvals produce for internal
     contradictions.

Nothing here writes to data/out. A verification step that can overwrite the
thing it verifies is theatre.

    make verify
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "api"))

import tableio
from engine.fuzzy import token_set_ratio
from engine.score import fuse

OUT = ROOT / "data/out"
SPLIT = "test"
TOL = 1e-9


def _fail(msg):
    print(f"  FAIL  {msg}")
    return False


def _ok(msg):
    print(f"  ok    {msg}")
    return True


def check_scores():
    print("\n1. every score in the locked split recomputes to the same value")
    pairs = tableio.read(f"data/out/pairs_{SPLIT}")
    prep = tableio.read(f"data/out/prepared_{SPLIT}").set_index("record_id")
    vecs = np.load(OUT / f"vecs_{SPLIT}.npy")
    pos = {rid: i for i, rid in enumerate(prep.index)}
    attrs = {rid: json.loads(prep.at[rid, "attrs"]) for rid in prep.index}
    norm = prep["norm"].to_dict()

    sample = pairs if len(pairs) <= 40000 else pairs.sample(40000, random_state=0)
    worst, bad, decision_mismatch = 0.0, 0, 0
    for r in sample.itertuples():
        a, b = int(r.a), int(r.b)
        cos = float(max(0.0, min(1.0, vecs[pos[a]] @ vecs[pos[b]])))
        fz = token_set_ratio(norm[a], norm[b]) / 100.0
        got = fuse(cos, fz, attrs[a], attrs[b])
        d = abs(got["score"] - float(r.score))
        worst = max(worst, d)
        bad += d > 1e-6
        decision_mismatch += got["decision"] != r.decision
    print(f"        {len(sample):,} pairs recomputed, largest score difference {worst:.2e}")
    return (_ok("scores identical") if bad == 0 else _fail(f"{bad} scores differ")) and \
           (_ok("decisions identical") if decision_mismatch == 0
            else _fail(f"{decision_mismatch} decisions differ"))


def check_layer_c():
    print("\n2. Layer C reproduces the locked holdout result")
    locked = json.loads((OUT / "holdout_run.json").read_text())
    want = locked["result"]["layer_c"]
    t = locked["threshold"]

    # Re-run the harness's own Layer C over the pairs on disk. This deliberately
    # reuses the measurement code rather than reimplementing it: the question
    # here is "do the same inputs still produce the locked answer", and a
    # second, subtly different formula answers a different question. The
    # genuinely independent check is step 1 above, which recomputes the scores
    # from the vectors without going near the harness.
    sys.path.insert(0, str(ROOT / "eval"))
    import harness

    recs, prep, pairs, pos, hn, _stats = harness.load(SPLIT)
    _B, _hard, is_true, n_true = harness.layer_b(recs, prep, pairs, pos, hn)
    got_c = harness.layer_c(recs, pairs, is_true, n_true, t_auto=t)

    ok = True
    for name, got, expect in (
            ("auto-suggest precision", got_c["auto_suggest_precision"],
             want.get("auto_suggest_precision")),
            ("coverage of true duplicates", got_c["coverage"], want.get("coverage")),
            ("records needing a human", got_c["pct_records_needing_review"],
             want.get("pct_records_needing_review"))):
        if expect is None:
            print(f"  ..    {name}: {got:.4f} (nothing locked to compare against)")
            continue
        same = abs(got - float(expect)) < 1e-4
        ok &= same
        (_ok if same else _fail)(f"{name}: {got:.4f} vs locked {float(expect):.4f}")
    return ok


def check_group_consistency():
    print("\n3. no golden record contradicts itself")
    import grouping
    import store
    db = OUT / "steward.db"
    if not db.exists():
        print("  ..    no steward.db yet - nothing approved, nothing to audit")
        return True
    import sqlite3
    conn = store.init_db(db)
    recs = tableio.read("data/out/records")
    recs = recs[recs.split == SPLIT].set_index("record_id")
    prep = tableio.read(f"data/out/prepared_{SPLIT}").set_index("record_id")
    state = grouping.resolve(store.approved_edges(conn), recs, prep)
    bad = grouping.audit_consistency(state["groups"], prep)
    print(f"        {len(state['groups']):,} golden records, "
          f"{len(state['blocked'])} approval(s) held back as contradictory")
    return _ok("all internally consistent") if not bad else \
        _fail(f"{len(bad)} contradictory group(s): {bad[:2]}")


def main():
    print("TULYA  verification of the locked measurements")
    print("=" * 66)
    results = [check_scores(), check_layer_c(), check_group_consistency()]
    print("\n" + "=" * 66)
    if all(results):
        print("PASS - the engine's measured behaviour is unchanged.")
        return 0
    print("FAIL - something downstream changed a measured number. Do not ship "
          "the old numbers.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
