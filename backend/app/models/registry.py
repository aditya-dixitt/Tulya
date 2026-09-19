"""The Common National Material Code registry.

Two invariants carried over from `engine/registry.py` and now enforced by the
database rather than by convention:

  * a code is issued once and never reissued — `serial` is unique per class and
    there is no delete path;
  * a legacy code is *mapped*, never overwritten. `code_members` holds the
    mapping and the ERP row it points at is untouched.

A superseded code still resolves. Old purchase orders carry printed codes that
nobody is going to reissue, so retirement is a status change plus a forwarding
pointer, not a deletion.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class NationalMaterialCode(Base, TimestampMixin):
    __tablename__ = "national_material_codes"
    __table_args__ = (
        UniqueConstraint("class_code", "serial", name="uq_national_material_codes_class_code"),
        CheckConstraint(
            "status IN ('ACTIVE','SUPERSEDED','REVOKED')", name="status_known"
        ),
        CheckConstraint(
            "status <> 'SUPERSEDED' OR superseded_by_id IS NOT NULL",
            name="superseded_needs_target",
        ),
        Index("ix_nmc_class_status", "class_code", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nmc: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    class_code: Mapped[str] = mapped_column(String(24), index=True)
    serial: Mapped[int] = mapped_column(Integer)
    check_digit: Mapped[int | None] = mapped_column(Integer)

    segment_name: Mapped[str | None] = mapped_column(String(120))
    family_name: Mapped[str | None] = mapped_column(String(120))
    class_name: Mapped[str | None] = mapped_column(String(120))

    canonical_description: Mapped[str | None] = mapped_column(Text)
    # the defining specification the code asserts; a member whose description
    # cannot confirm this is mapped PROVISIONAL, not CONFIRMED
    signature: Mapped[str | None] = mapped_column(String(300))
    specs: Mapped[dict] = mapped_column(JSONB, server_default="{}")

    identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_identities.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("national_material_codes.id")
    )
    issued_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    issued_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    identity = relationship("MaterialIdentity")
    issued_by = relationship("User")
    superseded_by = relationship("NationalMaterialCode", remote_side=[id])
    members: Mapped[list["CodeMember"]] = relationship(
        back_populates="code", cascade="all, delete-orphan"
    )


class CodeMember(Base, TimestampMixin):
    """One legacy code mapped to one national code. The legacy code survives."""

    __tablename__ = "code_members"
    __table_args__ = (
        UniqueConstraint("code_id", "record_id", name="uq_code_members_code_id"),
        CheckConstraint(
            "link_status IN ('CONFIRMED','PROVISIONAL','WITHDRAWN')",
            name="link_status_known",
        ),
        Index("ix_code_members_record", "record_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code_id: Mapped[int] = mapped_column(
        ForeignKey("national_material_codes.id", ondelete="CASCADE"), index=True
    )
    record_id: Mapped[int] = mapped_column(
        ForeignKey("material_records.id", ondelete="CASCADE"), index=True
    )
    link_status: Mapped[str] = mapped_column(String(16), default="CONFIRMED")
    # specs the member's own description could not confirm; it ships flagged
    # rather than asserted
    unknown_keys: Mapped[list | None] = mapped_column(JSONB)
    confirmed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    code: Mapped["NationalMaterialCode"] = relationship(back_populates="members")
    record = relationship("MaterialRecord")
    confirmed_by = relationship("User")


class CodeRefusal(Base, TimestampMixin):
    """A group the registry declined to code, and why.

    Refusals are kept because "we could not code this" is an operational fact a
    materials team needs, and a system that silently drops them looks better
    than it is.
    """

    __tablename__ = "code_refusals"

    id: Mapped[int] = mapped_column(primary_key=True)
    identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_identities.id", ondelete="CASCADE")
    )
    group_key: Mapped[str] = mapped_column(String(120), index=True)
    reason: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str | None] = mapped_column(Text)
