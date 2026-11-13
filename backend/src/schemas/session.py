from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SessionIn(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    hall: str = Field(min_length=2, max_length=24)
    start_at: datetime
    end_at: datetime
    speaker: str = Field(default="", max_length=80)
    track: str = Field(default="主题论坛", max_length=40)
    note: str | None = Field(default=None, max_length=2000)


class SessionPatch(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=160)
    hall: str | None = Field(default=None, min_length=2, max_length=24)
    start_at: datetime | None = None
    end_at: datetime | None = None
    speaker: str | None = Field(default=None, max_length=80)
    track: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=2000)
