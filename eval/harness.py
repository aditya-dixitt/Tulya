"""Three-layer evaluation.

Pair-level precision and recall on their own grade the scorer against whatever
candidates it happened to receive - and they improve as blocking loses more true
pairs. So we measure the whole cascade:

  Layer A  candidate generation - did the right record even reach the scorer?
           blocking pair completeness, Recall@20, and reduction ratio. Recall is
           reported WITH reduction because recall alone can always be bought by
           weakening the blocks until everything is a candidate.
  Layer B  pair classification  - P/R/F1 sweep, hard-negative rejection.
  Layer C  operational outcome  - what a CPSE actually experiences.

Recall throughout is measured against ALL true pairs in the split, including
those retrieval never surfaced. That is the honest denominator.
"""
import json, sys, pathlib, itertools
import numpy as np, pandas as pd

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import tableio
from engine.block import build_multi
from engine.score import T_DISCARD, T_AUTO

OUT = ROOT / "data/out"


def load(split):
    recs = tableio.read("data/out/records")
    recs = recs[recs.split == split].reset_index(drop=True)
    prep = tableio.read(f"data/out/prepared_{split}")
    pairs = tableio.read(f"data/out/pairs_{split}")
    pos = tableio.read("data/out/pairs_pos"); pos = pos[pos.split == split]
    hn = tableio.read("data/out/pairs_hardneg"); hn = hn[hn.split == split]
    stats = json.load(open(OUT / f"run_{split}.json"))
    return recs, prep, pairs, pos, hn, stats


def layer_a(recs, prep, pairs, pos, stats):
    uom = recs.set_index("record_id").uom
    prep = prep.set_index("record_id")
    order = prep.index.to_list()
    cats = prep["category"].fillna("").to_list()
    attrs = [json.loads(a) for a in prep["attrs"]]
    uoms = [uom[i] for i in order]
    blocks, _ = build_multi(cats, uoms, attrs)

    member_of = {}
    for key, members in blocks.items():
        for m in members:
            member_of.setdefault(order[m], set()).add(key)

    a, b = pos.a.to_numpy(), pos.b.to_numpy()
    shared = np.fromiter(
        (len(member_of.get(int(x), ())) and
         len(member_of.get(int(x), set()) & member_of.get(int(y), set())) > 0
         for x, y in zip(a, b)), bool, len(a))

    cand = set(map(tuple, pairs[["a", "b"]].to_numpy()))
    retrieved = np.fromiter(
        (((int(x), int(y)) in cand) or ((int(y), int(x)) in cand)
         for x, y in zip(a, b)), bool, len(a))

    return dict(
        true_pairs=int(len(a)),
        blocking_pair_completeness=float(shared.mean()),
        recall_at_20=float(retrieved.mean()),
        lost_in_blocking=int((~shared).sum()),
        lost_in_retrieval=int((shared & ~retrieved).sum()),
        candidate_pairs=int(stats["candidate_pairs"]),
        all_pairs=int(stats["all_pairs"]),
        reduction_ratio=float(stats["reduction_ratio"]))


def _curve(score, is_true, n_true, lo=0.0, step=0.01):
    out = []
    for t in np.arange(lo, 1.0001, step):
        sel = score >= t
        k = int(sel.sum())
        tp = int(is_true[sel].sum())
        p = tp / k if k else 1.0
        r = tp / n_true
        out.append(dict(t=round(float(t), 2), predicted=k, tp=tp,
                        precision=p, recall=r,
                        f1=(2 * p * r / (p + r)) if (p + r) else 0.0))
    return out


def layer_b(recs, prep, pairs, pos, hn):
    cl = recs.set_index("record_id").cluster_id
    is_true = (cl[pairs.a].to_numpy() == cl[pairs.b].to_numpy())
    n_true = len(pos)

    norm = prep.set_index("record_id").norm
    exact = (norm[pairs.a].to_numpy() == norm[pairs.b].to_numpy()).astype(float)

    methods = {
        "Exact normalised":      exact,
        "Fuzzy only":            pairs.fuz.to_numpy(),
        "Embeddings only":       pairs.cos.to_numpy(),
        "Fusion, no veto":       pairs.score_noveto.to_numpy(),
        "SAMANVAY hybrid":       pairs.score.to_numpy(),
    }
    res = {}
    for name, sc in methods.items():
        c = _curve(sc, is_true, n_true)
        best = max(c, key=lambda d: d["f1"])
        res[name] = dict(best=best, curve=c)

    # hard negatives that actually reached the scorer
    key = {(int(x), int(y)) for x, y in pairs[["a", "b"]].to_numpy()}
    hpairs = [(int(min(x, y)), int(max(x, y))) for x, y in hn[["a", "b"]].to_numpy()]
    reached = [p for p in hpairs if p in key]
    idx = pairs.set_index(["a", "b"])
    sub = idx.loc[reached] if reached else idx.iloc[0:0]
    hard = dict(
        hard_negatives=int(len(hpairs)),
        reached_scorer=int(len(reached)),
        vetoed=int(sub.vetoed.sum()) if len(sub) else 0,
        rejected_at_operating_point=int((sub.score < T_AUTO).sum()) if len(sub) else 0,
        would_pass_without_veto=int((sub.score_noveto >= T_AUTO).sum()) if len(sub) else 0)
    if len(sub):
        hard["rejection_rate"] = hard["rejected_at_operating_point"] / len(sub)
        hard["rejection_rate_without_veto"] = 1 - hard["would_pass_without_veto"] / len(sub)
    return res, hard, is_true, n_true


def ambiguity(recs, prep, pairs, is_true):
    """Pairs whose NORMALISED text is identical but whose clusters differ.

    Description loss (truncation, an omitted spec) can leave two genuinely
    different items indistinguishable from the text alone. No matcher can
    resolve these without going back to the source system, so they set a
    ceiling on achievable precision. Reported, not hidden."""
    nm = prep.set_index("record_id")["norm"]
    same = (nm.reindex(pairs.a).to_numpy() == nm.reindex(pairs.b).to_numpy())
    amb = same & ~is_true
    auto = (pairs.score >= T_AUTO).to_numpy()
    n_auto = int(auto.sum())
    fp_auto = int((auto & ~is_true).sum())
    fp_amb = int((auto & amb).sum())
    return dict(
        identical_text_different_cluster=int(amb.sum()),
        share_of_candidates=float(amb.mean()),
        false_auto_suggests=fp_auto,
        of_which_unresolvable=fp_amb,
        of_which_real_errors=fp_auto - fp_amb,
        precision_ceiling=(1 - fp_amb / n_auto) if n_auto else 1.0)


def layer_c(recs, pairs, is_true, n_true, t_auto=T_AUTO, t_disc=T_DISCARD):
    auto = pairs.score >= t_auto
    rev = (pairs.score >= t_disc) & (pairs.score < t_auto)
    tp_auto = int(is_true[auto.to_numpy()].sum())
    tp_rev = int(is_true[rev.to_numpy()].sum())
    revrecs = pd.unique(pd.concat([pairs.a[rev], pairs.b[rev]]))
    return dict(
        operating_point=t_auto,
        coverage_auto_recall=(tp_auto / n_true),
        auto_suggest_pairs=int(auto.sum()),
        auto_suggest_precision=(tp_auto / int(auto.sum())) if int(auto.sum()) else 1.0,
        review_pairs=int(rev.sum()),
        review_precision=(tp_rev / int(rev.sum())) if int(rev.sum()) else 1.0,
        false_merges_proposed=int(auto.sum()) - tp_auto,
        coverage=(tp_auto + tp_rev) / n_true,
        records=int(len(recs)),
        records_needing_review=int(len(revrecs)),
        pct_records_needing_review=len(revrecs) / len(recs),
        vetoed_pairs=int(pairs.vetoed.sum()))


def evaluate(split, t_auto=T_AUTO):
    recs, prep, pairs, pos, hn, stats = load(split)
    A = layer_a(recs, prep, pairs, pos, stats)
    B, hard, is_true, n_true = layer_b(recs, prep, pairs, pos, hn)
    C = layer_c(recs, pairs, is_true, n_true, t_auto)
    AMB = ambiguity(recs, prep, pairs, is_true)
    return dict(split=split, ambiguity=AMB, backends=dict(encoder=stats["encoder"],
                                           index=stats["index"], fuzzy=stats["fuzzy"]),
                timings=stats["timings"], layer_a=A,
                layer_b={k: v["best"] for k, v in B.items()},
                curves={k: v["curve"] for k, v in B.items()},
                hard_negatives=hard, layer_c=C)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--t-auto", type=float, default=T_AUTO)
    a = ap.parse_args()
    r = evaluate(a.split, a.t_auto)
    json.dump(r, open(OUT / f"eval_{a.split}.json", "w"), indent=2)

    A, C = r["layer_a"], r["layer_c"]
    print(f"\n=== {a.split.upper()}  (encoder={r['backends']['encoder']}) ===")
    print("\nLAYER A - candidate generation")
    print(f"  true pairs                    {A['true_pairs']:,}")
    print(f"  blocking pair completeness    {A['blocking_pair_completeness']:.4f}"
          f"   ({A['lost_in_blocking']:,} lost)")
    print(f"  Recall@20                     {A['recall_at_20']:.4f}"
          f"   ({A['lost_in_retrieval']:,} further lost in retrieval)")
    print(f"  reduction ratio               {A['reduction_ratio']:.6f}"
          f"   ({A['candidate_pairs']:,} of {A['all_pairs']:,} pairs compared)")
    print("\nLAYER B - pair classification (best-F1 point per method)")
    print(f"  {'method':<20} {'thr':>5} {'prec':>7} {'recall':>7} {'F1':>7}")
    for k, v in r["layer_b"].items():
        print(f"  {k:<20} {v['t']:>5.2f} {v['precision']:>7.4f} "
              f"{v['recall']:>7.4f} {v['f1']:>7.4f}")
    h = r["hard_negatives"]
    print(f"\n  hard negatives reaching scorer {h['reached_scorer']:,} of {h['hard_negatives']:,}")
    if h.get("rejection_rate") is not None:
        print(f"  rejected by system             {h['rejection_rate']:.4f}")
        print(f"  would be rejected WITHOUT veto {h['rejection_rate_without_veto']:.4f}")
    AM = r["ambiguity"]
    print(f"\n  irreducible ambiguity (identical text, different item):")
    print(f"    candidate pairs affected     {AM['identical_text_different_cluster']:,}"
          f" ({AM['share_of_candidates']:.4f})")
    print(f"    precision ceiling            {AM['precision_ceiling']:.4f}")
    print("\nLAYER C - operational outcome at threshold %.2f" % C["operating_point"])
    print(f"  auto-suggest precision        {C['auto_suggest_precision']:.4f} "
          f"({C['auto_suggest_pairs']:,} pairs, {C['false_merges_proposed']:,} wrong)")
    print(f"  review-band precision         {C['review_precision']:.4f} "
          f"({C['review_pairs']:,} pairs)")
    print(f"  coverage of true duplicates   {C['coverage']:.4f}")
    print(f"  records needing a human       {C['pct_records_needing_review']:.4f}")
    print(f"  of the wrong auto-suggests, {AM['of_which_unresolvable']:,} are "
          f"unresolvable and {AM['of_which_real_errors']:,} are real errors")
