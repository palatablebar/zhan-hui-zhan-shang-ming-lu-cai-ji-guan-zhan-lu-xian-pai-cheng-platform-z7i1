"""路线中的一次展位到访：算法输出 + 人工复核状态。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class Visit(Base):
    __tablename__ = "visits"
    __table_args__ = (UniqueConstraint("run_id", "exhibitor_id", name="uq_visits_run_exhibitor"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("route_runs.id", ondelete="CASCADE"), index=True)
    exhibitor_id: Mapped[int] = mapped_column(ForeignKey("exhibitors.id", ondelete="CASCADE"), index=True)
    day: Mapped[int] = mapped_column(Integer, default=1, index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    eta_min: Mapped[int] = mapped_column(Integer, default=0)
    eta_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dwell_min: Mapped[int] = mapped_column(Integer, default=6)
    walk_before_m: Mapped[float] = mapped_column(Float, default=0.0)
    conflict: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    conflict_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    conflict_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="planned", index=True)
    reviewer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
