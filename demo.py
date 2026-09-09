"""The demo surface: the three reason panels, and live search.

    python3 demo.py panels           the accepted / vetoed / capped examples
    python3 demo.py search "hex bolt 12mm stainless"
"""
import sys, json, pathlib, pickle
import numpy as np, pandas as pd

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))
import tableio
from engine.normalize import normalize
from engine.attributes import extract
from engine.fuzzy import token_set_ratio
from engine.score import fuse
from engine.explain import explain, render

OUT = ROOT / "data/out"
SPLIT = "test"


def _ctx():
    recs = tableio.read("data/out/records")
    recs = recs[recs.split == SPLIT].set_index("record_id")
    prep = tableio.read(f"data/out/prepared_{SPLIT}").set_index("record_id")
    pairs = tableio.read(f"data/out/pairs_{SPLIT}")
    return recs, prep, pairs


def _row(recs, prep, rid):
    r = recs.loc[rid]
    return dict(cpse=r.cpse, legacy_code=r.legacy_code, description=r.description,
                attrs=json.loads(prep["attrs"].loc[rid]))


def _panel(recs, prep, a, b):
    ra, rb = _row(recs, prep, a), _row(recs, prep, b)
    na, nb = prep["norm"].loc[a], prep["norm"].loc[b]
    enc = pickle.load(open(OUT / "encoder.pkl", "rb"))[0]
    v = enc.transform([na, nb])
    cos = float(v[0] @ v[1])
    r = fuse(max(0.0, min(1.0, cos)), token_set_ratio(na, nb) / 100.0,
             ra["attrs"], rb["attrs"])
    return render(explain(ra, rb, r))


def panels():
    recs, prep, pairs = _ctx()
    cl = recs.cluster_id
    pairs["true"] = (cl.reindex(pairs.a).to_numpy() == cl.reindex(pairs.b).to_numpy())

    acc = pairs[(pairs.decision == "AUTO_SUGGEST") & pairs["true"] &
                (pairs.coverage >= 3)].sort_values("score", ascending=False)
    veto = pairs[pairs.vetoed & ~pairs["true"]].sort_values("cos", ascending=False)
    cap = pairs[(pairs.decision == "REVIEW") & (pairs.score >= 0.92) &
                (pairs.coverage <= 1)].sort_values("score", ascending=False)

    for title, sub in [("1. ACCEPTED - proposed to the steward", acc),
                       ("2. REJECTED - text says yes, the specification says no", veto),
                       ("3. HELD - scores above the threshold, too little evidence", cap)]:
        print("\n" + "=" * 74 + f"\n{title}\n" + "=" * 74)
        if not len(sub):
            print("  (no example in this split)"); continue
        r = sub.iloc[0]
        print(_panel(recs, prep, int(r.a), int(r.b)))


def search(q, k=5):
    recs, prep, _ = _ctx()
    enc = pickle.load(open(OUT / "encoder.pkl", "rb"))[0]
    nq = normalize(q); aq = extract(nq)
    V = np.load(OUT / f"vecs_{SPLIT}.npy")
    ids = prep.index.to_numpy()
    qv = enc.transform([nq])[0]
    sims = V @ qv
    top = np.argsort(-sims)[:60]
    out = []
    for i in top:
        rid = int(ids[i]); nb = prep["norm"].loc[rid]
        r = fuse(float(max(0, min(1, sims[i]))), token_set_ratio(nq, nb) / 100.0,
                 aq, json.loads(prep["attrs"].loc[rid]))
        out.append((r["score"], r["decision"], rid))
        if len([o for o in out if not o[1].startswith("REJECT")]) >= k:
            break
    print(f'\nquery: "{q}"\n  normalised: {nq}\n  specs read: {aq}\n')
    shown = 0
    for sc, dec, rid in sorted(out, key=lambda t: -t[0]):
        if dec == "REJECTED_VETO" or shown >= k:
            continue
        r = recs.loc[rid]
        print(f"  {sc:.3f}  {dec:<13} {r.cpse}·{r.legacy_code:<12} {r.description}")
        shown += 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        search(" ".join(sys.argv[2:]) or "hex bolt 12mm stainless")
    else:
        panels()
