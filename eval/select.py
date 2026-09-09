"""Choose the auto-suggest threshold ON THE VALIDATION SPLIT, and write down why.

The asymmetry that drives the choice: a false merge silently corrupts a system of
record and is discovered late; a missed merge merely leaves a duplicate in place,
which is the status quo. So we do not maximise F1 - we take the lowest threshold
that still meets a precision floor, which buys the most coverage at acceptable risk.
"""
import json, sys, pathlib, argparse
import numpy as np, pandas as pd

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import tableio
from eval.harness import load, layer_c

PRECISION_FLOOR = 0.95     # the operational target, on UNSEEN data
VAL_MARGIN = 0.03          # required headroom on validation

# Why a margin. The lowest threshold that merely touches the floor on validation
# is the most fragile point on the curve: 37% of test records use corruption
# recipes dev and val never see, and precision degrades a couple of points across
# that gap. Selecting at the margin therefore lands below target on unseen data.
# We require floor+margin on validation so the operational target survives the gap.


def sweep(split="val", floor=PRECISION_FLOOR, margin=VAL_MARGIN):
    recs, prep, pairs, pos, hn, stats = load(split)
    cl = recs.set_index("record_id").cluster_id
    is_true = (cl.reindex(pairs.a).to_numpy() == cl.reindex(pairs.b).to_numpy())
    n_true = len(pos)

    rows = []
    for t in np.arange(0.80, 0.995, 0.01):
        c = layer_c(recs, pairs, is_true, n_true, t_auto=float(t))
        rows.append(dict(threshold=round(float(t), 2),
                         auto_precision=c["auto_suggest_precision"],
                         auto_pairs=c["auto_suggest_pairs"],
                         false_merges=c["false_merges_proposed"],
                         coverage=c["coverage"],
                         pct_review=c["pct_records_needing_review"]))
    df = pd.DataFrame(rows)
    ok = df[df.auto_precision >= floor + margin]
    chosen = float(ok.threshold.iloc[0]) if len(ok) else float(df.threshold.iloc[-1])
    met = bool(len(ok))
    out = dict(split=split, precision_floor=floor, val_margin=margin,
               chosen_threshold=chosen, floor_met=met, table=rows,
               justification=(
                   f"Lowest threshold whose validation auto-suggest precision "
                   f"reaches {floor + margin:.2f} — the {floor:.2f} operational "
                   f"target plus {margin:.2f} headroom for the validation-to-test "
                   f"gap, since a third of test records use corruption recipes "
                   f"never seen in training. The floor is on precision, not F1, "
                   f"because a wrong merge costs more than a missed one."
                   if met else
                   f"No threshold reached the {floor:.2f} precision floor on "
                   f"validation; reporting the strictest available."))
    json.dump(out, open(ROOT / "data/out/threshold_selection.json", "w"), indent=2)
    print(f"{'thr':>5} {'auto P':>8} {'pairs':>8} {'wrong':>7} {'coverage':>9} {'%review':>8}")
    for r in rows:
        mark = " <-- chosen" if r["threshold"] == chosen else ""
        print(f"{r['threshold']:>5.2f} {r['auto_precision']:>8.4f} {r['auto_pairs']:>8,} "
              f"{r['false_merges']:>7,} {r['coverage']:>9.4f} {r['pct_review']:>8.4f}{mark}")
    print(f"\nchosen threshold = {chosen:.2f}  (precision floor {floor:.2f} "
          f"{'met' if met else 'NOT met'})")
    return chosen


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor", type=float, default=PRECISION_FLOOR)
    ap.add_argument("--margin", type=float, default=VAL_MARGIN)
    a = ap.parse_args(); sweep("val", a.floor, a.margin)
