"""Material records and the attributes recovered from their descriptions.

A *material_record* is one row as it exists in one CPSE's ERP: a legacy code, a
plant, a messy description, a quantity. TULYA never edits it.

A *material_attribute* is one specification the engine recovered from that
description. It is stored as a row rather than folded into a JSON blob because
the attribute's provenance — rule-extracted, LLM-extracted, or steward-verified
— is the thing the whole veto argument rests on, and a blob cannot be indexed,
constrained or audited per attribute.

The raw normalised payload still lands in a JSONB column alongside, because the
set of possible attribute keys is genuinely open-ended and a column per key
would be wrong.
"""
from __future__ import annotations

from sqlalchemy import (
    CheckConstraint, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class MaterialRecord(Base, TimestampMixin):
    """One row of one CPSE's material master. Read-only with respect to the ERP."""

    __tablename__ = "material_records"
    __table_args__ = (
        # NOT unique. The benchmark dataset reuses a legacy code across plants of
        # the same CPSE (4,480 such collisions, up to 8 rows deep), which is why
        # `resolve legacy code -> national code` returns a SET of candidates and
        # asks the steward which plant they mean, rather than a single row.
        Index("ix_material_records_cpse_legacy", "cpse_id", "legacy_code"),
        Index("ix_material_records_split_category", "split", "category"),
        Index("ix_material_records_plant", "plant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # the prototype's record_id, preserved so evaluation artefacts still line up
    source_record_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)

    cpse_id: Mapped[int] = mapped_column(ForeignKey("cpses.id"), index=True)
    plant_id: Mapped[int | None] = mapped_column(ForeignKey("plants.id"))
    legacy_code: Mapped[str] = mapped_column(String(64), index=True)

    description: Mapped[str] = mapped_column(Text)
    normalised_description: Mapped[str | None] = mapped_column(Text)
    uom: Mapped[str | None] = mapped_column(String(16))
    category: Mapped[str | None] = mapped_column(String(64), index=True)
    block_bucket: Mapped[str | None] = mapped_column(String(80))

    # quantity and unit value come from the source extract, not from a guess
    qty: Mapped[float | None] = mapped_column(Float)
    unit_value: Mapped[float | None] = mapped_column(Float)

    # evaluation bookkeeping — kept so the harness can still split correctly
    split: Mapped[str | None] = mapped_column(String(8), index=True)
    cluster_id: Mapped[int | None] = mapped_column(Integer, index=True)
    family_id: Mapped[int | None] = mapped_column(Integer)
    recipe: Mapped[str | None] = mapped_column(String(120))

    attrs_payload: Mapped[dict] = mapped_column(JSONB, server_default="{}")

    cpse = relationship("Cpse")
    plant = relationship("Plant")
    attributes: Mapped[list["MaterialAttribute"]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )

    @property
    def stock_value(self) -> float:
        return float(self.qty or 0) * float(self.unit_value or 0)


class MaterialAttribute(Base, TimestampMixin):
    """One recovered specification, with the provenance of how it was recovered."""

    __tablename__ = "material_attributes"
    __table_args__ = (
        UniqueConstraint("record_id", "key", name="uq_material_attributes_record_id"),
        CheckConstraint(
            "source IN ('RULE','LLM','STEWARD','ERP')",
            name="source_known",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        Index("ix_material_attributes_key_value", "key", "value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("material_records.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(48))
    value: Mapped[str] = mapped_column(String(80))
    # HARD_KEYS participate in the veto; everything else is descriptive only
    is_hard_key: Mapped[bool] = mapped_column(default=False)
    source: Mapped[str] = mapped_column(String(12), default="RULE")
    confidence: Mapped[float | None] = mapped_column(Float)
    provenance: Mapped[str] = mapped_column(String(16), default="MEASURED")

    record: Mapped["MaterialRecord"] = relationship(back_populates="attributes")


class MaterialIdentity(Base, TimestampMixin):
    """A governed identity: the set of legacy records agreed to be one item.

    This is the golden record. It exists only because a steward approved every
    edge that formed it, and it is what a CNMC is minted against.
    """

    __tablename__ = "material_identities"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_records.id", ondelete="SET NULL")
    )
    canonical_description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64), index=True)
    equivalence_status: Mapped[str] = mapped_column(String(16), default="UNRESOLVED")
    specs: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    provenance: Mapped[str] = mapped_column(String(16), default="DERIVED")

    canonical_record = relationship("MaterialRecord")
    members: Mapped[list["IdentityMember"]] = relationship(
        back_populates="identity", cascade="all, delete-orphan"
    )


class IdentityMember(Base, TimestampMixin):
    __tablename__ = "identity_members"
    __table_args__ = (
        UniqueConstraint("identity_id", "record_id", name="uq_identity_members_identity_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    identity_id: Mapped[int] = mapped_column(
        ForeignKey("material_identities.id", ondelete="CASCADE"), index=True
    )
    record_id: Mapped[int] = mapped_column(
        ForeignKey("material_records.id", ondelete="CASCADE"), index=True
    )
    is_canonical: Mapped[bool] = mapped_column(default=False)

    identity: Mapped["MaterialIdentity"] = relationship(back_populates="members")
    record = relationship("MaterialRecord")
