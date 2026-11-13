from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import REVIEW_ROLES
from src.controllers import visit_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.visit import VisitReviewIn
from src.utils.pagination import page_params

router = APIRouter(prefix="/visits", tags=["visits"])


@router.get("")
def list_visits(
    run_id: int | None = None,
    day: int | None = Query(default=None, ge=1, le=3),
    status: str | None = None,
    conflict: bool | None = None,
    priority: str | None = None,
    limit: int = Query(100),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return visit_controller.list_visits(
        db,
        principal["role"],
        run_id=run_id,
        day=day,
        status=status,
        conflict=conflict,
        priority=priority,
        limit=page.limit,
        offset=page.offset,
    )


@router.patch("/{visit_id}/review")
def review(
    visit_id: int,
    payload: VisitReviewIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*REVIEW_ROLES)),
) -> dict:
    return visit_controller.review(db, visit_id, payload.model_dump(), principal, request)
