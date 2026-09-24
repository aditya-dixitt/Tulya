"""Shaping append-only audit events.

`audit_events` has no update path anywhere in the application, and this module
is the reason that is true rather than merely intended: it offers `event()` and
nothing else. There is no `amend`, no `correct`, no `redact`. A mistake in the
trail is fixed by appending the correction, which is what an auditor expects to
see and what a silent edit destroys.

Two fields do real work and are easy to get wrong:

**`score_at_event`** is the score the actor was looking at, not the score the
engine would produce now. It is passed in from the frozen `score_at_decision`,
never recomputed here.

**`before_state` / `after_state`** are the group state around the action, so a
reader can answer "what changed" without replaying every event since. They are
plain strings on purpose — an auditor reads them, a machine reads `payload`.

Pure module: no database, no network, no model.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AuditRow:
    """Shaped for AuditEvent(**row.as_dict())."""

    action: str
    entity_type: str | None = None
    entity_id: int | None = None
    actor_id: int | None = None
    actor_username: str | None = None
    record_a_id: int | None = None
    record_b_id: int | None = None
    score_at_event: float | None = None
    before_state: str | None = None
    after_state: str | None = None
    detail: str | None = None
    request_id: str | None = None
    payload: dict | None = field(default=None)

    def as_dict(self) -> dict:
        return {
            "action": self.action, "entity_type": self.entity_type,
            "entity_id": self.entity_id, "actor_id": self.actor_id,
            "actor_username": self.actor_username,
            "record_a_id": self.record_a_id, "record_b_id": self.record_b_id,
            "score_at_event": self.score_at_event,
            "before_state": self.before_state, "after_state": self.after_state,
            "detail": self.detail, "request_id": self.request_id,
            "payload": self.payload,
        }

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, default=str)


def _state(members) -> str | None:
    if members is None:
        return None
    members = sorted(members)
    if not members:
        return "no group"
    return f"group of {len(members)}: {', '.join(str(m) for m in members)}"


def event(action: str, *, actor_id=None, actor_username=None, entity_type=None,
          entity_id=None, record_a_id=None, record_b_id=None,
          score_at_event=None, before_members=None, after_members=None,
          detail=None, request_id=None, payload=None) -> AuditRow:
    """One thing that happened. Append it; never edit it."""
    if not action:
        raise ValueError("an audit event must name an action")
    return AuditRow(
        action=action, entity_type=entity_type, entity_id=entity_id,
        actor_id=actor_id, actor_username=actor_username,
        record_a_id=record_a_id, record_b_id=record_b_id,
        score_at_event=score_at_event,
        before_state=_state(before_members), after_state=_state(after_members),
        detail=detail, request_id=request_id, payload=payload,
    )


def for_decision(decision, *, match_id: int, actor_username: str | None = None,
                 record_a_id: int | None = None, record_b_id: int | None = None,
                 before_members=None, after_members=None,
                 request_id: str | None = None) -> AuditRow:
    """The audit row for a `review.Decision`, with its frozen score carried over."""
    return event(
        f"review.{decision.action}.{decision.status}",
        actor_id=decision.decided_by_id, actor_username=actor_username,
        entity_type="material_match", entity_id=match_id,
        record_a_id=record_a_id, record_b_id=record_b_id,
        score_at_event=decision.score_at_decision,
        before_members=before_members, after_members=after_members,
        detail=decision.reason, request_id=request_id,
        payload={"value_at_stake": decision.value_at_stake,
                 "needs_second": decision.needs_second},
    )


def for_blocked_edge(blocked, *, actor_id=None, actor_username=None,
                     request_id: str | None = None) -> AuditRow:
    """A refused approval is recorded as loudly as an accepted one.

    The steward made a decision and the system declined to carry it out. That
    is exactly the kind of event that must not be invisible.
    """
    return event(
        "grouping.edge_blocked", actor_id=actor_id, actor_username=actor_username,
        entity_type="review", entity_id=blocked.edge.review_id,
        record_a_id=blocked.edge.a, record_b_id=blocked.edge.b,
        score_at_event=blocked.edge.score, detail=blocked.reason,
        request_id=request_id, payload={"conflicts": list(blocked.conflicts)},
    )
