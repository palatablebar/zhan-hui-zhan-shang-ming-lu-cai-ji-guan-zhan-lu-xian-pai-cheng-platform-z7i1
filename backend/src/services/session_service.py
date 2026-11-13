"""同期论坛日程服务。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import SHOW_DAY_DATES
from src.models.session import Session
from src.utils.timeutil import iso_utc, utc_naive_to_local


def serialize(session: Session) -> dict:
    start_local = utc_naive_to_local(session.start_at)
    end_local = utc_naive_to_local(session.end_at)
    return {
        "id": session.id,
        "title": session.title,
        "hall": session.hall,
        "start_at": iso_utc(session.start_at),
        "end_at": iso_utc(session.end_at),
        "start_label": f"{start_local:%H:%M}" if start_local else None,
        "end_label": f"{end_local:%H:%M}" if end_local else None,
        "day": session.day,
        "day_label": SHOW_DAY_DATES.get(session.day, ""),
        "speaker": session.speaker,
        "track": session.track,
        "note": session.note,
    }


def list_sessions(
    db: Session,
    *,
    day: int | None = None,
    hall: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    stmt = select(Session)
    count_stmt = select(func.count()).select_from(Session)
    if day:
        stmt = stmt.where(Session.day == day)
        count_stmt = count_stmt.where(Session.day == day)
    if hall:
        stmt = stmt.where(Session.hall == hall)
        count_stmt = count_stmt.where(Session.hall == hall)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Session.title.ilike(like) | Session.speaker.ilike(like))
        count_stmt = count_stmt.where(Session.title.ilike(like) | Session.speaker.ilike(like))
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(Session.day, Session.start_at, Session.id).limit(limit).offset(offset)).all()
    return {"items": [serialize(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def list_day_sessions(db: Session, day: int) -> list[dict]:
    rows = db.scalars(select(Session).where(Session.day == day).order_by(Session.start_at, Session.id)).all()
    return [serialize(row) for row in rows]
