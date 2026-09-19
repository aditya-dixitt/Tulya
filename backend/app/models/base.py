"""Declarative base and shared column conventions."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Explicit constraint naming so Alembic can autogenerate reversible migrations
# instead of emitting unnamed constraints Postgres will not let it drop later.
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Provenance is a first-class column type in TULYA, not a UI decoration.
# Every number a steward or an auditor sees must be able to say where it came
# from, and the database is the only place that can guarantee it.
# ---------------------------------------------------------------------------
PROVENANCE_VALUES = (
    "MEASURED",      # produced by the pipeline from source records
    "DERIVED",       # computed deterministically from measured values
    "SIMULATED",     # generated for demonstration; not a measured CPSE result
    "PROPOSED",      # asserted by the engine, not yet governed
    "VERIFIED",      # confirmed against a cited source by a human
    "UNKNOWN",       # not readable / not on file
    "PLANNED",       # designed but not implemented or not yet validated
)

EQUIVALENCE_VALUES = (
    "IDENTICAL", "EQUIVALENT", "CONDITIONAL", "DIFFERENT", "CONFLICT", "UNRESOLVED",
)

DECISION_VALUES = ("AUTO_SUGGEST", "REVIEW", "DISCARD", "REJECTED_VETO")

ROLE_VALUES = ("viewer", "steward", "approver", "admin")

WORKFLOW_STAGES = ("AI", "DATA_STEWARD", "ENGINEERING", "PROCUREMENT", "FINAL_GOVERNANCE")

RELATIONSHIP_VALUES = ("EQUIVALENT", "SUPERSET", "SUBSTITUTE", "CONFLICT", "RELATED")

VERIFICATION_VALUES = ("VERIFIED", "SCOPED", "REQUIRES_REVIEW", "UNVERIFIED")
