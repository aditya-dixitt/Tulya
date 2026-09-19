"""Procurement opportunities and cross-CPSE impact scenarios.

Every row in both tables carries a `provenance` column and a `basis` string,
and the API refuses to serialise either without them. The reason is blunt: the
quantities in this project come from a synthetic benchmark dataset, not from a
CPSE's ERP. They are useful for showing what harmonised identity *would* let a
procurement team see, and they are worthless — worse than worthless — if anyone
quotes them as a measured saving.

`basis` is free text that must say, in words a non-technical reader can check,
where the number came from. It is rendered next to the number in the UI.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class ProcurementOpportunity(Base, TimestampMixin):
    """An open demand that a harmonised identity says could be met elsewhere."""

    __tablename__ = "procurement_opportunities"
    __table_args__ = (
        CheckConstraint(
            "provenance IN ('MEASURED','DERIVED','SIMULATED')", name="provenance_known"
        ),
        CheckConstraint(
            "signal IN ('CROSS_CPSE_STOCK_FOUND','DEMAND_AGGREGATION_CANDIDATE',"
            "'OPPORTUNITY_DETECTED','NO_CROSS_CPSE_STOCK','UNRESOLVED_CASE')",
            name="signal_known",
        ),
        CheckConstraint("coverage >= 0 AND coverage <= 1", name="coverage_range"),
        Index("ix_proc_signal_coverage", "signal", "coverage"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_identities.id", ondelete="CASCADE"), index=True
    )
    code_id: Mapped[int | None] = mapped_column(
        ForeignKey("national_material_codes.id", ondelete="SET NULL")
    )
    requesting_cpse_id: Mapped[int] = mapped_column(ForeignKey("cpses.id"), index=True)
    required_qty: Mapped[float] = mapped_column(Float)
    available_qty: Mapped[float] = mapped_column(Float, default=0.0)
    best_source_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_records.id", ondelete="SET NULL")
    )
    coverage: Mapped[float] = mapped_column(Float, default=0.0)
    signal: Mapped[str] = mapped_column(String(40), index=True)
    scope: Mapped[str | None] = mapped_column(String(12))  # INTRA / INTER
    standards_status: Mapped[str | None] = mapped_column(String(32))
    review_status: Mapped[str | None] = mapped_column(String(16))

    provenance: Mapped[str] = mapped_column(String(16), default="SIMULATED")
    basis: Mapped[str] = mapped_column(Text)

    identity = relationship("MaterialIdentity")
    code = relationship("NationalMaterialCode")
    requesting_cpse = relationship("Cpse")
    best_source_record = relationship("MaterialRecord")


class ImpactScenario(Base, TimestampMixin):
    """A saved cross-CPSE harmonisation scenario and its computed outputs."""

    __tablename__ = "impact_scenarios"
    __table_args__ = (
        CheckConstraint(
            "provenance IN ('MEASURED','DERIVED','SIMULATED')", name="provenance_known"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    identity_id: Mapped[int] = mapped_column(
        ForeignKey("material_identities.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    label: Mapped[str | None] = mapped_column(String(160))

    # inputs
    participating_cpse_ids: Mapped[list] = mapped_column(JSONB)
    demand_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    required_qty: Mapped[float] = mapped_column(Float)

    # outputs
    combined_stock: Mapped[float] = mapped_column(Float)
    coverage: Mapped[float] = mapped_column(Float)
    surplus: Mapped[float] = mapped_column(Float)
    procurement_requirement: Mapped[float] = mapped_column(Float)
    legacy_codes_consolidated: Mapped[int] = mapped_column(Integer)
    aggregation_opportunity: Mapped[bool] = mapped_column(default=False)
    outputs: Mapped[dict] = mapped_column(JSONB, server_default="{}")

    provenance: Mapped[str] = mapped_column(String(16), default="SIMULATED")
    basis: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    identity = relationship("MaterialIdentity")
    created_by = relationship("User")
