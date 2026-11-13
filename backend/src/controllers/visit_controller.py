"""到访复核控制器。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, visit_service


def list_visits(db: Session, role: str, **filters) -> dict:
    return visit_service.list_visits(db, role=role, **filters)


def review(db: Session, visit_id: int, payload: dict, principal: dict, request: Request) -> dict:
    visit = visit_service.get_visit(db, visit_id)
    visit_service.review(
        db,
        visit,
        status=payload["status"],
        note=payload.get("note"),
        day=payload.get("day"),
        reviewer=principal["email"],
    )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="visit.review",
        entity="visit",
        entity_id=visit.id,
        detail={"status": visit.status, "day": visit.day, "eta_min": visit.eta_min, "conflict": visit.conflict},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    from src.models.exhibitor import Exhibitor
    from src.models.route_run import RouteRun

    return visit_service.serialize(
        visit,
        db.get(Exhibitor, visit.exhibitor_id),
        db.get(RouteRun, visit.run_id),
        role=principal["role"],
    )
