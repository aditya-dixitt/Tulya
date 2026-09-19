"""Reviews, the collaborative workflow, and the append-only audit trail.

Three rules this schema hard-codes, because they are the ones people work
around when they are only conventions:

  1. A high-value approval is *parked*, not applied. `status` starts as
     `awaiting_second` and only a different user can move it to `applied`.
  2. The countersigner may not be the proposer — enforced in the service and
     backed by `second_by <> decided_by` here.
  3. Audit rows are append-only. There is no update path in the repository and
     no ON UPDATE on this table.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Review(Base, TimestampMixin):
    """A steward's decision on one candidate pair."""

    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("match_id", name="uq_reviews_match_id"),
        CheckConstraint(
            "action IN ('approve','reject','conditional')", name="action_known"
        ),
        CheckConstraint(
            "status IN ('applied','awaiting_second','withdrawn')", name="status_known"
        ),
        # the two-person rule, at the storage layer
        CheckConstraint(
            "second_by_id IS NULL OR second_by_id <> decided_by_id",
            name="no_self_countersign",
        ),
        Index("ix_reviews_status_value", "status", "value_at_stake"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("material_matches.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(20), default="applied", index=True)
    decided_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    decided_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    note: Mapped[str | None] = mapped_column(Text)
    # the score at the moment of the decision, frozen. Re-running the engine
    # must not silently rewrite what a person was looking at when they signed.
    score_at_decision: Mapped[float | None] = mapped_column(Float)
    value_at_stake: Mapped[float] = mapped_column(Float, default=0.0)

    second_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    second_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    match = relationship("MaterialMatch")
    decided_by = relationship("User", foreign_keys=[decided_by_id])
    second_by = relationship("User", foreign_keys=[second_by_id])


class WorkflowCase(Base, TimestampMixin):
    """A material case moving AI -> steward -> engineering -> procurement -> governance."""

    __tablename__ = "workflow_cases"
    __table_args__ = (
        UniqueConstraint("match_id", name="uq_workflow_cases_match_id"),
        CheckConstraint(
            "stage IN ('AI','DATA_STEWARD','ENGINEERING','PROCUREMENT','FINAL_GOVERNANCE')",
            name="stage_known",
        ),
        Index("ix_workflow_cases_stage_state", "stage", "state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    case_ref: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("material_matches.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[str] = mapped_column(String(24), default="AI", index=True)
    state: Mapped[str] = mapped_column(String(20), default="open", index=True)
    assigned_steward_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    assigned_engineer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    procurement_state: Mapped[str | None] = mapped_column(String(40))
    escalated: Mapped[bool] = mapped_column(default=False)
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    match = relationship("MaterialMatch")
    assigned_steward = relationship("User", foreign_keys=[assigned_steward_id])
    assigned_engineer = relationship("User", foreign_keys=[assigned_engineer_id])
    events: Mapped[list["WorkflowEvent"]] = relationship(
        back_populates="case", cascade="all, delete-orphan",
        order_by="WorkflowEvent.id",
    )
    comments: Mapped[list["WorkflowComment"]] = relationship(
        back_populates="case", cascade="all, delete-orphan",
        order_by="WorkflowComment.id",
    )


class WorkflowEvent(Base):
    """Stage transitions and requests. Append-only, like the audit log."""

    __tablename__ = "workflow_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_cases.id", ondelete="CASCADE"), index=True
    )
    at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    from_stage: Mapped[str | None] = mapped_column(String(24))
    to_stage: Mapped[str | None] = mapped_column(String(24))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    detail: Mapped[str | None] = mapped_column(Text)

    case: Mapped["WorkflowCase"] = relationship(back_populates="events")
    actor = relationship("User")


class WorkflowComment(Base):
    __tablename__ = "workflow_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_cases.id", ondelete="CASCADE"), index=True
    )
    at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)

    case: Mapped["WorkflowCase"] = relationship(back_populates="comments")
    author = relationship("User")


class AuditEvent(Base):
    """Append-only. No update path exists anywhere in the application."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_at_action", "at", "action"),
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    action: Mapped[str] = mapped_column(String(48), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    actor_username: Mapped[str | None] = mapped_column(String(64))
    record_a_id: Mapped[int | None] = mapped_column(Integer)
    record_b_id: Mapped[int | None] = mapped_column(Integer)
    score_at_event: Mapped[float | None] = mapped_column(Float)
    before_state: Mapped[str | None] = mapped_column(Text)
    after_state: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(40), index=True)
    payload: Mapped[dict | None] = mapped_column(JSONB)

    actor = relationship("User")
