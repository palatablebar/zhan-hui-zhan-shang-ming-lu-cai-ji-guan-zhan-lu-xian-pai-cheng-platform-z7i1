from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VisitReviewIn(BaseModel):
    """复核一条到访：确认 / 改期到另一天 / 顺延。"""

    status: Literal["planned", "confirmed", "adjusted", "deferred"]
    note: str | None = Field(default=None, max_length=1000)
    day: int | None = Field(default=None, ge=1, le=3)
