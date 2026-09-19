from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AttributeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    value: str
    is_hard_key: bool
    source: str
    provenance: str
    confidence: float | None = None


class MaterialRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_record_id: int
    legacy_code: str
    description: str
    normalised_description: str | None = None
    category: str | None = None
    uom: str | None = None
    qty: float | None = None
    unit_value: float | None = None
    split: str | None = None
    cpse: str | None = None
    plant: str | None = None
    attributes: list[AttributeOut] = []
