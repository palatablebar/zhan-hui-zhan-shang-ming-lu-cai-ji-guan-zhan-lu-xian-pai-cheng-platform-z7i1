"""路线排程控制器：发起排程、查询运行与路线明细。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, route_run_service, visit_service


def create_run(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    run = route_run_service.create_and_execute(
        db,
        params=payload,
        operator_email=principal["email"],
        trigger="manual",
    )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="route.create",
        entity="route_run",
        entity_id=run.id,
        detail={"run_no": run.run_no, "priorities": (run.params or {}).get("priorities")},
        ip=request.client.host if request.client else None,
    )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="route.complete",
        entity="route_run",
        entity_id=run.id,
        detail={"status": run.status, "visits": (run.metrics or {}).get("visit_count"), "walk_m": (run.metrics or {}).get("total_walk_m")},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    data = route_run_service.serialize(run)
    data["visits"] = visit_service.list_visits(db, run_id=run.id, limit=400, role=principal["role"])["items"]
    return data


def list_runs(db: Session, **filters) -> dict:
    return route_run_service.list_runs(db, **filters)


def get_run(db: Session, run_id: int, role: str) -> dict:
    run = route_run_service.get_run(db, run_id)
    data = route_run_service.serialize(run)
    data["visits"] = visit_service.list_visits(db, run_id=run.id, limit=400, role=role)["items"]
    return data
