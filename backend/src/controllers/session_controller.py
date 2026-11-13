"""论坛日程控制器（只读）。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.services import session_service


def list_sessions(db: Session, **filters) -> dict:
    return session_service.list_sessions(db, **filters)
