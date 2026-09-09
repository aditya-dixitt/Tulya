"""Builds a self-contained, shareable HTML copy of the steward console.

Why this exists: the production console (api/app.py) needs a running Flask
process. For sharing outside a machine that can run Python — a link to send
judges, a laptop with no repo checked out — this script snapshots a sample
of REAL scored pairs from the locked test-split run (queue, auto-suggest,
vetoed examples, a handful of live-search queries) into one HTML file with
no server dependency. Approve / reject / un-merge still work — they run in
the browser via a JS union-find port of api/grouping.py and persist to
localStorage — but the underlying pair data is a frozen sample, not a live
read of data/out/pairs_test.csv.

Run:  python3 api/export_static_demo.py
Output: reports/steward_console_demo.html
"""
import sys, json, pickle, pathlib
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import tableio
from engine.attributes import compare, extract
from engine.normalize import normalize
from engine.fuzzy import token_set_ratio
from engine.score import fuse, T_DISCARD, T_AUTO
from engine.explain import explain

OUT = ROOT / "data" / "out"
SPLIT = "test"
N_QUEUE, N_AUTO, N_VETOED = 220, 160, 25
PRESET_QUERIES = [
    "hex bolt 12mm stainless", "ball valve 2 inch class 600", "ss304 gate valve 4 inch",
    "gasket spiral wound", "centrifugal pump 40 m3/hr", "xlpe cable 3 core 240 sqmm",
    "roller bearing NU210", "seamless pipe 10 inch schedule xs",
]


def build_data():
    recs = tableio.read("data/out/records")
    recs = recs[recs.split == SPLIT].set_index("record_id")
    prep = tableio.read(f"data/out/prepared_{SPLIT}").set_index("record_id")
    pairs = tableio.read(f"data/out/pairs_{SPLIT}")
    with open(OUT / "encoder.pkl", "rb") as f:
        encoder = pickle.load(f)[0]
    vecs = np.load(OUT / f"vecs_{SPLIT}.npy")
    vec_ids = prep.index.to_numpy()
    run_info = json.loads((OUT / f"run_{SPLIT}.json").read_text())
    thresh_info = json.loads((OUT / "threshold_selection.json").read_text())

    def row_dict(rid):
        r = recs.loc[rid]
        attrs = json.loads(prep.at[rid, "attrs"]) if rid in prep.index else {}
        # ~1.4% of records fail category extraction and fall into the global
        # block; prep.category is NaN there, which is not valid JSON.
        category = prep.at[rid, "category"] if rid in prep.index else None
        if category is None or (isinstance(category, float) and pd.isna(category)):
            category = r.get("category_true") or "unclassified"
        return dict(record_id=int(rid), cpse=r.cpse, legacy_code=str(r.legacy_code),
                    description=r.description, category=category, attrs=attrs)

    def build_item(row):
        a, b = int(row.a), int(row.b)
        ra, rb = row_dict(a), row_dict(b)
        r = dict(score=float(row.score), cos=float(row.cos), fuz=float(row.fuz),
                 attr=(float(row.attr) if pd.notna(row.attr) else None),
                 coverage=int(row.coverage), decision=row.decision, vetoed=bool(row.vetoed))
        verdicts, n_match, n_mismatch, n_known = compare(ra["attrs"], rb["attrs"])
        r["verdicts"] = verdicts
        r["reason"] = (
            "hard-key conflict on " + ", ".join(k for k, v in verdicts.items() if v == "MISMATCH")
        ) if row.vetoed else (
            "above auto-suggest threshold" if row.decision == "AUTO_SUGGEST" else
            "in steward review band" if row.decision == "REVIEW" else "below discard threshold")
        x = explain(ra, rb, r)
        return dict(a=a, b=b, score=round(r["score"], 4), cos=round(r["cos"], 4), fuz=round(r["fuz"], 4),
                    coverage=r["coverage"], decision=row.decision, record_a=ra, record_b=rb, explain=x)

    review = pairs[pairs.decision == "REVIEW"].sort_values("score", ascending=False).head(N_QUEUE)
    auto = pairs[pairs.decision == "AUTO_SUGGEST"].sort_values("score", ascending=False).head(N_AUTO)
    vetoed = pairs[pairs.vetoed].sort_values("cos", ascending=False).head(N_VETOED)

    def do_search(q, k=6):
        nq = normalize(q)
        aq = extract(nq)
        qv = encoder.transform([nq])[0]
        sims = vecs @ qv
        top = np.argsort(-sims)[:80]
        scored = []
        for i in top:
            rid = int(vec_ids[i])
            nb = prep.at[rid, "norm"]
            r = fuse(float(max(0, min(1, sims[i]))), token_set_ratio(nq, nb) / 100.0,
                      aq, json.loads(prep.at[rid, "attrs"]))
            if r["decision"] == "REJECTED_VETO":
                continue
            scored.append((r["score"], r["decision"], rid))
        scored.sort(key=lambda t: -t[0])
        results = []
        for sc, dec, rid in scored[:k]:
            rr = row_dict(rid)
            rr.update(score=round(sc, 4), decision=dec)
            results.append(rr)
        return dict(query=q, normalised=nq, extracted_attrs=aq, results=results)

    return dict(
        split=SPLIT, records=int(len(recs)), pairs_scored=int(len(pairs)),
        decision_counts={k: int(v) for k, v in pairs["decision"].value_counts().items()},
        engine=dict(encoder_backend=run_info["encoder"], index_backend=run_info["index"],
                    fuzzy_backend=run_info["fuzzy"], reduction_ratio=run_info["reduction_ratio"],
                    candidate_pairs=run_info["candidate_pairs"]),
        threshold=dict(t_auto=T_AUTO, t_discard=T_DISCARD, chosen=thresh_info["chosen_threshold"],
                       justification=thresh_info["justification"]),
        queue=[build_item(r) for r in review.itertuples()],
        auto_suggest=[build_item(r) for r in auto.itertuples()],
        vetoed_examples=[build_item(r) for r in vetoed.itertuples()],
        search_presets=[do_search(q) for q in PRESET_QUERIES],
    )


PAGE_TEMPLATE = pathlib.Path(__file__).with_name("static_demo_template.html").read_text()


def _sanitize_nan(o):
    """NaN/Infinity are valid to Python's json.dumps (non-standard extension)
    but not to a browser's JSON.parse - belt-and-suspenders on top of the
    category fix above, in case another NaN sneaks in from the source data."""
    if isinstance(o, float):
        return None if (o != o or o in (float("inf"), float("-inf"))) else o
    if isinstance(o, dict):
        return {k: _sanitize_nan(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_sanitize_nan(v) for v in o]
    return o


def main():
    data = _sanitize_nan(build_data())
    html = PAGE_TEMPLATE.replace("__DATA_JSON__", json.dumps(data))
    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "steward_console_demo.html"
    out_path.write_text(html)
    print(f"wrote {out_path} ({out_path.stat().st_size / 1024:.0f} KB) — "
          f"{len(data['queue'])} queue, {len(data['auto_suggest'])} auto-suggest, "
          f"{len(data['vetoed_examples'])} vetoed examples")


if __name__ == "__main__":
    main()
