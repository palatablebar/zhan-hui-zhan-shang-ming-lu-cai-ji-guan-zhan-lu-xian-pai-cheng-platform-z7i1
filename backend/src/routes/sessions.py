from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import session_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.utils.pagination import page_params

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
def list_sessions(
    day: int | None = Query(default=None, ge=1, le=3),
    hall: str | None = None,
    q: str | None = None,
    limit: int = Query(50),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return session_controller.list_sessions(db, day=day, hall=hall, q=q, limit=page.limit, offset=page.offset)
