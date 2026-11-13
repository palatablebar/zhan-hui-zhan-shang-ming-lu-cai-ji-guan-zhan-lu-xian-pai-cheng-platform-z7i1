"""到访路线服务：按运行/天/状态筛选，序列化，人工复核与改期。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import (
    CONFLICT_KIND_LABELS,
    PRIORITY_LABELS,
    SHOW_DAY_DATES,
    VISIT_STATUS_LABELS,
)
from src.models.exhibitor import Exhibitor
from src.models.route_run import RouteRun
from src.models.visit import Visit
from src.services import booth_service, route_service
from src.utils.errors import AppError
from src.utils.timeutil import iso_utc, show_day_utc, utcnow


def serialize(visit: Visit, exhibitor: Exhibitor | None = None, run: RouteRun | None = None, *, role: str = "admin") -> dict:
    phone = exhibitor.contact_phone if exhibitor else ""
    return {
        "id": visit.id,
        "run_id": visit.run_id,
        "run_no": run.run_no if run else None,
        "exhibitor_id": visit.exhibitor_id,
        "exhibitor_name": exhibitor.name if exhibitor else None,
        "hall": exhibitor.hall if exhibitor else None,
        "booth_no": exhibitor.booth_no if exhibitor else None,
        "category": exhibitor.category if exhibitor else None,
        "priority": exhibitor.priority if exhibitor else None,
        "priority_label": PRIORITY_LABELS.get(exhibitor.priority, exhibitor.priority) if exhibitor else None,
        "contact_name": exhibitor.contact_name if exhibitor else None,
        "contact_phone": (phone if role != "viewer" else f"{phone[:3]}****{phone[-4:]}" if len(phone or '') >= 6 else phone),
        "day": visit.day,
        "seq": visit.seq,
        "eta_min": visit.eta_min,
        "eta_label": route_service.format_minute(visit.eta_min),
        "eta_at": iso_utc(visit.eta_at),
        "dwell_min": visit.dwell_min,
        "walk_before_m": round(float(visit.walk_before_m or 0), 1),
        "conflict": visit.conflict,
        "conflict_kind": visit.conflict_kind,
        "conflict_label": CONFLICT_KIND_LABELS.get(visit.conflict_kind or "", None),
        "conflict_note": visit.conflict_note,
        "status": visit.status,
        "status_label": VISIT_STATUS_LABELS.get(visit.status, visit.status),
        "reviewer": visit.reviewer,
        "review_note": visit.review_note,
        "appointment_label": (
            f"Day{exhibitor.appointment_day} {route_service.format_minute(exhibitor.appointment_start_min)}"
            if exhibitor and exhibitor.appointment_day is not None and exhibitor.appointment_start_min is not None
            else None
        ),
    }


def _maps(db: Session, run_ids: set[int] | None = None) -> tuple[dict[int, Exhibitor], dict[int, RouteRun]]:
    exhibitors = {row.id: row for row in db.scalars(select(Exhibitor)).all()}
    runs = {row.id: row for row in db.scalars(select(RouteRun)).all()}
    if run_ids is not None:
        runs = {key: value for key, value in runs.items() if key in run_ids}
    return exhibitors, runs


def list_visits(
    db: Session,
    *,
    run_id: int | None = None,
    day: int | None = None,
    status: str | None = None,
    conflict: bool | None = None,
    priority: str | None = None,
    limit: int = 100,
    offset: int = 0,
    role: str = "admin",
) -> dict:
    stmt = select(Visit)
    count_stmt = select(func.count()).select_from(Visit)
    filters = []
    if run_id:
        filters.append(Visit.run_id == run_id)
    if day:
        filters.append(Visit.day == day)
    if status:
        filters.append(Visit.status == status)
    if conflict is not None:
        filters.append(Visit.conflict.is_(conflict))
    for clause in filters:
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(Visit.day, Visit.seq, Visit.id).limit(limit).offset(offset)).all()
    exhibitors, runs = _maps(db, {row.run_id for row in rows})
    items = [serialize(row, exhibitors.get(row.exhibitor_id), runs.get(row.run_id), role=role) for row in rows]
    if priority:
        items = [item for item in items if item["priority"] == priority]
    return {"items": items, "total": len(items) if priority else total, "limit": limit, "offset": offset}


def get_visit(db: Session, visit_id: int) -> Visit:
    visit = db.get(Visit, visit_id)
    if visit is None:
        raise AppError("NOT_FOUND", 404, {"entity": "visit", "id": visit_id})
    return visit


def _reschedule(db: Session, visit: Visit, target_day: int) -> Visit:
    """把到访改到目标天：接在当天最后一站之后，按实时距离重算 ETA。"""
    siblings = [
        row
        for row in db.scalars(select(Visit).where(Visit.run_id == visit.run_id, Visit.day == target_day)).all()
        if row.id != visit.id and row.seq < route_service.DEFERRED_SEQ_BASE
    ]
    siblings.sort(key=lambda row: row.seq)
    if not siblings:
        eta = 540
        seq = 1
    else:
        last = siblings[-1]
        last_end = last.eta_min + last.dwell_min
        current_exhibitor = db.get(Exhibitor, visit.exhibitor_id)
        last_exhibitor = db.get(Exhibitor, last.exhibitor_id)
        distance = 0.0
        if current_exhibitor and last_exhibitor:
            try:
                distance = booth_service.walking_distance(
                    booth_service.parse_booth_no(last_exhibitor.booth_no),
                    booth_service.parse_booth_no(current_exhibitor.booth_no),
                )
            except booth_service.BoothFormatError:
                distance = 0.0
        eta = last_end + int(round(distance / 55.0))
        seq = last.seq + 1
    visit.day = target_day
    visit.seq = seq
    visit.eta_min = eta
    visit.eta_at = show_day_utc(target_day, eta) if target_day in SHOW_DAY_DATES else None
    visit.conflict = False
    return visit


def review(db: Session, visit: Visit, *, status: str, note: str | None, day: int | None, reviewer: str) -> Visit:
    if status not in {"planned", "confirmed", "adjusted", "deferred"}:
        raise AppError("VALIDATION", 422, {"field": "status"})
    moved = False
    if day is not None and day != visit.day:
        if day not in SHOW_DAY_DATES:
            raise AppError("VALIDATION", 422, {"field": "day"})
        _reschedule(db, visit, day)
        moved = True
    visit.status = "adjusted" if moved else status
    visit.reviewer = reviewer
    visit.review_note = note
    if moved:
        suffix = f"人工改期至 Day{day}"
        visit.conflict_note = f"{visit.conflict_note}；{suffix}" if visit.conflict_note else suffix
    if status == "deferred" and visit.conflict is False:
        visit.conflict = True
        visit.conflict_kind = visit.conflict_kind or "appointment"
        visit.conflict_note = note or visit.conflict_note
    visit.updated_at = utcnow()
    db.flush()
    return visit
