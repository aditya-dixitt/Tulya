"""Approved pairs into golden records, with the veto enforced at group level.

A group exists only because a person approved every edge in it. This module
answers "given the approvals so far, what does the catalogue look like".

    Why this is not just a union-find
    ---------------------------------
    **Transitive closure defeats a pairwise veto.**

    The hard-key veto compares two records. Union-find joins whole components.
    A record whose specification was destroyed — a description truncated at
    SAP's 40-character MAKTX limit, say — conflicts with nobody, because an
    unreadable key is UNKNOWN and UNKNOWN never vetoes. It can therefore pair
    legitimately with a 1-inch gasket and, separately, with an 18-inch gasket.
    Neither pair is wrong. Their union is very wrong, and no pairwise check
    anywhere in the system is looking at it.

    Measured on the prototype's ERP round trip before the fix: 21 of 516
    golden records (4.1%) held at least one pair of members that directly
    contradicted each other on a hard key — bores of 1", 2.5", 5" and 18"
    inside a single national code. Catalogue-corrupting, and invisible at pair
    level because every individual pair passed.

So each group carries a **consolidated specification profile**, and an edge
that would merge two profiles disagreeing on a hard key is refused. The
approval is not discarded — it comes back as a `BlockedEdge` naming the
conflict, for the console to show the steward who made it. A system declining
an instruction it can prove is unsafe, and saying exactly why, is better
behaviour than either silently obeying or silently dropping it.

Edges are applied strongest-evidence-first, so when two approvals cannot both
hold, the one refused is the weaker one — deterministically, whatever order the
reviews arrived in.

Pure module: no database, no network, no model.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..matching.attributes import HARD_KEYS


@dataclass(frozen=True)
class ApprovedEdge:
    """One steward-approved pair. `score` is the frozen score_at_decision."""

    a: int
    b: int
    score: float | None = None
    review_id: int | None = None

    @property
    def key(self) -> tuple[int, int]:
        return (min(self.a, self.b), max(self.a, self.b))


@dataclass(frozen=True)
class BlockedEdge:
    edge: ApprovedEdge
    conflicts: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict:
        return {"a": self.edge.a, "b": self.edge.b, "review_id": self.edge.review_id,
                "conflicts": list(self.conflicts), "reason": self.reason}


@dataclass(frozen=True)
class Group:
    members: tuple[int, ...]
    profile: dict = field(default_factory=dict)
    canonical: int | None = None

    def as_dict(self) -> dict:
        return {"members": list(self.members), "profile": dict(self.profile),
                "canonical": self.canonical, "member_count": len(self.members)}


@dataclass(frozen=True)
class GroupingResult:
    groups: tuple[Group, ...]
    blocked: tuple[BlockedEdge, ...]

    def as_dict(self) -> dict:
        return {"groups": [g.as_dict() for g in self.groups],
                "blocked": [b.as_dict() for b in self.blocked],
                "group_count": len(self.groups), "blocked_count": len(self.blocked)}


class UnionFind:
    def __init__(self):
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:           # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        # lowest id wins, so the same approvals always produce the same roots
        self.parent[max(ra, rb)] = min(ra, rb)
        return True


def conflicts_between(pa: dict, pb: dict) -> tuple[str, ...]:
    """Hard keys known in both profiles that disagree. UNKNOWN never conflicts."""
    return tuple(k for k in HARD_KEYS
                 if k in pa and k in pb and pa[k] is not None and pb[k] is not None
                 and pa[k] != pb[k])


def _merge(pa: dict, pb: dict) -> dict:
    """Union of two agreeing profiles. Callers check conflicts first."""
    out = dict(pa)
    for k, v in pb.items():
        out.setdefault(k, v)
    return out


def _canonical(members, attrs_by_record) -> int:
    """The member whose description states the most hard keys, ties by lowest id.

    The canonical record is what a national code's description is written from,
    so it should be the least degraded row in the group, not an arbitrary one.
    """
    def readable(rid):
        a = attrs_by_record.get(rid) or {}
        return sum(1 for k in HARD_KEYS if a.get(k) is not None)
    return min(members, key=lambda r: (-readable(r), r))


def group(edges, attrs_by_record) -> GroupingResult:
    """Fold approved edges into groups, refusing any that would corrupt a profile.

    `attrs_by_record` maps record id -> the extracted specification dict.
    Records with no entry are treated as having no readable specification,
    which is exactly the degraded case that motivates this module.
    """
    edges = list(edges or [])
    attrs_by_record = dict(attrs_by_record or {})

    # strongest evidence first; the id tie-break keeps it deterministic when
    # scores are equal or missing
    ordered = sorted(
        edges,
        key=lambda e: (-(e.score if e.score is not None else -1.0), e.key),
    )

    uf = UnionFind()
    profiles: dict[int, dict] = {}
    blocked: list[BlockedEdge] = []

    def profile_of(rid: int) -> dict:
        root = uf.find(rid)
        if root not in profiles:
            profiles[root] = dict(attrs_by_record.get(root) or {})
        return profiles[root]

    for e in ordered:
        # seed both singletons before touching either root
        for rid in (e.a, e.b):
            uf.find(rid)
            profiles.setdefault(rid, dict(attrs_by_record.get(rid) or {}))

        ra, rb = uf.find(e.a), uf.find(e.b)
        if ra == rb:
            continue                                  # already one group

        pa, pb = profile_of(e.a), profile_of(e.b)
        clash = conflicts_between(pa, pb)
        if clash:
            detail = ", ".join(f"{k}: {pa[k]} vs {pb[k]}" for k in clash)
            blocked.append(BlockedEdge(
                edge=e, conflicts=clash,
                reason=(f"approving {e.a}-{e.b} would merge two groups that "
                        f"disagree on {detail}; the pair itself is consistent, "
                        f"the union is not"),
            ))
            continue

        merged = _merge(pa, pb)
        uf.union(e.a, e.b)
        root = uf.find(e.a)
        for old in (ra, rb):
            profiles.pop(old, None)
        profiles[root] = merged

    # collect members per root, including singletons that only appear in edges
    seen: dict[int, list[int]] = {}
    for rid in sorted(set(list(uf.parent) + [r for e in edges for r in (e.a, e.b)])):
        seen.setdefault(uf.find(rid), []).append(rid)

    groups = tuple(
        Group(members=tuple(sorted(m)),
              profile=profiles.get(root, dict(attrs_by_record.get(root) or {})),
              canonical=_canonical(m, attrs_by_record))
        for root, m in sorted(seen.items())
    )
    return GroupingResult(groups=groups, blocked=tuple(blocked))
