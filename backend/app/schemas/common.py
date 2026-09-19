from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Every list endpoint returns this shape; the UI never guesses a total."""
    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class Provenance(BaseModel):
    """Attached to any value that is not a direct measurement."""
    kind: str = Field(description="MEASURED | DERIVED | SIMULATED | PROPOSED | "
                                  "VERIFIED | UNKNOWN | PLANNED")
    basis: str = Field(description="Plain-language statement of where this came from")
