"""总览：名录结构、两日时间轴、同期论坛、最新路线与冲突。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.constants.enums import (
    CATEGORY_LABELS,
    HALL_LABELS,
    PRIORITY_LABELS,
    PRIORITY_ORDER,
    ROUTE_STATUS_LABELS,
    SHOW_DAY_DATES,
    SHOW_DAY_LABELS,
    VISIT_STATUS_LABELS,
)
from src.models.exhibitor import Exhibitor
from src.models.route_run import RouteRun
from src.models.session import Session
from src.models.visit import Visit
from src.services import route_service, session_service


def worker_alive() -> bool:
    try:
        import time

        import redis

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2)
        value = client.get(f"{settings.app_name}:worker:heartbeat")
        return bool(value) and (time.time() - float(value)) < 120
    except Exception:
        return False


def _priority_counts(db: Session) -> list[dict]:
    rows = dict(db.execute(select(Exhibitor.priority, func.count()).group_by(Exhibitor.priority)).all())
    return [
        {"key": key, "label": PRIORITY_LABELS.get(key, key), "count": int(rows.get(key, 0))}
        for key in PRIORITY_ORDER
    ]


def _hall_counts(db: Session) -> list[dict]:
    rows = db.execute(select(Exhibitor.hall, func.count()).group_by(Exhibitor.hall)).all()
    return [
        {"key": hall, "label": HALL_LABELS.get(hall, hall), "count": count}
        for hall, count in sorted(rows)
    ]


def _category_counts(db: Session) -> list[dict]:
    rows = db.execute(select(Exhibitor.category, func.count()).group_by(Exhibitor.category)).all()
    return sorted(
        [{"key": key, "label": CATEGORY_LABELS.get(key, key), "count": count} for key, count in rows],
        key=lambda item: -item["count"],
    )


def _timeline(db: Session, run: RouteRun | None) -> list[dict]:
    visits_by_day: dict[int, list[dict]] = {1: [], 2: [], 3: []}
    if run is not None:
        rows = db.scalars(select(Visit).where(Visit.run_id == run.id, Visit.seq < route_service.DEFERRED_SEQ_BASE)).all()
        exhibitors = {row.id: row for row in db.scalars(select(Exhibitor)).all()}
        for row in sorted(rows, key=lambda item: (item.day, item.seq)):
            exhibitor = exhibitors.get(row.exhibitor_id)
            visits_by_day.setdefault(row.day, []).append(
                {
                    "id": row.id,
                    "seq": row.seq,
                    "eta_label": route_service.format_minute(row.eta_min),
                    "exhibitor_name": exhibitor.name if exhibitor else f"#{row.exhibitor_id}",
                    "hall": exhibitor.hall if exhibitor else None,
                    "booth_no": exhibitor.booth_no if exhibitor else None,
                    "priority": exhibitor.priority if exhibitor else None,
                    "priority_label": PRIORITY_LABELS.get(exhibitor.priority, exhibitor.priority) if exhibitor else None,
                    "dwell_min": row.dwell_min,
                    "conflict": row.conflict,
                    "status": row.status,
                    "status_label": VISIT_STATUS_LABELS.get(row.status, row.status),
                }
            )
    timeline = []
    for day in (1, 2):
        sessions = [
            {
                "id": item["id"],
                "title": item["title"],
                "start_label": item["start_label"],
                "end_label": item["end_label"],
                "hall": item["hall"],
                "speaker": item["speaker"],
                "track": item["track"],
            }
            for item in session_service.list_day_sessions(db, day)
        ]
        timeline.append(
            {
                "day": day,
                "label": SHOW_DAY_LABELS.get(day, f"Day {day}"),
                "date": SHOW_DAY_DATES.get(day, ""),
                "visits": visits_by_day.get(day, []),
                "sessions": sessions,
            }
        )
    return timeline


def overview(db: Session) -> dict:
    exhibitors_total = db.scalar(select(func.count()).select_from(Exhibitor)) or 0
    sessions_total = db.scalar(select(func.count()).select_from(Session)) or 0
    runs_total = db.scalar(select(func.count()).select_from(RouteRun)) or 0
    visits_total = db.scalar(select(func.count()).select_from(Visit)) or 0
    latest_run = db.scalar(select(RouteRun).order_by(RouteRun.id.desc()).limit(1))
    conflicts = 0
    deferred = 0
    if latest_run is not None:
        conflicts = db.scalar(
            select(func.count()).select_from(Visit).where(Visit.run_id == latest_run.id, Visit.conflict.is_(True))
        ) or 0
        deferred = db.scalar(
            select(func.count()).select_from(Visit).where(Visit.run_id == latest_run.id, Visit.status == "deferred")
        ) or 0
    appointment_total = db.scalar(select(func.count()).select_from(Exhibitor).where(Exhibitor.appointment_day.is_not(None))) or 0
    return {
        "exhibitors_total": exhibitors_total,
        "sessions_total": sessions_total,
        "runs_total": runs_total,
        "visits_total": visits_total,
        "conflicts": conflicts,
        "deferred": deferred,
        "appointment_total": appointment_total,
        "worker_alive": worker_alive(),
        "priority": _priority_counts(db),
        "halls": _hall_counts(db),
        "categories": _category_counts(db),
        "latest_run": (
            {
                "id": latest_run.id,
                "run_no": latest_run.run_no,
                "status": latest_run.status,
                "status_label": ROUTE_STATUS_LABELS.get(latest_run.status, latest_run.status),
                "started_at": latest_run.started_at.isoformat(timespec="seconds") + "Z" if latest_run.started_at else None,
                "metrics": latest_run.metrics or {},
            }
            if latest_run
            else None
        ),
        "timeline": _timeline(db, latest_run),
    }
