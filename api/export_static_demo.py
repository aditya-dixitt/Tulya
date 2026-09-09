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
from engine.score import fuse, T_DISCARD, T_AUTO, W_COS, W_FUZ, W_ATTR
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

    # ground truth, used only to label the challenge cases after the judge has
    # committed to an answer - never to influence what the engine proposes
    cl = recs.cluster_id
    pairs["is_true"] = (cl.reindex(pairs.a).to_numpy() == cl.reindex(pairs.b).to_numpy())

    # value at stake per record: the generator gives every record a real
    # quantity and unit value, so this is a genuine number, not a stand-in
    spend = (recs.qty * recs.unit_value)

    def build_item(row, with_priority=False):
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
        # per-signal contribution to the fused score, so the panel can show
        # where the number actually came from rather than just its total
        contrib = dict(cos=round(W_COS * r["cos"], 4), fuz=round(W_FUZ * r["fuz"], 4),
                       attr=(round(W_ATTR * r["attr"], 4) if r["attr"] is not None else None))
        item = dict(a=a, b=b, score=round(r["score"], 4), cos=round(r["cos"], 4), fuz=round(r["fuz"], 4),
                    attr=(round(r["attr"], 4) if r["attr"] is not None else None),
                    score_noveto=round(float(row.score_noveto), 4) if hasattr(row, "score_noveto") else None,
                    coverage=r["coverage"], decision=row.decision, contrib=contrib,
                    record_a=ra, record_b=rb, explain=x)
        if with_priority:
            item["priority"] = priority_of(row)
        return item

    def priority_of(row):
        """Which pairs should a steward open first?

        Three real signals, no invented ones:
          uncertainty - how close the score sits to the operating threshold;
                        a pair at 0.918 is a genuinely marginal call, one at
                        0.76 is not.
          thin evidence - how few hard keys were readable on both sides. Fewer
                        specs means the score rests on text alone.
          value at stake - qty x unit_value across both records: merging (or
                        failing to merge) a high-spend item costs more.
        """
        score = float(row.score)
        uncertainty = max(0.0, 1.0 - abs(score - T_AUTO) / (T_AUTO - T_DISCARD))
        thin = 1.0 / (1.0 + int(row.coverage))
        value = float(spend.get(int(row.a), 0.0) + spend.get(int(row.b), 0.0))
        return dict(uncertainty=round(uncertainty, 3), thin_evidence=round(thin, 3),
                    value_at_stake=round(value, 2),
                    raw=round(0.40 * uncertainty + 0.30 * thin, 4), value_raw=value)

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

    # ---- three cases a judge can try their own judgement on ----------------
    # All real rows from the locked test split. The ground-truth answer is
    # carried alongside so the page can reveal it only after they've guessed.
    true_pairs = pairs[pairs.is_true]
    # "easy" must actually look easy to a human: rank by raw-description
    # similarity, not by the engine's own score, or we end up calling a pair
    # of wildly different strings the easy case.
    import difflib
    _easy_pool = true_pairs[(true_pairs.decision == "AUTO_SUGGEST") &
                            (true_pairs.coverage >= 3)].head(400).copy()
    _easy_pool["raw_sim"] = [
        difflib.SequenceMatcher(None, str(recs.at[int(r.a), "description"]).lower(),
                                str(recs.at[int(r.b), "description"]).lower()).ratio()
        for r in _easy_pool.itertuples()]
    # exclude byte-identical descriptions - a pair of literally identical
    # strings makes the "would you have caught it?" question meaningless.
    # Aim for visibly-the-same-but-not-identical, around 0.85 raw similarity.
    _easy_pool = _easy_pool[_easy_pool.raw_sim < 0.97]
    _easy_pool["easy_rank"] = (_easy_pool.raw_sim - 0.85).abs()
    easy = _easy_pool.sort_values("easy_rank")
    # a real duplicate whose text agrees least - the case plain fuzzy matching loses
    hard = true_pairs[(true_pairs.decision != "DISCARD") & (~true_pairs.vetoed)] \
        .sort_values("fuz", ascending=True)
    # near-identical text, different item: the pair a naive matcher merges
    danger = pairs[pairs.vetoed & (~pairs.is_true)].sort_values("cos", ascending=False)

    def challenge_case(row, kind, prompt, lesson):
        it = build_item(row)
        it.update(kind=kind, prompt=prompt, lesson=lesson,
                  truth="SAME" if bool(row.is_true) else "DIFFERENT",
                  engine_says="MERGE" if row.decision == "AUTO_SUGGEST" else (
                      "DO NOT MERGE" if row.vetoed else "SEND TO STEWARD"))
        return it

    challenge = []
    if len(easy):
        challenge.append(challenge_case(
            easy.iloc[0], "easy", "Two records, two CPSEs. Same item or different?",
            "Casing and spacing differ, every readable specification agrees. This is the case "
            "any matcher gets right — it is the floor, not the achievement. The two below are harder."))
    if len(hard):
        challenge.append(challenge_case(
            hard.iloc[0], "hard", "These two descriptions barely share a word. Same item or different?",
            "This is a real duplicate that pure text matching misses: the descriptions were "
            "written differently, but once abbreviations are expanded and the specifications "
            "are parsed, the identifying attributes line up."))
    if len(danger):
        challenge.append(challenge_case(
            danger.iloc[0], "danger", "These two read almost identically. Same item or different?",
            "This is the dangerous one. Text similarity is near-perfect, so a fuzzy matcher "
            "merges it — and two genuinely different parts end up under one code. SAMANVAY "
            "rejects it outright because a hard specification disagrees."))

    # ---- score distribution across every candidate pair -------------------
    edges = [round(x * 0.05, 2) for x in range(21)]
    live = pairs[~pairs.vetoed]
    hist = np.histogram(live.score.to_numpy(), bins=edges)[0].tolist()

    holdout = json.loads((OUT / "holdout_run.json").read_text())

    return dict(
        split=SPLIT, records=int(len(recs)), pairs_scored=int(len(pairs)),
        decision_counts={k: int(v) for k, v in pairs["decision"].value_counts().items()},
        engine=dict(encoder_backend=run_info["encoder"], index_backend=run_info["index"],
                    fuzzy_backend=run_info["fuzzy"], reduction_ratio=run_info["reduction_ratio"],
                    candidate_pairs=run_info["candidate_pairs"],
                    all_pairs=run_info["all_pairs"], timings=run_info["timings"],
                    weights=dict(cos=W_COS, fuz=W_FUZ, attr=W_ATTR)),
        threshold=dict(t_auto=T_AUTO, t_discard=T_DISCARD, chosen=thresh_info["chosen_threshold"],
                       justification=thresh_info["justification"],
                       floor=thresh_info["precision_floor"], margin=thresh_info["val_margin"]),
        sweep=thresh_info["table"],
        holdout=dict(run_at=holdout["run_at"], threshold=holdout["threshold"],
                     layer_a=holdout["result"]["layer_a"], layer_b=holdout["result"]["layer_b"],
                     layer_c=holdout["result"]["layer_c"],
                     hard_negatives=holdout["result"]["hard_negatives"],
                     ambiguity=holdout["result"]["ambiguity"]),
        distribution=dict(edges=edges, counts=hist, total=int(len(live))),
        queue=[build_item(r, with_priority=True) for r in review.itertuples()],
        auto_suggest=[build_item(r) for r in auto.itertuples()],
        vetoed_examples=[build_item(r) for r in vetoed.itertuples()],
        challenge=challenge,
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
