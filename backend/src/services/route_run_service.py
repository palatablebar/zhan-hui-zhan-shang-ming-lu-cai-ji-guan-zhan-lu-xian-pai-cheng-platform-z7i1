"""路线排程服务：加载名录 → 调用算法 B → 落库 RouteRun + Visit。"""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.constants.enums import PRIORITY_DWELL_MIN, ROUTE_STATUS_LABELS, SHOW_DAY_DATES
from src.models.exhibitor import Exhibitor
from src.models.route_run import RouteRun
from src.models.visit import Visit
from src.services import booth_service, route_service
from src.utils.errors import AppError
from src.utils.timeutil import iso_utc, local_now, show_day_utc, utcnow


def serialize(run: RouteRun) -> dict:
    return {
        "id": run.id,
        "run_no": run.run_no,
        "day_count": run.day_count,
        "status": run.status,
        "status_label": ROUTE_STATUS_LABELS.get(run.status, run.status),
        "trigger": run.trigger,
        "operator_email": run.operator_email,
        "params": run.params or {},
        "metrics": run.metrics or {},
        "log_text": run.log_text,
        "started_at": iso_utc(run.started_at),
        "finished_at": iso_utc(run.finished_at),
    }


def next_run_no(db: Session) -> str:
    prefix = f"RT{local_now():%Y%m%d}"
    count = db.scalar(select(func.count()).select_from(RouteRun).where(RouteRun.run_no.like(f"{prefix}%"))) or 0
    return f"{prefix}-{count + 1:04d}"


def load_candidates(db: Session, priorities: list[str]) -> tuple[list[route_service.Candidate], int]:
    rows = db.scalars(select(Exhibitor).order_by(Exhibitor.id)).all()
    candidates: list[route_service.Candidate] = []
    invalid = 0
    for row in rows:
        if row.priority not in priorities:
            continue
        try:
            candidates.append(
                route_service.build_candidate(
                    {
                        "id": row.id,
                        "name": row.name,
                        "booth_no": row.booth_no,
                        "priority": row.priority,
                        "dwell_min": row.dwell_min or PRIORITY_DWELL_MIN.get(row.priority, 8),
                        "appointment_day": row.appointment_day,
                        "appointment_start_min": row.appointment_start_min,
                        "appointment_end_min": row.appointment_end_min,
                    }
                )
            )
        except booth_service.BoothFormatError:
            invalid += 1
    return candidates, invalid


def execute_run(db: Session, run: RouteRun, *, priorities: list[str], invalid_rows: int = 0) -> RouteRun:
    run.status = "running"
    params = run.params or {}
    candidates, invalid = load_candidates(db, priorities)
    try:
        result = route_service.plan_routes(
            candidates,
            day_count=int(params.get("day_count") or run.day_count or 2),
            day_minutes=int(params.get("day_minutes") or 480),
            day_start_minute=int(params.get("day_start_minute") or 540),
            speed=float(params.get("walk_speed_m_per_min") or 55.0),
            priorities=priorities,
            max_visits=params.get("max_visits"),
        )
        db.execute(delete(Visit).where(Visit.run_id == run.id))
        for row in result["visits"]:
            eta_at = show_day_utc(row["day"], row["eta_min"]) if row["day"] in SHOW_DAY_DATES else None
            db.add(
                Visit(
                    run_id=run.id,
                    exhibitor_id=row["exhibitor_id"],
                    day=row["day"],
                    seq=row["seq"],
                    eta_min=row["eta_min"],
                    eta_at=eta_at,
                    dwell_min=row["dwell_min"],
                    walk_before_m=row["walk_before_m"],
                    conflict=bool(row["conflict"]),
                    conflict_kind=row["conflict_kind"],
                    conflict_note=row["conflict_note"],
                    status=row["status"],
                )
            )
        run.metrics = result["metrics"]
        run.log_text = result["log"]
        run.status = result["status"]
        run.finished_at = utcnow()
        run.params = {**params, "priorities": priorities, "invalid_rows": invalid + invalid_rows}
    except Exception as exc:  # noqa: BLE001 - 运行失败要留痕
        run.status = "failed"
        run.log_text = f"排程失败：{exc}"
        run.metrics = {"error": str(exc)[:300]}
        run.finished_at = utcnow()
    db.flush()
    return run


def create_and_execute(
    db: Session,
    *,
    params: dict,
    operator_email: str,
    trigger: str = "manual",
    seed_key: str | None = None,
) -> RouteRun:
    if seed_key:
        existing = db.scalar(select(RouteRun).where(RouteRun.seed_key == seed_key))
        if existing is not None:
            return existing
    priorities = [str(item).upper() for item in (params.get("priorities") or ["P0", "P1"])]
    run = RouteRun(
        run_no=next_run_no(db),
        day_count=int(params.get("day_count") or 2),
        status="running",
        operator_email=operator_email,
        trigger=trigger,
        params={**params, "priorities": priorities},
        seed_key=seed_key,
    )
    db.add(run)
    db.flush()
    return execute_run(db, run, priorities=priorities)


def list_runs(db: Session, *, status: str | None, limit: int, offset: int) -> dict:
    stmt = select(RouteRun)
    count_stmt = select(func.count()).select_from(RouteRun)
    if status:
        stmt = stmt.where(RouteRun.status == status)
        count_stmt = count_stmt.where(RouteRun.status == status)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(RouteRun.id.desc()).limit(limit).offset(offset)).all()
    return {"items": [serialize(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def get_run(db: Session, run_id: int) -> RouteRun:
    run = db.get(RouteRun, run_id)
    if run is None:
        raise AppError("NOT_FOUND", 404, {"entity": "route_run", "id": run_id})
    return run
