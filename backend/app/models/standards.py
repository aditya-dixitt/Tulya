"""The standards knowledge graph, as a real relational model.

The rule this schema exists to enforce: **a relationship without a source is
not a fact.** `verification` and `source_id` are both required on every edge,
and the only value that may claim VERIFIED is one that cites a StandardSource.
Everything else is REQUIRES_REVIEW and the UI must render it that way.

StandardTextChunk holds the retrievable evidence for the RAG path: chunked
standard text with its embedding kept in a FAISS index on disk (the id column
is the index's row label). The LLM may summarise what comes back from that
retrieval; it may never overturn a deterministic attribute conflict.
"""
from __future__ import annotations

from sqlalchemy import (
    CheckConstraint, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class StandardSource(Base, TimestampMixin):
    """Where a claim about a standard came from. No source, no VERIFIED."""

    __tablename__ = "standard_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    citation: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32))  # STANDARD_TEXT / GOVERNMENT / VENDOR
    url: Mapped[str | None] = mapped_column(String(500))
    retrieved_at: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)


class Standard(Base, TimestampMixin):
    __tablename__ = "standards"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    body: Mapped[str] = mapped_column(String(32))  # BIS / BSI / ASTM / JIS / ISO / API
    title: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)
    family: Mapped[str | None] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE")  # or WITHDRAWN
    superseded_by_id: Mapped[int | None] = mapped_column(ForeignKey("standards.id"))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("standard_sources.id"))
    provenance: Mapped[str] = mapped_column(String(16), default="VERIFIED")

    designations: Mapped[list["StandardDesignation"]] = relationship(
        back_populates="standard", cascade="all, delete-orphan"
    )
    source = relationship("StandardSource")


class StandardDesignation(Base, TimestampMixin):
    """The spellings a standard appears under in real material descriptions."""

    __tablename__ = "standard_designations"
    __table_args__ = (
        UniqueConstraint("designation", name="uq_standard_designations_designation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    standard_id: Mapped[int] = mapped_column(
        ForeignKey("standards.id", ondelete="CASCADE"), index=True
    )
    designation: Mapped[str] = mapped_column(String(80), index=True)
    normalised: Mapped[str] = mapped_column(String(80), index=True)

    standard: Mapped["Standard"] = relationship(back_populates="designations")


class StandardRelationship(Base, TimestampMixin):
    """A typed, scoped, sourced edge between two standards."""

    __tablename__ = "standard_relationships"
    __table_args__ = (
        UniqueConstraint(
            "source_standard_id", "target_standard_id", "relationship",
            name="uq_standard_relationships_source_standard_id",
        ),
        CheckConstraint(
            "relationship IN ('EQUIVALENT','SUPERSET','SUBSTITUTE','CONFLICT','RELATED')",
            name="relationship_known",
        ),
        CheckConstraint(
            "verification IN ('VERIFIED','SCOPED','REQUIRES_REVIEW','UNVERIFIED')",
            name="verification_known",
        ),
        # The schema-level expression of "no source, no fact".
        CheckConstraint(
            "verification <> 'VERIFIED' OR source_id IS NOT NULL",
            name="verified_needs_source",
        ),
        CheckConstraint(
            "source_standard_id <> target_standard_id", name="no_self_edge"
        ),
        Index("ix_standard_relationships_pair", "source_standard_id", "target_standard_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_standard_id: Mapped[int] = mapped_column(
        ForeignKey("standards.id", ondelete="CASCADE"), index=True
    )
    target_standard_id: Mapped[int] = mapped_column(
        ForeignKey("standards.id", ondelete="CASCADE"), index=True
    )
    relationship_: Mapped[str] = mapped_column("relationship", String(24))
    scope: Mapped[str | None] = mapped_column(Text)
    verification: Mapped[str] = mapped_column(String(24), default="REQUIRES_REVIEW")
    source_id: Mapped[int | None] = mapped_column(ForeignKey("standard_sources.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    # which attributes this relationship is scoped to (e.g. bore, wall class)
    scoped_attributes: Mapped[list | None] = mapped_column(JSONB)

    source_standard = relationship("Standard", foreign_keys=[source_standard_id])
    target_standard = relationship("Standard", foreign_keys=[target_standard_id])
    source = relationship("StandardSource")


class StandardTextChunk(Base, TimestampMixin):
    """Retrievable evidence. The FAISS row label is this row's id."""

    __tablename__ = "standard_text_chunks"
    __table_args__ = (Index("ix_standard_text_chunks_std_seq", "standard_id", "seq"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    standard_id: Mapped[int] = mapped_column(
        ForeignKey("standards.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str | None] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("standard_sources.id"))
    embedded: Mapped[bool] = mapped_column(default=False)

    standard = relationship("Standard")
    source = relationship("StandardSource")


class StandardEvidence(Base, TimestampMixin):
    """Evidence attached to a specific match: what was retrieved and why."""

    __tablename__ = "standard_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("material_matches.id", ondelete="CASCADE"), index=True
    )
    relationship_id: Mapped[int | None] = mapped_column(
        ForeignKey("standard_relationships.id", ondelete="SET NULL")
    )
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("standard_text_chunks.id", ondelete="SET NULL")
    )
    retrieval_score: Mapped[float | None] = mapped_column(Float)
    verdict: Mapped[str] = mapped_column(String(24), default="REQUIRES_REVIEW")
    summary: Mapped[str | None] = mapped_column(Text)
    # true when the summary text was produced by the local LLM rather than a rule
    summary_from_llm: Mapped[bool] = mapped_column(default=False)
    provenance: Mapped[str] = mapped_column(String(16), default="DERIVED")

    relationship_row = relationship("StandardRelationship")
    chunk = relationship("StandardTextChunk")
