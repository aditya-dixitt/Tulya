"""Fusion scoring, the hard-key veto, and the decision bands.

Weights and thresholds come from configuration. They were constants in the
prototype, which meant the only way to re-tune was to edit source and lose the
provenance of what produced a given result.

The veto is the part that must not change: if a specification is known on BOTH
sides and the two disagree, the score is forced to zero no matter how similar
the text is. That is the difference between a system that finds duplicates and
one that merges an M12 bolt into an M16 bolt.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import settings
from .attributes import compare


@dataclass(frozen=True)
class ScoringConfig:
    w_cos: float = settings.W_COS
    w_fuz: float = settings.W_FUZ
    w_attr: float = settings.W_ATTR
    t_discard: float = settings.T_DISCARD
    t_auto: float = settings.T_AUTO
    min_coverage: int = settings.MIN_COVERAGE

    @classmethod
    def from_settings(cls) -> "ScoringConfig":
        return cls(settings.W_COS, settings.W_FUZ, settings.W_ATTR,
                   settings.T_DISCARD, settings.T_AUTO, settings.MIN_COVERAGE)

    def as_dict(self) -> dict:
        return {"weights": {"cos": self.w_cos, "fuz": self.w_fuz, "attr": self.w_attr},
                "thresholds": {"discard": self.t_discard, "auto_suggest": self.t_auto},
                "min_coverage": self.min_coverage}


def fuse(cos: float, fuz: float, attrs_a: dict, attrs_b: dict,
         cfg: ScoringConfig | None = None,
         provisional: set[str] | frozenset[str] | None = None) -> dict:
    """`provisional` names keys recovered by the LLM rather than by the rules.

    Such a key still vetoes — a specification conflict is worth acting on
    whoever read it, and being wrong there costs a review. It does NOT count
    toward the coverage floor, so a model that hallucinates an agreement cannot
    manufacture the evidence that lets a pair merge without a human. Wrong in
    the safe direction is a nuisance; wrong in the unsafe direction is the
    failure this project exists to prevent.
    """
    cfg = cfg or ScoringConfig.from_settings()
    verdicts, n_match, n_mismatch, n_known = compare(attrs_a, attrs_b)
    prov = frozenset(provisional or ())
    # coverage that a steward could reproduce from the text with the rules alone
    n_verified = sum(1 for k, v in verdicts.items()
                     if v in ("MATCH", "MISMATCH") and k not in prov)

    # what fusion alone would have said with the veto switched off. Kept so the
    # veto's contribution is measurable rather than asserted.
    if n_known:
        raw = cfg.w_cos * cos + cfg.w_fuz * fuz + cfg.w_attr * (n_match / n_known)
    else:
        raw = (cfg.w_cos * cos + cfg.w_fuz * fuz) / (cfg.w_cos + cfg.w_fuz)

    if n_mismatch:                                    # engineering fact beats text
        conflicts = [k for k, v in verdicts.items() if v == "MISMATCH"]
        llm_only = [k for k in conflicts if k in prov]
        return dict(score=0.0, score_noveto=raw, cos=cos, fuz=fuz, attr=None,
                    verdicts=verdicts, coverage=n_known,
                    coverage_verified=n_verified, provisional=sorted(prov),
                    decision="REJECTED_VETO", vetoed=True, capped=False,
                    conflicts=conflicts,
                    reason=f"hard-key conflict on {', '.join(conflicts)}"
                           + (f" (LLM-read: {', '.join(llm_only)})" if llm_only else ""))

    if n_known:
        attr = n_match / n_known
        score = cfg.w_cos * cos + cfg.w_fuz * fuz + cfg.w_attr * attr
    else:                                             # no shared evidence
        attr = None
        score = (cfg.w_cos * cos + cfg.w_fuz * fuz) / (cfg.w_cos + cfg.w_fuz)

    if score < cfg.t_discard:
        decision, reason = "DISCARD", "below discard threshold"
    elif score < cfg.t_auto:
        decision, reason = "REVIEW", "in steward review band"
    else:
        decision, reason = "AUTO_SUGGEST", "above auto-suggest threshold"

    # UNKNOWN is not MATCH. A high score resting on too little readable
    # evidence is capped at human review rather than trusted.
    capped = False
    if decision == "AUTO_SUGGEST" and n_verified < cfg.min_coverage:
        decision, capped = "REVIEW", True
        detail = (f"only {n_verified} rule-read hard key(s) known on both sides"
                  if n_verified == n_known else
                  f"{n_known} hard key(s) known on both sides but only "
                  f"{n_verified} read by the rules; the rest came from the LLM, "
                  f"which cannot authorise a merge")
        reason = f"score {score:.2f} clears auto-suggest but {detail} - capped at review"

    return dict(score=score, score_noveto=raw, cos=cos, fuz=fuz, attr=attr,
                verdicts=verdicts, coverage=n_known, coverage_verified=n_verified,
                provisional=sorted(prov), decision=decision,
                vetoed=False, capped=capped, conflicts=[], reason=reason)
