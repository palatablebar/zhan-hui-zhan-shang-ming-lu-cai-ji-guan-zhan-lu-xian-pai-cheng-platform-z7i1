from __future__ import annotations

from pydantic import BaseModel, Field


class RouteRunIn(BaseModel):
    day_count: int = Field(default=2, ge=1, le=3)
    day_minutes: int = Field(default=480, ge=240, le=720)
    day_start_minute: int = Field(default=540, ge=360, le=780)
    walk_speed_m_per_min: float = Field(default=55.0, ge=20.0, le=120.0)
    priorities: list[str] = Field(default_factory=lambda: ["P0", "P1"])
    max_visits: int | None = Field(default=None, ge=1, le=400)
    note: str | None = Field(default=None, max_length=500)
