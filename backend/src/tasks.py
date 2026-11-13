"""Celery 任务：worker 心跳 + 每日观展摘要（写 Redis，供总览读取）。"""
from __future__ import annotations

import time

from src.config.celery_app import TASK_DAILY, TASK_HEARTBEAT, celery_app
from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger("tasks")


def _redis():
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


@celery_app.task(name=TASK_HEARTBEAT)
def heartbeat() -> str:
    try:
        _redis().set(f"{settings.app_name}:worker:heartbeat", time.time())
        return "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("heartbeat failed: %s", exc)
        return "error"


@celery_app.task(name=TASK_DAILY)
def daily_digest() -> dict:
    """每天早上汇总名录与最新路线，写入 Redis 供总览页显示「上次汇总」。"""
    from sqlalchemy import func, select

    from src.config.database import session_scope
    from src.models.exhibitor import Exhibitor
    from src.models.route_run import RouteRun
    from src.models.visit import Visit

    with session_scope() as db:
        payload = {
            "exhibitors": db.scalar(select(func.count()).select_from(Exhibitor)) or 0,
            "route_runs": db.scalar(select(func.count()).select_from(RouteRun)) or 0,
            "visits": db.scalar(select(func.count()).select_from(Visit)) or 0,
            "conflicts": db.scalar(select(func.count()).select_from(Visit).where(Visit.conflict.is_(True))) or 0,
            "generated_at": int(time.time()),
        }
    try:
        import json

        _redis().set(f"{settings.app_name}:digest", json.dumps(payload, ensure_ascii=False, sort_keys=True))
    except Exception as exc:  # noqa: BLE001
        logger.warning("digest write failed: %s", exc)
    logger.info("daily digest: %s", payload)
    return payload
