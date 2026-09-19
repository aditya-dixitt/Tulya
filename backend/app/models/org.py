"""CPSEs and their plants.

Kept as real tables rather than free-text columns on material_records because
the whole Phase-1 argument of this project is that most duplication sits
*inside* one CPSE, between two of its own plants. That claim is only
answerable with a query if the plant is an entity.
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Cpse(Base, TimestampMixin):
    __tablename__ = "cpses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    sector: Mapped[str | None] = mapped_column(String(80))

    plants: Mapped[list["Plant"]] = relationship(
        back_populates="cpse", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Cpse {self.code}>"


class Plant(Base, TimestampMixin):
    __tablename__ = "plants"
    __table_args__ = (
        UniqueConstraint("cpse_id", "name", name="uq_plants_cpse_id"),
        Index("ix_plants_cpse_code", "cpse_id", "sap_plant_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cpse_id: Mapped[int] = mapped_column(
        ForeignKey("cpses.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    # SAP WERKS is four characters; kept so a write-back batch round-trips
    sap_plant_code: Mapped[str | None] = mapped_column(String(8))
    kind: Mapped[str | None] = mapped_column(String(40))  # refinery / terminal / station

    cpse: Mapped["Cpse"] = relationship(back_populates="plants")
