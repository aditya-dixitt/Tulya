"""Steward decisions, grouping, and the audit trail.

Phase 6. Three pure modules:

    review      maker-checker: the two-person rule, high-value parking, and the
                score frozen at the moment a person signed
    grouping    approved pairs into golden records, with the hard-key veto
                enforced at GROUP level — a pairwise veto alone is not enough,
                because transitive closure defeats it
    audit       append-only event shaping; there is no update path, here or
                anywhere else in the application

The load-bearing idea is in `grouping`: two approvals that are each individually
correct can combine into a group that is wrong, and nothing at pair level is
looking at it. Read that module's docstring before changing it.
"""
from .audit import AuditRow, event, for_blocked_edge, for_decision  # noqa: F401
from .grouping import (  # noqa: F401
    ApprovedEdge, BlockedEdge, Group, GroupingResult, UnionFind,
    conflicts_between, group,
)
from .review import (  # noqa: F401
    ACTIONS, STATUSES, Decision, ReviewError, SelfCountersign, countersign,
    decide, is_edge_approved, value_at_stake, withdraw,
)
