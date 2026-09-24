"""The only module in `standards/` that touches the database.

Everything else is pure so it can be tested without PostgreSQL, which is why
the decision rules in `graph.py` have tests that run anywhere. This file is the
seam: it turns rows into the plain dataclasses those rules operate on, and
writes evidence back.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession, selectinload

from ..models import (
    Standard, StandardDesignation, StandardEvidence, StandardRelationship,
    StandardTextChunk,
)
from .designations import keys as designation_keys
from .graph import Edge
from .retrieval import Chunk


def standards_in_text(db: DbSession, text: str) -> list[Standard]:
    """Standards whose designation appears in `text`.

    Matching is on the canonical key, so "IS 1367 PT-3", "IS:1367 Part 3" and
    "is1367part3" all resolve to the same row — and a designation that is not
    on file resolves to nothing rather than to a guess.
    """
    ks = designation_keys(text)
    if not ks:
        return []
    return list(db.execute(
        select(Standard)
        .join(StandardDesignation, StandardDesignation.standard_id == Standard.id)
        .where(StandardDesignation.normalised.in_(ks))
        .options(selectinload(Standard.source))
        .distinct()
    ).scalars().all())


def edges_between(db: DbSession, a_ids, b_ids) -> list[Edge]:
    """Relationship edges connecting the two sets, in either direction.

    Edges are stored once with a direction; equivalence is symmetric in meaning,
    so both orientations are queried and the result is flattened to the plain
    Edge dataclass the graph rules take.
    """
    a_ids, b_ids = list(a_ids or []), list(b_ids or [])
    if not a_ids or not b_ids:
        return []
    rows = db.execute(
        select(StandardRelationship)
        .options(selectinload(StandardRelationship.source_standard),
                 selectinload(StandardRelationship.target_standard),
                 selectinload(StandardRelationship.source))
        .where(
            (StandardRelationship.source_standard_id.in_(a_ids)
             & StandardRelationship.target_standard_id.in_(b_ids))
            | (StandardRelationship.source_standard_id.in_(b_ids)
               & StandardRelationship.target_standard_id.in_(a_ids))
        )
    ).scalars().all()

    return [
        Edge(
            source_standard=r.source_standard.code if r.source_standard else "?",
            target_standard=r.target_standard.code if r.target_standard else "?",
            relationship=r.relationship_,
            verification=r.verification,
            scope=r.scope,
            scoped_attributes=tuple(r.scoped_attributes or ()),
            citation=r.source.citation if r.source else None,
            relationship_id=r.id,
        )
        for r in rows
    ]


def load_chunks(db: DbSession, standard_ids=None) -> list[Chunk]:
    """Retrievable passages, optionally narrowed to particular standards."""
    stmt = (select(StandardTextChunk)
            .options(selectinload(StandardTextChunk.standard),
                     selectinload(StandardTextChunk.source))
            .order_by(StandardTextChunk.standard_id, StandardTextChunk.seq))
    if standard_ids:
        stmt = stmt.where(StandardTextChunk.standard_id.in_(list(standard_ids)))
    return [
        Chunk(
            id=c.id,
            standard_code=c.standard.code if c.standard else "?",
            text=c.text,
            heading=c.heading,
            citation=c.source.citation if c.source else None,
        )
        for c in db.execute(stmt).scalars().all()
    ]


def persist_evidence(db: DbSession, rows) -> list[StandardEvidence]:
    """Append evidence for a match. Never updates in place — the trail is a log."""
    made = [StandardEvidence(**r.as_dict()) for r in rows]
    db.add_all(made)
    db.flush()
    return made
