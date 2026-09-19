"""Scored candidate pairs and the engineering evidence behind each one.

`MaterialMatch` stores what the deterministic pipeline concluded; it is never
written by a human. Human decisions live in `reviews` and never overwrite the
engine's opinion — an auditor has to be able to see that a steward approved a
pair the engine had only sent to review, and that is impossible if the two
share a column.
"""
from __future__ import annotations

from sqlalchemy import (
    CheckConstraint, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class MaterialMatch(Base, TimestampMixin):
    __tablename__ = "material_matches"
    __table_args__ = (
        UniqueConstraint("record_a_id", "record_b_id", name="uq_material_matches_record_a_id"),
        # pairs are unordered; the lower id is always stored first
        CheckConstraint("record_a_id < record_b_id", name="ordered_pair"),
        CheckConstraint(
            "decision IN ('AUTO_SUGGEST','REVIEW','DISCARD','REJECTED_VETO')",
            name="decision_known",
        ),
        CheckConstraint(
            "equivalence_status IN ('IDENTICAL','EQUIVALENT','CONDITIONAL',"
            "'DIFFERENT','CONFLICT','UNRESOLVED')",
            name="equivalence_known",
        ),
        Index("ix_material_matches_decision_score", "decision", "score"),
        Index("ix_material_matches_priority", "priority_band", "priority_total"),
        Index("ix_material_matches_scope", "scope"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    record_a_id: Mapped[int] = mapped_column(
        ForeignKey("material_records.id", ondelete="CASCADE"), index=True
    )
    record_b_id: Mapped[int] = mapped_column(
        ForeignKey("material_records.id", ondelete="CASCADE"), index=True
    )

    # ---- signals, exactly as the engine produced them --------------------
    cosine: Mapped[float] = mapped_column(Float)
    fuzzy: Mapped[float] = mapped_column(Float)
    attribute_agreement: Mapped[float | None] = mapped_column(Float)
    coverage: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, index=True)
    # what fusion alone would have said with the veto switched off — this is
    # what makes the veto's contribution measurable rather than asserted
    score_without_veto: Mapped[float | None] = mapped_column(Float)

    decision: Mapped[str] = mapped_column(String(20), index=True)
    equivalence_status: Mapped[str] = mapped_column(String(16), default="UNRESOLVED")
    vetoed: Mapped[bool] = mapped_column(default=False, index=True)
    capped_by_coverage: Mapped[bool] = mapped_column(default=False)
    reason: Mapped[str | None] = mapped_column(Text)
    conflicts: Mapped[list | None] = mapped_column(JSONB)

    scope: Mapped[str | None] = mapped_column(String(12))  # INTRA / INTER
    same_plant: Mapped[bool] = mapped_column(default=False)

    # steward-attention ranking, recomputed by the engine not the browser
    priority_uncertainty: Mapped[float | None] = mapped_column(Float)
    priority_thin_evidence: Mapped[float | None] = mapped_column(Float)
    priority_value_at_stake: Mapped[float | None] = mapped_column(Float)
    priority_total: Mapped[float | None] = mapped_column(Float)
    priority_band: Mapped[str | None] = mapped_column(String(12), index=True)

    # which backends produced this row — so a result can never be quoted
    # against an algorithm that did not compute it
    engine_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("engine_runs.id", ondelete="SET NULL"), index=True
    )

    record_a = relationship("MaterialRecord", foreign_keys=[record_a_id])
    record_b = relationship("MaterialRecord", foreign_keys=[record_b_id])
    evidence: Mapped[list["MatchEvidence"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    run = relationship("EngineRun")


class MatchEvidence(Base, TimestampMixin):
    """One attribute comparison. The veto is the sum of these, not a black box."""

    __tablename__ = "match_evidence"
    __table_args__ = (
        UniqueConstraint("match_id", "key", name="uq_match_evidence_match_id"),
        CheckConstraint(
            "verdict IN ('MATCH','MISMATCH','UNKNOWN','REVIEW_SCOPE')",
            name="verdict_known",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("material_matches.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(48))
    value_a: Mapped[str | None] = mapped_column(String(80))
    value_b: Mapped[str | None] = mapped_column(String(80))
    verdict: Mapped[str] = mapped_column(String(16))
    is_hard_key: Mapped[bool] = mapped_column(default=False)

    match: Mapped["MaterialMatch"] = relationship(back_populates="evidence")


class EngineRun(Base, TimestampMixin):
    """A pipeline execution and the exact backends that produced it.

    RESULTS.md is generated from these rows. It is the mechanism that stops a
    TF-IDF number being reported as a Sentence-BERT number.
    """

    __tablename__ = "engine_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    split: Mapped[str] = mapped_column(String(16), index=True)
    embedding_backend: Mapped[str] = mapped_column(String(32))
    embedding_model: Mapped[str | None] = mapped_column(String(160))
    embedding_dim: Mapped[int | None] = mapped_column(Integer)
    vector_index: Mapped[str] = mapped_column(String(32))
    fuzzy_backend: Mapped[str] = mapped_column(String(32))
    llm_extraction: Mapped[str | None] = mapped_column(String(64))
    weights: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    thresholds: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    record_count: Mapped[int | None] = mapped_column(Integer)
    candidate_pairs: Mapped[int | None] = mapped_column(Integer)
    all_pairs: Mapped[int | None] = mapped_column(Integer)
    reduction_ratio: Mapped[float | None] = mapped_column(Float)
    timings: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    decisions: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    app_version: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)
