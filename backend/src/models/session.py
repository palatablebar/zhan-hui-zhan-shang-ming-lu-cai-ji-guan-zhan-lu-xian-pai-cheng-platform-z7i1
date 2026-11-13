"""同期论坛/发布会日程：与展商观展时间竞争。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (UniqueConstraint("title", "start_at", name="uq_sessions_title_start"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(160), index=True)
    hall: Mapped[str] = mapped_column(String(24), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    day: Mapped[int] = mapped_column(Integer, default=1, index=True)
    speaker: Mapped[str] = mapped_column(String(80), default="")
    track: Mapped[str] = mapped_column(String(40), default="主题论坛")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    seed_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
