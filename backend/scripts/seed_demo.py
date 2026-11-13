"""幂等 seed：3 账号 / 186 家展商 / 24 场论坛 / 1 次两日路线排程。

自然键 upsert：
  users.email
  exhibitors.seed_key
  sessions.seed_key
  route_runs.seed_key
  visits (run_id, exhibitor_id)
  audit_logs.seed_key

重复执行不新增、不覆盖用户改过的优先级与复核状态；SEED_SUMMARY 逐字一致。
SEED_SUMMARY 键名沿用批次固定契约：
  sources = 展商名录条目数（本项目没有「接入源」实体）
  runs    = 路线排程次数（route_runs）
  findings= 到访条目数（visits，含冲突改期行）
  pending = 仍待确认（status=planned）的到访数
"""
from __future__ import annotations

from sqlalchemy import func, select

from src.config.database import session_scope
from src.models.audit import AuditLog
from src.models.exhibitor import Exhibitor
from src.models.route_run import RouteRun
from src.models.session import Session
from src.models.user import User
from src.models.visit import Visit
from src.services import route_run_service
from src.utils.security import hash_password
from src.utils.timeutil import show_day_utc

from scripts.demo_config import (
    DEMO_PASSWORD,
    DEMO_USERS,
    EXHIBITORS,
    ORG,
    SEED_AUDIT,
    SEED_ROUTE_RUN,
    SESSIONS,
)


def ensure_users(db) -> int:
    for email, display_name, role in DEMO_USERS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            db.add(
                User(
                    email=email,
                    password_hash=hash_password(DEMO_PASSWORD),
                    display_name=display_name,
                    role=role,
                    org=ORG,
                )
            )
    db.flush()
    return db.scalar(select(func.count()).select_from(User)) or 0


def ensure_exhibitors(db) -> int:
    for spec in EXHIBITORS:
        existing = db.scalar(select(Exhibitor).where(Exhibitor.seed_key == spec["seed_key"]))
        if existing is not None:
            continue
        db.add(
            Exhibitor(
                name=spec["name"],
                hall=spec["hall"],
                booth_no=spec["booth_no"],
                row_no=spec["row_no"],
                col_no=spec["col_no"],
                category=spec["category"],
                target_industry=spec["target_industry"],
                contact_name=spec["contact_name"],
                contact_title=spec["contact_title"],
                contact_phone=spec["contact_phone"],
                priority=spec["priority"],
                dwell_min=spec["dwell_min"],
                appointment_at=(
                    show_day_utc(spec["appointment_day"], spec["appointment_start_min"])
                    if spec.get("appointment_day") is not None
                    else None
                ),
                appointment_day=spec.get("appointment_day"),
                appointment_start_min=spec.get("appointment_start_min"),
                appointment_end_min=spec.get("appointment_end_min"),
                note=spec.get("note"),
                seed_key=spec["seed_key"],
            )
        )
    db.flush()
    return db.scalar(select(func.count()).select_from(Exhibitor)) or 0


def ensure_sessions(db) -> int:
    for spec in SESSIONS:
        existing = db.scalar(select(Session).where(Session.seed_key == spec["seed_key"]))
        if existing is not None:
            continue
        db.add(
            Session(
                title=spec["title"],
                hall=spec["hall"],
                start_at=show_day_utc(spec["day"], spec["start_min"]),
                end_at=show_day_utc(spec["day"], spec["end_min"]),
                day=spec["day"],
                speaker=spec["speaker"],
                track=spec["track"],
                note=None,
                seed_key=spec["seed_key"],
            )
        )
    db.flush()
    return db.scalar(select(func.count()).select_from(Session)) or 0


def ensure_route_run(db) -> int:
    route_run_service.create_and_execute(
        db,
        params=dict(SEED_ROUTE_RUN["params"]),
        operator_email=SEED_ROUTE_RUN["operator"],
        trigger=SEED_ROUTE_RUN["trigger"],
        seed_key=SEED_ROUTE_RUN["seed_key"],
    )
    return db.scalar(select(func.count()).select_from(RouteRun)) or 0


def ensure_audit(db) -> None:
    for seed_key, email, role, action, entity, detail in SEED_AUDIT:
        exists = db.scalar(select(AuditLog).where(AuditLog.seed_key == seed_key))
        if exists is not None:
            continue
        db.add(
            AuditLog(
                actor_email=email,
                actor_role=role,
                action=action,
                entity=entity,
                detail=detail,
                layer="seed",
                seed_key=seed_key,
            )
        )
    db.flush()


def seed_all() -> dict:
    with session_scope() as db:
        users = ensure_users(db)
        exhibitors = ensure_exhibitors(db)
        sessions = ensure_sessions(db)
        runs = ensure_route_run(db)
        ensure_audit(db)
        visits = db.scalar(select(func.count()).select_from(Visit)) or 0
        pending = db.scalar(select(func.count()).select_from(Visit).where(Visit.status == "planned")) or 0
        conflicts = db.scalar(select(func.count()).select_from(Visit).where(Visit.conflict.is_(True))) or 0
        summary = (
            f"SEED_SUMMARY brand=boothmap users={users} sources={exhibitors} "
            f"runs={runs} findings={visits} pending={pending}"
        )
        print(summary, flush=True)
        print(
            f"SEED_DETAIL sessions={sessions} conflicts={conflicts} "
            f"deferred={db.scalar(select(func.count()).select_from(Visit).where(Visit.status == 'deferred')) or 0}",
            flush=True,
        )
        return {
            "users": users,
            "exhibitors": exhibitors,
            "sessions": sessions,
            "runs": runs,
            "visits": visits,
            "pending": pending,
            "conflicts": conflicts,
        }


if __name__ == "__main__":
    seed_all()
