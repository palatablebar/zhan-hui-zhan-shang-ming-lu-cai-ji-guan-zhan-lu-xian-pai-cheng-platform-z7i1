from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import EXHIBITOR_WRITE_ROLES
from src.controllers import exhibitor_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.exhibitor import ExhibitorIn, ExhibitorPatch
from src.utils.pagination import page_params

router = APIRouter(prefix="/exhibitors", tags=["exhibitors"])


@router.get("")
def list_exhibitors(
    q: str | None = None,
    hall: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    target_industry: str | None = None,
    has_appointment: bool | None = None,
    limit: int = Query(30),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return exhibitor_controller.list_exhibitors(
        db,
        principal["role"],
        q=q,
        hall=hall,
        priority=priority,
        category=category,
        target_industry=target_industry,
        has_appointment=has_appointment,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/distance-groups")
def distance_groups(
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return exhibitor_controller.distance_groups(db)


@router.get("/distance-matrix")
def distance_matrix(
    ids: str | None = Query(default=None, description="逗号分隔的展商 id，最多 20 个"),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    parsed: list[int] = []
    for token in (ids or "").split(","):
        token = token.strip()
        if token.isdigit():
            parsed.append(int(token))
    return exhibitor_controller.distance_matrix(db, parsed[:20])


@router.get("/{exhibitor_id}")
def get_exhibitor(
    exhibitor_id: int,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return exhibitor_controller.get_exhibitor(db, exhibitor_id, principal["role"])


@router.post("", status_code=201)
def create_exhibitor(
    payload: ExhibitorIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EXHIBITOR_WRITE_ROLES)),
) -> dict:
    return exhibitor_controller.create_exhibitor(db, payload.model_dump(), principal, request)


@router.patch("/{exhibitor_id}")
def update_exhibitor(
    exhibitor_id: int,
    payload: ExhibitorPatch,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EXHIBITOR_WRITE_ROLES)),
) -> dict:
    return exhibitor_controller.update_exhibitor(
        db, exhibitor_id, payload.model_dump(exclude_unset=True), principal, request
    )
