from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

PriorityLiteral = Literal["P0", "P1", "P2"]
CategoryLiteral = Literal["robot", "vision", "drive", "sensor", "software", "logistics", "electric", "metrology"]
IndustryLiteral = Literal["auto", "electronics", "energy", "food", "general", "pharma"]
HallLiteral = Literal["A1", "A2", "B1", "B2", "C1", "C2", "D1", "D2"]

BOOTH_HINT = "展位号格式：馆号-排号(两位)+列号(一位)，例如 A1-023 表示 A1 馆第 02 排第 3 列"


class ExhibitorIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    hall: HallLiteral
    booth_no: str = Field(min_length=5, max_length=10)
    category: CategoryLiteral
    target_industry: IndustryLiteral = "general"
    contact_name: str = Field(default="", max_length=60)
    contact_title: str = Field(default="", max_length=40)
    contact_phone: str = Field(default="", max_length=32, pattern=r"^[0-9+\- ]{0,32}$")
    priority: PriorityLiteral = "P2"
    dwell_min: int | None = Field(default=None, ge=3, le=60)
    appointment_at: datetime | None = None
    appointment_window_min: int = Field(default=30, ge=15, le=120)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("booth_no")
    @classmethod
    def _upper_booth(cls, value: str) -> str:
        return value.strip().upper()


class ExhibitorPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    hall: HallLiteral | None = None
    booth_no: str | None = Field(default=None, min_length=5, max_length=10)
    category: CategoryLiteral | None = None
    target_industry: IndustryLiteral | None = None
    contact_name: str | None = Field(default=None, max_length=60)
    contact_title: str | None = Field(default=None, max_length=40)
    contact_phone: str | None = Field(default=None, max_length=32, pattern=r"^[0-9+\- ]{0,32}$")
    priority: PriorityLiteral | None = None
    dwell_min: int | None = Field(default=None, ge=3, le=60)
    appointment_at: datetime | None = None
    appointment_window_min: int | None = Field(default=None, ge=15, le=120)
    clear_appointment: bool = False
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("booth_no")
    @classmethod
    def _upper_booth(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value
