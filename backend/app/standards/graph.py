"""The standards knowledge graph, as decision logic.

Two records cite different standards. Does that help, hurt, or neither?

The graph answers with one of four effects, and the constraint that shapes all
of them is the same one Phase 4 established for the LLM, stated here for
standards evidence:

    **External evidence may block a merge. It may never authorise one.**

A CONFLICT edge between two cited standards is allowed to stop a pair outright,
because being wrong in that direction costs a steward one review. An
EQUIVALENT edge is never allowed to clear a hard-key veto, raise a score, or
turn a REVIEW into an AUTO_SUGGEST — because being wrong in *that* direction
merges an M12 bolt into an M16 bolt on the strength of a table someone typed.

`apply()` enforces it mechanically rather than by convention: decisions are
ranked by restrictiveness and the function cannot return a rank lower than the
one it was given. `test_standards.py` asserts that over every combination.

The second rule comes from the schema: **a relationship without a source is not
a fact.** `verified_needs_source` is a CHECK constraint on the table; here it
means only VERIFIED and in-scope SCOPED edges may SUPPORT. Everything else can
INFORM a human and nothing more.

Pure module: no database, no network, no model.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# --- effects ---------------------------------------------------------------
BLOCKS = "BLOCKS"      # a cited standard conflicts — stop the pair
SUPPORTS = "SUPPORTS"  # sourced, in-scope equivalence — show the steward
INFORMS = "INFORMS"    # an edge exists but is unsourced or out of scope
NONE = "NONE"          # nothing in the graph connects these standards

# --- vocabulary mirrored from models/standards.py CHECK constraints ---------
RELATIONSHIPS = ("EQUIVALENT", "SUPERSET", "SUBSTITUTE", "CONFLICT", "RELATED")
VERIFICATIONS = ("VERIFIED", "SCOPED", "REQUIRES_REVIEW", "UNVERIFIED")
_SUPPORTING = {"EQUIVALENT", "SUPERSET", "SUBSTITUTE"}
_SOURCED = {"VERIFIED", "SCOPED"}

# How restrictive a pipeline decision is. `apply` may raise this rank, never
# lower it. REJECTED_STANDARD sits with the veto: both mean "not this pair".
RANK = {
    "AUTO_SUGGEST": 0,
    "REVIEW": 1,
    "DISCARD": 2,
    "REJECTED_VETO": 3,
    "REJECTED_STANDARD": 3,
}


@dataclass(frozen=True)
class Edge:
    """One row of standard_relationships, flattened for decision-making."""

    source_standard: str
    target_standard: str
    relationship: str
    verification: str = "REQUIRES_REVIEW"
    scope: str | None = None
    scoped_attributes: tuple[str, ...] = ()
    citation: str | None = None
    relationship_id: int | None = None

    @property
    def sourced(self) -> bool:
        """The schema's rule, restated: VERIFIED without a citation is impossible."""
        return self.verification in _SOURCED and bool(self.citation)

    def covers(self, attributes) -> bool:
        """Is this edge in scope for the attributes actually in question?

        An unscoped edge covers everything. A scoped one covers only what it
        names — "equivalent for bore and wall class" says nothing about thread.
        """
        if not self.scoped_attributes:
            return True
        if not attributes:
            return False        # scoped edge, nothing to scope it against
        return set(attributes).issubset(set(self.scoped_attributes))

    def as_dict(self) -> dict:
        return {"source_standard": self.source_standard,
                "target_standard": self.target_standard,
                "relationship": self.relationship, "verification": self.verification,
                "scope": self.scope, "scoped_attributes": list(self.scoped_attributes),
                "citation": self.citation, "relationship_id": self.relationship_id}


@dataclass(frozen=True)
class Finding:
    effect: str
    reason: str
    edges: tuple[Edge, ...] = ()
    citations: tuple[str, ...] = field(default=())

    @property
    def citable(self) -> bool:
        return bool(self.citations)

    def as_dict(self) -> dict:
        return {"effect": self.effect, "reason": self.reason,
                "citable": self.citable, "citations": list(self.citations),
                "edges": [e.as_dict() for e in self.edges]}


def assess(edges, *, attributes=()) -> Finding:
    """What the graph has to say about a pair citing these standards.

    `attributes` are the specifications actually in question — the contested or
    unreadable ones. A scoped edge is only allowed to speak about those.
    """
    edges = tuple(edges or ())
    if not edges:
        return Finding(NONE, "no relationship recorded between the cited standards")

    conflicts = [e for e in edges if e.relationship == "CONFLICT"]
    if conflicts:
        e = conflicts[0]
        qualifier = "" if e.sourced else " (unsourced — recorded as a caution, not a fact)"
        return Finding(
            BLOCKS,
            f"{e.source_standard} and {e.target_standard} are recorded as CONFLICT"
            f"{qualifier}",
            edges=tuple(conflicts),
            citations=tuple(c.citation for c in conflicts if c.citation),
        )

    supporting = [e for e in edges
                  if e.relationship in _SUPPORTING and e.sourced and e.covers(attributes)]
    if supporting:
        e = supporting[0]
        scope = f" for {', '.join(e.scoped_attributes)}" if e.scoped_attributes else ""
        return Finding(
            SUPPORTS,
            f"{e.source_standard} is recorded {e.relationship} to {e.target_standard}"
            f"{scope}, cited to {e.citation}",
            edges=tuple(supporting),
            citations=tuple(s.citation for s in supporting if s.citation),
        )

    # Something is recorded, but it cannot carry weight. Say which of the two
    # reasons applies, because they call for different fixes.
    unsourced = [e for e in edges if e.relationship in _SUPPORTING and not e.sourced]
    out_of_scope = [e for e in edges
                    if e.relationship in _SUPPORTING and e.sourced and not e.covers(attributes)]
    if out_of_scope:
        e = out_of_scope[0]
        return Finding(
            INFORMS,
            f"{e.source_standard}/{e.target_standard} equivalence is scoped to "
            f"{', '.join(e.scoped_attributes)}, which does not cover "
            f"{', '.join(attributes) or 'the attributes in question'}",
            edges=tuple(out_of_scope), citations=tuple(
                s.citation for s in out_of_scope if s.citation),
        )
    if unsourced:
        e = unsourced[0]
        return Finding(
            INFORMS,
            f"{e.source_standard}/{e.target_standard} is recorded {e.relationship} but "
            f"is {e.verification} with no source — shown, not relied on",
            edges=tuple(unsourced),
        )
    return Finding(INFORMS,
                   "only RELATED edges connect the cited standards — context, not evidence",
                   edges=edges)


def apply(decision: str, finding: Finding) -> tuple[str, str]:
    """Fold a Finding into a pipeline decision. Returns (decision, reason).

    The invariant: `RANK[out] >= RANK[in]`, always. Standards evidence can make
    an outcome more restrictive and can never make it less. SUPPORTS therefore
    changes nothing about the decision — it attaches citations a steward reads,
    which is the whole of its job.
    """
    if decision not in RANK:
        raise ValueError(f"unknown decision {decision!r}")

    if finding.effect == BLOCKS:
        out = "REJECTED_STANDARD" if RANK[decision] < RANK["REJECTED_STANDARD"] else decision
        return out, finding.reason

    if finding.effect == SUPPORTS:
        return decision, (f"{finding.reason} — recorded as evidence; standards "
                          f"support does not change the decision")

    if finding.effect == INFORMS:
        return decision, finding.reason

    return decision, "no standards evidence"
