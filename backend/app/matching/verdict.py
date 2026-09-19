"""The six governed equivalence states.

This logic used to live in the browser (tulya/model.js). That was wrong twice
over: a decision state computed client-side cannot be trusted by an auditor,
and it meant the same rules existed in JavaScript and nowhere else. It is
server-side now, it is persisted on material_matches.equivalence_status, and
the frontend renders what the API says rather than deciding for itself.

The states are derived from what the deterministic pipeline measured — the veto
outcome, the attribute verdicts, the evidence coverage and the fused score. No
model output is consulted here and the LLM is not in this path at all.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import settings

IDENTICAL = "IDENTICAL"
EQUIVALENT = "EQUIVALENT"
CONDITIONAL = "CONDITIONAL"
DIFFERENT = "DIFFERENT"
CONFLICT = "CONFLICT"
UNRESOLVED = "UNRESOLVED"

NEXT_STEP = {
    IDENTICAL: "Ready for governed mapping",
    EQUIVALENT: "Steward approval",
    CONDITIONAL: "Engineering / steward review",
    DIFFERENT: "No mapping proposed",
    CONFLICT: "Merge blocked",
    UNRESOLVED: "More evidence required",
}

_FLAT = re.compile(r"[^a-z0-9]")


def _flat(s: str) -> str:
    return _FLAT.sub("", (s or "").lower())


@dataclass(frozen=True)
class Verdict:
    status: str
    reason: str

    @property
    def next_step(self) -> str:
        return NEXT_STEP[self.status]

    def as_dict(self) -> dict:
        return {"status": self.status, "reason": self.reason,
                "next_step": self.next_step}


def classify(*, score: float, coverage: int, vetoed: bool, verdicts: dict,
             description_a: str = "", description_b: str = "") -> Verdict:
    """Derive the governed state from measured pipeline output only."""
    mism = [k for k, v in verdicts.items() if v == "MISMATCH"]
    unk = [k for k, v in verdicts.items() if v == "UNKNOWN"]
    agree = [k for k, v in verdicts.items() if v == "MATCH"]

    if vetoed or mism:
        detail = ", ".join(mism) if mism else "a specification known on both sides disagreed"
        return Verdict(CONFLICT, f"hard specification conflict on {detail}")

    if coverage == 0 or len(unk) > len(agree):
        if coverage == 0:
            return Verdict(UNRESOLVED,
                           "no specification could be read on both sides — nothing "
                           "confirms and nothing contradicts")
        return Verdict(UNRESOLVED,
                       f"{len(unk)} specification(s) unreadable on one side against "
                       f"{len(agree)} that agree — the evidence base is mostly missing")

    if score < settings.T_DISCARD:
        return Verdict(DIFFERENT,
                       f"fused score {score:.3f} sits below the discard threshold")

    # IDENTICAL and EQUIVALENT are not degrees of confidence. IDENTICAL means
    # the two records state the item the same way once normalised; EQUIVALENT
    # means they state it differently and the specifications still agree — and
    # that second case is what this whole system exists to find.
    if score >= settings.T_AUTO and coverage >= settings.MIN_COVERAGE and not unk:
        if _flat(description_a) == _flat(description_b):
            return Verdict(IDENTICAL,
                           "normalised descriptions are indistinguishable and every "
                           "readable specification agrees")
        return Verdict(EQUIVALENT,
                       f"descriptions differ in wording but all {len(agree)} readable "
                       f"specification(s) agree and none conflict")

    if score >= settings.T_AUTO and coverage < settings.MIN_COVERAGE:
        return Verdict(CONDITIONAL,
                       f"clears {settings.T_AUTO} but rests on {coverage} readable "
                       f"specification(s) — the coverage floor caps it at review")

    if unk:
        return Verdict(CONDITIONAL,
                       f"{len(agree)} specification(s) agree, {len(unk)} could not be "
                       f"read on one side")
    return Verdict(CONDITIONAL,
                   "score sits in the steward review band — the call is marginal")
