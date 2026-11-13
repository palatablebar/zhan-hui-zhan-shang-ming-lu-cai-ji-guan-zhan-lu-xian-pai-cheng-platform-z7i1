"""时间工具：UTC naive 存储 + 业务时区（UTC+8）展示。"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from src.config.settings import settings
from src.constants.enums import SHOW_DAY_DATES


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="seconds") + "Z"


def local_now(reference: datetime | None = None) -> datetime:
    base = reference or utcnow()
    return base + timedelta(minutes=settings.app_timezone_offset_minutes)


def local_stamp(value: datetime | None = None) -> str:
    return (value or local_now()).strftime("%Y-%m-%d %H:%M")


def local_to_utc_naive(value: datetime) -> datetime:
    """把业务本地墙钟时间转成 UTC naive 存储值。"""
    return value - timedelta(minutes=settings.app_timezone_offset_minutes)


def utc_naive_to_local(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value + timedelta(minutes=settings.app_timezone_offset_minutes)


def show_day_local_datetime(day: int, minute_of_day: int) -> datetime:
    """展期第 N 天的本地墙钟时间（09:00 入场 = 540）。"""
    base = date.fromisoformat(SHOW_DAY_DATES[day])
    return datetime.combine(base, time()) + timedelta(minutes=minute_of_day)


def show_day_utc(day: int, minute_of_day: int) -> datetime:
    return local_to_utc_naive(show_day_local_datetime(day, minute_of_day))


def iso_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def days_ago(anchor: date, days: int) -> date:
    return anchor - timedelta(days=days)


def parse_date(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None
