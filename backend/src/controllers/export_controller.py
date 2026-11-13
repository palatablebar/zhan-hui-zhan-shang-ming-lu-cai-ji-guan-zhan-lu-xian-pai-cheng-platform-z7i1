"""导出控制器：CSV 响应 + 审计。"""
from __future__ import annotations

from fastapi import Request, Response
from sqlalchemy.orm import Session

from src.services import audit_service, export_service
from src.utils.csv_export import csv_response_headers


def visits_csv(db: Session, run_id: int | None, principal: dict, request: Request) -> Response:
    content = export_service.visits_csv(db, run_id)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="export.visits",
        entity="visit",
        entity_id=run_id,
        detail={"bytes": len(content)},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return Response(content=content, media_type="text/csv; charset=utf-8", headers=csv_response_headers("boothmap-visits.csv"))
