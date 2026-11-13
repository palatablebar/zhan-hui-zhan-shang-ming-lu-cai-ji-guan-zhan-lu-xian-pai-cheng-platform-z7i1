"""展商名录服务：筛选、序列化（按角色脱敏）、新增与修改。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import (
    CATEGORY_LABELS,
    HALL_LABELS,
    PRIORITY_DWELL_MIN,
    PRIORITY_LABELS,
    SHOW_DAY_DATES,
    TARGET_INDUSTRY_LABELS,
)
from src.models.exhibitor import Exhibitor
from src.services import booth_service
from src.utils.errors import AppError, not_found
from src.utils.timeutil import iso_utc, local_to_utc_naive


def mask_phone(phone: str | None) -> str:
    digits = (phone or "").strip()
    if len(digits) < 6:
        return digits
    return f"{digits[:3]}****{digits[-4:]}"


def serialize(exhibitor: Exhibitor, *, role: str = "admin") -> dict:
    try:
        position = booth_service.parse_booth_no(exhibitor.booth_no)
        coords = {"x": position.x, "y": position.y}
    except booth_service.BoothFormatError:
        coords = {"x": None, "y": None}
    phone = exhibitor.contact_phone or ""
    return {
        "id": exhibitor.id,
        "name": exhibitor.name,
        "hall": exhibitor.hall,
        "hall_label": HALL_LABELS.get(exhibitor.hall, exhibitor.hall),
        "booth_no": exhibitor.booth_no,
        "row_no": exhibitor.row_no,
        "col_no": exhibitor.col_no,
        "x": coords["x"],
        "y": coords["y"],
        "category": exhibitor.category,
        "category_label": CATEGORY_LABELS.get(exhibitor.category, exhibitor.category),
        "target_industry": exhibitor.target_industry,
        "target_industry_label": TARGET_INDUSTRY_LABELS.get(exhibitor.target_industry, exhibitor.target_industry),
        "contact_name": exhibitor.contact_name,
        "contact_title": exhibitor.contact_title,
        "contact_phone": phone if role != "viewer" else mask_phone(phone),
        "phone_masked": role == "viewer",
        "priority": exhibitor.priority,
        "priority_label": PRIORITY_LABELS.get(exhibitor.priority, exhibitor.priority),
        "dwell_min": exhibitor.dwell_min,
        "appointment_at": iso_utc(exhibitor.appointment_at),
        "appointment_day": exhibitor.appointment_day,
        "appointment_start_min": exhibitor.appointment_start_min,
        "appointment_end_min": exhibitor.appointment_end_min,
        "appointment_label": _appointment_label(exhibitor),
        "note": exhibitor.note,
        "created_at": iso_utc(exhibitor.created_at),
        "updated_at": iso_utc(exhibitor.updated_at),
    }


def _appointment_label(exhibitor: Exhibitor) -> str | None:
    if exhibitor.appointment_day is None or exhibitor.appointment_start_min is None:
        return None
    start = exhibitor.appointment_start_min
    end = exhibitor.appointment_end_min if exhibitor.appointment_end_min is not None else start + 30
    return f"Day{exhibitor.appointment_day} {start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"


def _apply_appointment(exhibitor: Exhibitor, appointment_at: datetime | None, window_min: int) -> None:
    if appointment_at is None:
        exhibitor.appointment_at = None
        exhibitor.appointment_day = None
        exhibitor.appointment_start_min = None
        exhibitor.appointment_end_min = None
        return
    local = appointment_at
    day = None
    for index, day_text in SHOW_DAY_DATES.items():
        if local.date().isoformat() == day_text:
            day = index
            break
    if day is None:
        raise AppError("VALIDATION", 422, {"field": "appointment_at", "message": "预约时间需落在 2026-11-18 / 11-19 展期内"})
    start_min = local.hour * 60 + local.minute
    if start_min < 540 or start_min + window_min > 1080:
        raise AppError("VALIDATION", 422, {"field": "appointment_at", "message": "预约需落在 09:00-18:00 之间"})
    exhibitor.appointment_at = local_to_utc_naive(local.replace(tzinfo=None))
    exhibitor.appointment_day = day
    exhibitor.appointment_start_min = start_min
    exhibitor.appointment_end_min = start_min + window_min


def _priority_counts(db: Session) -> dict:
    rows = db.execute(select(Exhibitor.priority, func.count()).group_by(Exhibitor.priority)).all()
    counts = {"P0": 0, "P1": 0, "P2": 0}
    for key, count in rows:
        counts[key] = count
    return counts


def list_exhibitors(
    db: Session,
    *,
    q: str | None = None,
    hall: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    target_industry: str | None = None,
    has_appointment: bool | None = None,
    limit: int = 30,
    offset: int = 0,
    role: str = "admin",
) -> dict:
    stmt = select(Exhibitor)
    count_stmt = select(func.count()).select_from(Exhibitor)
    filters = []
    if q:
        like = f"%{q.strip()}%"
        filters.append(Exhibitor.name.ilike(like) | Exhibitor.booth_no.ilike(like))
    if hall:
        filters.append(Exhibitor.hall == hall)
    if priority:
        filters.append(Exhibitor.priority == priority)
    if category:
        filters.append(Exhibitor.category == category)
    if target_industry:
        filters.append(Exhibitor.target_industry == target_industry)
    if has_appointment is True:
        filters.append(Exhibitor.appointment_day.is_not(None))
    if has_appointment is False:
        filters.append(Exhibitor.appointment_day.is_(None))
    for clause in filters:
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Exhibitor.priority, Exhibitor.hall, Exhibitor.row_no, Exhibitor.col_no, Exhibitor.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [serialize(row, role=role) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "counts": _priority_counts(db),
    }


def get_exhibitor(db: Session, exhibitor_id: int) -> Exhibitor:
    exhibitor = db.get(Exhibitor, exhibitor_id)
    if exhibitor is None:
        raise not_found("exhibitor", exhibitor_id)
    return exhibitor


def create_exhibitor(db: Session, payload: dict) -> Exhibitor:
    position = booth_service.parse_booth_no(payload["booth_no"])
    if position.hall != payload.get("hall"):
        raise AppError("VALIDATION", 422, {"field": "booth_no", "message": "展位号馆号与 hall 字段不一致"})
    exists = db.scalar(select(Exhibitor).where(Exhibitor.hall == position.hall, Exhibitor.booth_no == position.booth_no))
    if exists is not None:
        raise AppError("CONFLICT", 409, {"booth_no": position.booth_no, "exhibitor_id": exists.id})
    priority = payload.get("priority") or "P2"
    window = int(payload.get("appointment_window_min") or 30)
    exhibitor = Exhibitor(
        name=payload["name"],
        hall=position.hall,
        booth_no=position.booth_no,
        row_no=position.row,
        col_no=position.col,
        category=payload.get("category") or "robot",
        target_industry=payload.get("target_industry") or "general",
        contact_name=payload.get("contact_name") or "",
        contact_title=payload.get("contact_title") or "",
        contact_phone=payload.get("contact_phone") or "",
        priority=priority,
        dwell_min=int(payload.get("dwell_min") or PRIORITY_DWELL_MIN.get(priority, 6)),
        note=payload.get("note"),
    )
    _apply_appointment(exhibitor, payload.get("appointment_at"), window)
    db.add(exhibitor)
    db.flush()
    return exhibitor


def update_exhibitor(db: Session, exhibitor: Exhibitor, payload: dict) -> Exhibitor:
    if "booth_no" in payload and payload["booth_no"]:
        position = booth_service.parse_booth_no(payload["booth_no"])
        hall = payload.get("hall") or exhibitor.hall
        if position.hall != hall:
            raise AppError("VALIDATION", 422, {"field": "booth_no", "message": "展位号馆号与 hall 字段不一致"})
        other = db.scalar(
            select(Exhibitor).where(
                Exhibitor.hall == position.hall,
                Exhibitor.booth_no == position.booth_no,
                Exhibitor.id != exhibitor.id,
            )
        )
        if other is not None:
            raise AppError("CONFLICT", 409, {"booth_no": position.booth_no})
        exhibitor.hall = position.hall
        exhibitor.booth_no = position.booth_no
        exhibitor.row_no = position.row
        exhibitor.col_no = position.col
    for field in ("name", "category", "target_industry", "contact_name", "contact_title", "contact_phone", "priority", "note", "dwell_min"):
        if field in payload and payload[field] is not None:
            setattr(exhibitor, field, payload[field])
    if payload.get("clear_appointment"):
        _apply_appointment(exhibitor, None, 30)
    elif payload.get("appointment_at") is not None:
        _apply_appointment(exhibitor, payload["appointment_at"], int(payload.get("appointment_window_min") or 30))
    db.flush()
    return exhibitor
