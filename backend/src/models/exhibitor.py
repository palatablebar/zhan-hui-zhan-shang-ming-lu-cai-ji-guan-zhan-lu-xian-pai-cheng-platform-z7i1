"""展商名录：官网/小程序采集后清洗入册的一条展商记录。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class Exhibitor(Base):
    __tablename__ = "exhibitors"
    __table_args__ = (UniqueConstraint("hall", "booth_no", name="uq_exhibitors_hall_booth"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    hall: Mapped[str] = mapped_column(String(8), index=True)
    booth_no: Mapped[str] = mapped_column(String(16), index=True)
    row_no: Mapped[int] = mapped_column(Integer, default=0)
    col_no: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String(24), index=True)
    target_industry: Mapped[str] = mapped_column(String(24), default="general", index=True)
    contact_name: Mapped[str] = mapped_column(String(60), default="")
    contact_title: Mapped[str] = mapped_column(String(40), default="")
    contact_phone: Mapped[str] = mapped_column(String(32), default="")
    priority: Mapped[str] = mapped_column(String(4), default="P2", index=True)
    dwell_min: Mapped[int] = mapped_column(Integer, default=6)
    appointment_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    appointment_day: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    appointment_start_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    appointment_end_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    seed_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
