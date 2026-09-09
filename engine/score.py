"""Fusion scoring, the hard-key veto, and the decision bands."""
from engine.attributes import compare

W_COS, W_FUZ, W_ATTR = 0.60, 0.25, 0.15
T_DISCARD, T_AUTO = 0.75, 0.92     # INITIAL configuration, selected on validation
MIN_COVERAGE = 2                   # hard keys known on BOTH sides


def fuse(cos, fuz, attrs_a, attrs_b):
    """-> dict with score, decision and everything needed to explain both."""
    verdicts, n_match, n_mismatch, n_known = compare(attrs_a, attrs_b)

    # what the fusion alone would have said, veto ignored - kept so the harness
    # can measure exactly what the veto contributes (ablation row in RESULTS.md)
    if n_known:
        raw = W_COS * cos + W_FUZ * fuz + W_ATTR * (n_match / n_known)
    else:
        raw = (W_COS * cos + W_FUZ * fuz) / (W_COS + W_FUZ)

    if n_mismatch:                                   # engineering fact beats text
        conflicts = [k for k, v in verdicts.items() if v == "MISMATCH"]
        return dict(score=0.0, score_noveto=raw, cos=cos, fuz=fuz, attr=None,
                    verdicts=verdicts, coverage=n_known, decision="REJECTED_VETO",
                    vetoed=True, capped=False, conflicts=conflicts,
                    reason=f"hard-key conflict on {', '.join(conflicts)}")

    if n_known:
        attr = n_match / n_known
        score = W_COS * cos + W_FUZ * fuz + W_ATTR * attr
    else:                                            # no shared evidence: renormalise
        attr = None
        score = (W_COS * cos + W_FUZ * fuz) / (W_COS + W_FUZ)

    if score < T_DISCARD:
        decision, reason = "DISCARD", "below discard threshold"
    elif score < T_AUTO:
        decision, reason = "REVIEW", "in steward review band"
    else:
        decision, reason = "AUTO_SUGGEST", "above auto-suggest threshold"

    capped = False
    if decision == "AUTO_SUGGEST" and n_known < MIN_COVERAGE:
        decision, capped = "REVIEW", True
        reason = (f"score {score:.2f} clears auto-suggest but only {n_known} hard "
                  f"key(s) known on both sides - capped at review")

    return dict(score=score, score_noveto=raw, cos=cos, fuz=fuz, attr=attr,
                verdicts=verdicts, coverage=n_known, decision=decision,
                vetoed=False, capped=capped, conflicts=[], reason=reason)
