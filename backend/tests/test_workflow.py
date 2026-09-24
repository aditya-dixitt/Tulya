"""Phase 6: review, grouping and the audit trail.

No database, no network, no model.

The test that matters most is
`test_transitive_closure_cannot_smuggle_a_conflict_into_a_group`. Two approvals
that are each individually correct combine into a group that is wrong, and
nothing at pair level is looking at it. That was a real 4.1% defect rate in the
prototype's ERP round trip before it was fixed.
"""
from __future__ import annotations

import pytest

from app.workflow import (
    ApprovedEdge, Decision, ReviewError, SelfCountersign, conflicts_between,
    countersign, decide, event, for_blocked_edge, for_decision, group,
    is_edge_approved, value_at_stake, withdraw,
)

# --------------------------------------------------------------------------
# review: the two-person rule
# --------------------------------------------------------------------------
LOW, HIGH = 10_000.0, 5_000_000.0


def test_an_ordinary_approval_applies_immediately():
    d = decide(action="approve", actor_id=1, score=0.95, value=LOW,
               second_approval_value=1_000_000.0)
    assert d.status == "applied" and d.applied and not d.needs_second


def test_a_high_value_approval_is_parked_not_applied():
    d = decide(action="approve", actor_id=1, score=0.95, value=HIGH,
               second_approval_value=1_000_000.0)
    assert d.status == "awaiting_second"
    assert d.needs_second and not d.applied
    assert "nothing is applied" in d.reason


def test_a_parked_approval_does_not_form_a_group():
    d = decide(action="approve", actor_id=1, score=0.95, value=HIGH,
               second_approval_value=1_000_000.0)
    assert is_edge_approved(d) is False
    assert is_edge_approved(countersign(d, actor_id=2)) is True


def test_the_proposer_cannot_countersign_their_own_approval():
    d = decide(action="approve", actor_id=7, score=0.95, value=HIGH,
               second_approval_value=1_000_000.0)
    with pytest.raises(SelfCountersign) as exc:
        countersign(d, actor_id=7)
    assert "two-person rule" in str(exc.value)


def test_only_a_parked_approval_can_be_countersigned():
    d = decide(action="approve", actor_id=1, score=0.9, value=LOW,
               second_approval_value=1_000_000.0)
    with pytest.raises(ReviewError):
        countersign(d, actor_id=2)


def test_rejections_never_need_a_second_approver():
    for action in ("reject", "conditional"):
        d = decide(action=action, actor_id=1, score=0.5, value=HIGH,
                   second_approval_value=1_000_000.0)
        assert d.status == "applied"


def test_an_unknown_action_is_refused_rather_than_stored():
    with pytest.raises(ReviewError):
        decide(action="probably_fine", actor_id=1, score=0.9)


def test_a_decision_must_name_who_made_it():
    with pytest.raises(ReviewError):
        decide(action="approve", actor_id=None, score=0.9)


# --------------------------------------------------------------------------
# review: the frozen score
# --------------------------------------------------------------------------
def test_the_score_is_frozen_at_the_moment_of_the_decision():
    """Re-running the engine must not rewrite what a person signed against."""
    d = decide(action="approve", actor_id=1, score=0.9312, value=HIGH,
               second_approval_value=1_000_000.0)
    later = countersign(d, actor_id=2)
    assert later.score_at_decision == 0.9312 == d.score_at_decision
    assert withdraw(later, actor_id=3).score_at_decision == 0.9312


def test_countersigning_does_not_edit_the_original_decision():
    d = decide(action="approve", actor_id=1, score=0.9, value=HIGH,
               second_approval_value=1_000_000.0)
    countersign(d, actor_id=2)
    assert d.status == "awaiting_second"          # frozen dataclass, untouched


def test_the_countersigned_row_still_names_the_proposer():
    d = decide(action="approve", actor_id=1, score=0.9, value=HIGH,
               second_approval_value=1_000_000.0)
    out = countersign(d, actor_id=2)
    assert out.decided_by_id == 1
    assert "countersigned by user 2" in out.reason


# --------------------------------------------------------------------------
# review: value at stake
# --------------------------------------------------------------------------
def test_value_at_stake_uses_the_extract_never_an_estimate():
    a = {"qty": 100, "unit_value": 250.0}
    b = {"qty": 40, "unit_value": 250.0}
    assert value_at_stake(a, b) == 35_000.0


def test_a_record_missing_a_figure_contributes_nothing_rather_than_a_guess():
    assert value_at_stake({"qty": 100}, {"qty": 5, "unit_value": 2.0}) == 10.0
    assert value_at_stake(None, None) == 0.0


# --------------------------------------------------------------------------
# grouping: the pairwise case
# --------------------------------------------------------------------------
BOLT12 = {"thread": "M12", "length_mm": "50"}
BOLT16 = {"thread": "M16", "length_mm": "50"}
TRUNCATED = {}                                    # MAKTX cut the specs off


def test_agreeing_records_form_one_group():
    r = group([ApprovedEdge(1, 2, 0.95)], {1: BOLT12, 2: dict(BOLT12)})
    assert len(r.groups) == 1
    assert r.groups[0].members == (1, 2)
    assert not r.blocked


def test_a_directly_conflicting_edge_is_blocked():
    r = group([ApprovedEdge(1, 2, 0.95)], {1: BOLT12, 2: BOLT16})
    assert r.blocked and r.blocked[0].conflicts == ("thread",)
    assert len(r.groups) == 2                     # they stay separate


def test_unknown_never_conflicts():
    assert conflicts_between(BOLT12, TRUNCATED) == ()


# --------------------------------------------------------------------------
# grouping: THE case
# --------------------------------------------------------------------------
def test_transitive_closure_cannot_smuggle_a_conflict_into_a_group():
    """1 --- 3 --- 2, where 3 is unreadable and 1 and 2 contradict each other.

    Every pair is individually fine: an unreadable spec is UNKNOWN and UNKNOWN
    never vetoes. The union is a national code containing both an M12 and an
    M16 bolt. This is the defect that made group-level profiles necessary.
    """
    edges = [ApprovedEdge(1, 3, 0.95), ApprovedEdge(3, 2, 0.94)]
    attrs = {1: BOLT12, 3: TRUNCATED, 2: BOLT16}

    # both pairs pass a pairwise check
    assert conflicts_between(attrs[1], attrs[3]) == ()
    assert conflicts_between(attrs[3], attrs[2]) == ()

    r = group(edges, attrs)
    assert len(r.blocked) == 1
    assert r.blocked[0].conflicts == ("thread",)
    assert "the union is not" in r.blocked[0].reason

    merged = [g for g in r.groups if len(g.members) > 1]
    assert len(merged) == 1
    assert set(merged[0].members) == {1, 3}       # the stronger edge held
    assert merged[0].profile["thread"] == "M12"


def test_the_weaker_approval_is_the_one_refused_deterministically():
    attrs = {1: BOLT12, 3: TRUNCATED, 2: BOLT16}
    strong_first = group([ApprovedEdge(1, 3, 0.99), ApprovedEdge(3, 2, 0.80)], attrs)
    weak_first = group([ApprovedEdge(3, 2, 0.80), ApprovedEdge(1, 3, 0.99)], attrs)
    assert strong_first.blocked[0].edge.key == weak_first.blocked[0].edge.key == (2, 3)


def test_grouping_is_order_independent():
    attrs = {1: BOLT12, 2: dict(BOLT12), 3: dict(BOLT12)}
    a = group([ApprovedEdge(1, 2, 0.9), ApprovedEdge(2, 3, 0.8)], attrs)
    b = group([ApprovedEdge(2, 3, 0.8), ApprovedEdge(1, 2, 0.9)], attrs)
    assert [g.members for g in a.groups] == [g.members for g in b.groups]


def test_a_group_profile_consolidates_what_each_member_contributed():
    attrs = {1: {"thread": "M12"}, 2: {"length_mm": "50"}, 3: {"material_grade": "SS304"}}
    r = group([ApprovedEdge(1, 2, 0.9), ApprovedEdge(2, 3, 0.9)], attrs)
    assert r.groups[0].profile == {"thread": "M12", "length_mm": "50",
                                   "material_grade": "SS304"}


def test_the_canonical_member_is_the_least_degraded_row():
    attrs = {1: TRUNCATED, 2: {"thread": "M12", "length_mm": "50"}}
    r = group([ApprovedEdge(1, 2, 0.9)], attrs)
    assert r.groups[0].canonical == 2


def test_a_blocked_edge_is_returned_not_discarded():
    r = group([ApprovedEdge(1, 2, 0.95, review_id=77)], {1: BOLT12, 2: BOLT16})
    assert r.blocked[0].edge.review_id == 77       # the console can show the steward


# --------------------------------------------------------------------------
# audit
# --------------------------------------------------------------------------
def test_an_audit_row_carries_the_frozen_score_not_a_recomputed_one():
    d = decide(action="approve", actor_id=1, score=0.8812, value=LOW,
               second_approval_value=1_000_000.0)
    row = for_decision(d, match_id=5, actor_username="steward",
                       record_a_id=1, record_b_id=2)
    assert row.score_at_event == 0.8812
    assert row.action == "review.approve.applied"


def test_before_and_after_state_say_what_changed():
    row = event("grouping.merge", before_members=[1], after_members=[1, 2, 3])
    assert row.before_state == "group of 1: 1"
    assert row.after_state == "group of 3: 1, 2, 3"


def test_a_refused_approval_is_audited_as_loudly_as_an_accepted_one():
    r = group([ApprovedEdge(1, 2, 0.95, review_id=9)], {1: BOLT12, 2: BOLT16})
    row = for_blocked_edge(r.blocked[0], actor_id=3, actor_username="steward")
    assert row.action == "grouping.edge_blocked"
    assert row.payload["conflicts"] == ["thread"]
    assert row.record_a_id == 1 and row.record_b_id == 2


def test_the_audit_module_offers_no_way_to_edit_an_event():
    """Append-only is a property of the API surface, not just of intent."""
    import app.workflow.audit as audit
    forbidden = {"update", "amend", "correct", "edit", "delete", "redact"}
    assert not forbidden & {n for n in dir(audit) if not n.startswith("_")}


def test_an_event_must_name_an_action():
    with pytest.raises(ValueError):
        event("")
