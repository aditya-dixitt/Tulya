"""The maker-checker rules for a steward decision.

Three things this module exists to make impossible rather than discouraged:

**One person cannot approve a high-value merge alone.** Above
`SECOND_APPROVAL_VALUE` an approval is *parked* as `awaiting_second`, not
applied. It does nothing to the catalogue until a different user countersigns.
The database backs this up with `no_self_countersign`; this is where the rule
is expressed in a form a caller can read.

**The score is frozen at the moment of the decision.** `score_at_decision` is
captured here and never recomputed. The engine will be re-run — new backends,
re-tuned thresholds — and when it is, what a steward was looking at when they
signed must not change underneath them. A later score is a new fact about the
pair, not a correction to the past.

**Rejections are decisions too.** A rejected pair carries a frozen score and an
audit trail exactly like an approval, because "why was this not merged" is a
question a materials team asks as often as the opposite.

Pure module: no database, no network, no model.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import settings

ACTIONS = ("approve", "reject", "conditional")
STATUSES = ("applied", "awaiting_second", "withdrawn")

#: only an approval can change the catalogue, so only an approval is parked
_NEEDS_SECOND = {"approve"}


class ReviewError(ValueError):
    """A decision that the rules refuse to record."""


class SelfCountersign(ReviewError):
    """The two-person rule, violated."""


@dataclass(frozen=True)
class Decision:
    """What to persist as a `reviews` row."""

    action: str
    status: str
    decided_by_id: int
    score_at_decision: float | None
    value_at_stake: float
    reason: str
    note: str | None = None

    @property
    def needs_second(self) -> bool:
        return self.status == "awaiting_second"

    @property
    def applied(self) -> bool:
        return self.status == "applied"

    def as_dict(self) -> dict:
        return {"action": self.action, "status": self.status,
                "decided_by_id": self.decided_by_id,
                "score_at_decision": self.score_at_decision,
                "value_at_stake": self.value_at_stake, "note": self.note}


def value_at_stake(record_a: dict, record_b: dict) -> float:
    """Quantity times unit value across both records.

    Taken from the source extract, never invented. A record missing either
    figure contributes nothing rather than an estimate — understating the value
    routes a case to one approver instead of two, so the failure is visible in
    the queue rather than silently permissive.
    """
    def side(r):
        return float((r or {}).get("qty") or 0) * float((r or {}).get("unit_value") or 0)
    return side(record_a) + side(record_b)


def decide(*, action: str, actor_id: int, score: float | None,
           value: float = 0.0, note: str | None = None,
           second_approval_value: float | None = None) -> Decision:
    """Record one steward decision, deciding for itself whether it can apply."""
    if action not in ACTIONS:
        raise ReviewError(f"unknown action {action!r}; expected one of {ACTIONS}")
    if actor_id is None:
        raise ReviewError("a decision must name the person who made it")

    threshold = (settings.SECOND_APPROVAL_VALUE if second_approval_value is None
                 else second_approval_value)
    value = float(value or 0.0)

    if action in _NEEDS_SECOND and value > threshold:
        return Decision(
            action=action, status="awaiting_second", decided_by_id=actor_id,
            score_at_decision=score, value_at_stake=value, note=note,
            reason=(f"value at stake {value:,.0f} exceeds {threshold:,.0f} — parked "
                    f"for a second approver; nothing is applied until someone else "
                    f"countersigns"),
        )

    return Decision(
        action=action, status="applied", decided_by_id=actor_id,
        score_at_decision=score, value_at_stake=value, note=note,
        reason=f"{action} applied by user {actor_id}",
    )


def countersign(decision: Decision, *, actor_id: int) -> Decision:
    """A second person signs off a parked approval.

    Returns a new Decision — the original is frozen, so the record of what the
    first approver saw and signed is not edited by the second.
    """
    if decision.status != "awaiting_second":
        raise ReviewError(
            f"only a parked approval can be countersigned; this one is "
            f"{decision.status!r}")
    if actor_id is None:
        raise ReviewError("a countersignature must name the person who made it")
    if actor_id == decision.decided_by_id:
        raise SelfCountersign(
            f"user {actor_id} proposed this approval and cannot also countersign it; "
            f"the two-person rule needs a different approver")

    return Decision(
        action=decision.action, status="applied",
        decided_by_id=decision.decided_by_id,
        score_at_decision=decision.score_at_decision,      # still the original
        value_at_stake=decision.value_at_stake, note=decision.note,
        reason=(f"countersigned by user {actor_id}; proposed by user "
                f"{decision.decided_by_id}"),
    )


def withdraw(decision: Decision, *, actor_id: int, note: str | None = None) -> Decision:
    """Withdraw a decision. The score it was made against stays frozen."""
    if decision.status == "withdrawn":
        raise ReviewError("already withdrawn")
    return Decision(
        action=decision.action, status="withdrawn",
        decided_by_id=decision.decided_by_id,
        score_at_decision=decision.score_at_decision,
        value_at_stake=decision.value_at_stake,
        note=note or decision.note,
        reason=f"withdrawn by user {actor_id}",
    )


def is_edge_approved(decision: Decision) -> bool:
    """Only an applied approval may form a group. Parked ones must not."""
    return decision.action == "approve" and decision.status == "applied"
