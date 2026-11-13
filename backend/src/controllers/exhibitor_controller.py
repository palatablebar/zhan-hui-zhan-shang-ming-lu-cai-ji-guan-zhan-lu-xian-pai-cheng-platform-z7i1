"""展商名录控制器：写操作记领域审计；平面图接口不落库。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.constants.enums import SHOW_DAY_DATES
from src.models.exhibitor import Exhibitor
from src.services import audit_service, booth_service, exhibitor_service


def list_exhibitors(db: Session, role: str, **filters) -> dict:
    return exhibitor_service.list_exhibitors(db, role=role, **filters)


def get_exhibitor(db: Session, exhibitor_id: int, role: str) -> dict:
    return exhibitor_service.serialize(exhibitor_service.get_exhibitor(db, exhibitor_id), role=role)


def create_exhibitor(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    exhibitor = exhibitor_service.create_exhibitor(db, payload)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="exhibitor.create",
        entity="exhibitor",
        entity_id=exhibitor.id,
        detail={"name": exhibitor.name, "booth_no": exhibitor.booth_no, "priority": exhibitor.priority},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return exhibitor_service.serialize(exhibitor, role=principal["role"])


def update_exhibitor(db: Session, exhibitor_id: int, payload: dict, principal: dict, request: Request) -> dict:
    exhibitor = exhibitor_service.get_exhibitor(db, exhibitor_id)
    exhibitor_service.update_exhibitor(db, exhibitor, payload)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="exhibitor.update",
        entity="exhibitor",
        entity_id=exhibitor.id,
        detail={"fields": sorted(payload.keys()), "priority": exhibitor.priority},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return exhibitor_service.serialize(exhibitor, role=principal["role"])


def _rows(db: Session) -> list[Exhibitor]:
    return list(db.query(Exhibitor).order_by(Exhibitor.hall, Exhibitor.row_no, Exhibitor.col_no).all())


def distance_groups(db: Session) -> dict:
    rows = _rows(db)
    return booth_service.build_hall_groups(
        [{"id": row.id, "name": row.name, "hall": row.hall, "booth_no": row.booth_no, "priority": row.priority} for row in rows]
    )


def distance_matrix(db: Session, ids: list[int]) -> dict:
    rows = _rows(db)
    if ids:
        wanted = set(ids)
        rows = [row for row in rows if row.id in wanted]
    return booth_service.distance_matrix(
        [{"id": row.id, "name": row.name, "hall": row.hall, "booth_no": row.booth_no} for row in rows]
    )


def day_meta() -> dict:
    return {"days": [{"day": day, "date": date} for day, date in sorted(SHOW_DAY_DATES.items())]}
