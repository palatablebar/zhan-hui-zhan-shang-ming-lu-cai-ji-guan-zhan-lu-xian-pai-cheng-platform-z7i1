"""导出服务：观展路线清单 CSV（UTF-8 BOM，Excel 直接可读）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants.enums import (
    CONFLICT_KIND_LABELS,
    PRIORITY_LABELS,
    VISIT_STATUS_LABELS,
)
from src.models.exhibitor import Exhibitor
from src.models.route_run import RouteRun
from src.models.visit import Visit
from src.utils.csv_export import to_csv


def visits_csv(db: Session, run_id: int | None = None) -> bytes:
    stmt = select(Visit)
    if run_id:
        stmt = stmt.where(Visit.run_id == run_id)
    else:
        latest = db.scalar(select(RouteRun).order_by(RouteRun.id.desc()).limit(1))
        if latest is not None:
            stmt = stmt.where(Visit.run_id == latest.id)
    visits = db.scalars(stmt.order_by(Visit.day, Visit.seq, Visit.id)).all()
    exhibitors = {row.id: row for row in db.scalars(select(Exhibitor)).all()}
    runs = {row.id: row for row in db.scalars(select(RouteRun)).all()}
    headers = [
        "日期", "天", "序号", "展商", "馆", "展位号", "优先级", "预计到达",
        "停留(分)", "步行增量(m)", "预约", "冲突", "状态", "联系人", "电话", "运行号",
    ]
    rows = []
    for visit in visits:
        exhibitor = exhibitors.get(visit.exhibitor_id)
        run = runs.get(visit.run_id)
        appointment = ""
        if exhibitor and exhibitor.appointment_day is not None and exhibitor.appointment_start_min is not None:
            appointment = f"Day{exhibitor.appointment_day} {exhibitor.appointment_start_min // 60:02d}:{exhibitor.appointment_start_min % 60:02d}"
        rows.append(
            [
                f"Day{visit.day}",
                visit.day,
                visit.seq if visit.seq < 9000 else "",
                exhibitor.name if exhibitor else "",
                exhibitor.hall if exhibitor else "",
                exhibitor.booth_no if exhibitor else "",
                PRIORITY_LABELS.get(exhibitor.priority, exhibitor.priority) if exhibitor else "",
                f"{visit.eta_min // 60:02d}:{visit.eta_min % 60:02d}",
                visit.dwell_min,
                f"{float(visit.walk_before_m or 0):.1f}",
                appointment,
                CONFLICT_KIND_LABELS.get(visit.conflict_kind or "", "") if visit.conflict else "",
                VISIT_STATUS_LABELS.get(visit.status, visit.status),
                exhibitor.contact_name if exhibitor else "",
                exhibitor.contact_phone if exhibitor else "",
                run.run_no if run else "",
            ]
        )
    return to_csv(headers, rows)
