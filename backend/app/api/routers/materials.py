"""Material records: list, filter, search, and fetch one with its attributes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession, selectinload

from ...db import get_db
from ...matching import normalize
from ...models import Cpse, MaterialRecord, Plant
from ...schemas.common import Page
from ...schemas.material import AttributeOut, MaterialRecordOut
from ..deps import require_viewer

router = APIRouter(prefix="/materials", tags=["materials"],
                   dependencies=[Depends(require_viewer)])


def _out(r: MaterialRecord) -> MaterialRecordOut:
    return MaterialRecordOut(
        id=r.id, source_record_id=r.source_record_id, legacy_code=r.legacy_code,
        description=r.description, normalised_description=r.normalised_description,
        category=r.category, uom=r.uom, qty=r.qty, unit_value=r.unit_value,
        split=r.split,
        cpse=r.cpse.code if r.cpse else None,
        plant=r.plant.name if r.plant else None,
        attributes=[AttributeOut.model_validate(a) for a in r.attributes],
    )


@router.get("", response_model=Page[MaterialRecordOut], summary="List material records")
def list_materials(
    db: DbSession = Depends(get_db),
    q: str | None = Query(None, description="free text over description and legacy code"),
    cpse: str | None = None,
    plant: str | None = None,
    category: str | None = None,
    split: str | None = None,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Page[MaterialRecordOut]:
    stmt = select(MaterialRecord).options(
        selectinload(MaterialRecord.attributes),
        selectinload(MaterialRecord.cpse),
        selectinload(MaterialRecord.plant),
    )
    count_stmt = select(func.count()).select_from(MaterialRecord)

    def narrow(s):
        if cpse:
            s = s.join(Cpse, MaterialRecord.cpse_id == Cpse.id).where(Cpse.code == cpse)
        if plant:
            s = s.join(Plant, MaterialRecord.plant_id == Plant.id).where(
                Plant.name.ilike(f"%{plant}%"))
        if category:
            s = s.where(MaterialRecord.category == category)
        if split:
            s = s.where(MaterialRecord.split == split)
        if q:
            # the same normaliser the engine uses, so a query behaves like a record
            nq = normalize(q)
            s = s.where(or_(
                MaterialRecord.description.ilike(f"%{q}%"),
                MaterialRecord.normalised_description.ilike(f"%{nq}%"),
                MaterialRecord.legacy_code.ilike(f"%{q}%"),
            ))
        return s

    total = db.execute(narrow(count_stmt)).scalar_one()
    rows = db.execute(
        narrow(stmt).order_by(MaterialRecord.source_record_id).limit(limit).offset(offset)
    ).scalars().all()
    return Page[MaterialRecordOut](items=[_out(r) for r in rows], total=total,
                                   limit=limit, offset=offset)


@router.get("/{record_id}", response_model=MaterialRecordOut, summary="One record")
def get_material(record_id: int, db: DbSession = Depends(get_db)) -> MaterialRecordOut:
    r = db.execute(
        select(MaterialRecord)
        .options(selectinload(MaterialRecord.attributes),
                 selectinload(MaterialRecord.cpse), selectinload(MaterialRecord.plant))
        .where(MaterialRecord.id == record_id)
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, detail={"code": "not_found",
                                         "message": f"no material record {record_id}"})
    return _out(r)


@router.get("/by-legacy/{cpse}/{legacy_code}", response_model=list[MaterialRecordOut],
            summary="Resolve a legacy code (may be ambiguous)")
def by_legacy(cpse: str, legacy_code: str,
              db: DbSession = Depends(get_db)) -> list[MaterialRecordOut]:
    """Returns a LIST on purpose.

    Legacy codes are not unique within a CPSE in this dataset — the same code
    appears at more than one plant — so resolving one has to hand the steward
    every candidate rather than silently picking the first.
    """
    rows = db.execute(
        select(MaterialRecord)
        .join(Cpse, MaterialRecord.cpse_id == Cpse.id)
        .options(selectinload(MaterialRecord.attributes),
                 selectinload(MaterialRecord.cpse), selectinload(MaterialRecord.plant))
        .where(Cpse.code == cpse, MaterialRecord.legacy_code == legacy_code)
    ).scalars().all()
    return [_out(r) for r in rows]
