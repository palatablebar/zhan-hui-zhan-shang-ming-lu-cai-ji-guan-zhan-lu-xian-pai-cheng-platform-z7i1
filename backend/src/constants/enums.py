"""共享枚举（后端唯一定义处）。前端副本见 frontend/site/js/config.js。

README「共享枚举出现位置」一节列出全部出现点，改动需两侧同步。
"""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class Priority(StrEnum):
    """展商观展优先级。权重见 PRIORITY_WEIGHT（算法 B 使用）。"""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


PRIORITY_LABELS: dict[str, str] = {
    Priority.P0.value: "必看",
    Priority.P1.value: "重点",
    Priority.P2.value: "顺访",
}

PRIORITY_ORDER: list[str] = [Priority.P0.value, Priority.P1.value, Priority.P2.value]

PRIORITY_WEIGHT: dict[str, int] = {
    Priority.P0.value: 5,
    Priority.P1.value: 3,
    Priority.P2.value: 1,
}

PRIORITY_DWELL_MIN: dict[str, int] = {
    Priority.P0.value: 12,
    Priority.P1.value: 8,
    Priority.P2.value: 6,
}


class Hall(StrEnum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"
    D1 = "D1"
    D2 = "D2"


HALL_LABELS: dict[str, str] = {
    Hall.A1.value: "A1 · 工业机器人与智能装备",
    Hall.A2.value: "A2 · 机器视觉与传感",
    Hall.B1.value: "B1 · 传动与伺服",
    Hall.B2.value: "B2 · 电气与配电",
    Hall.C1.value: "C1 · 工业软件与数字化",
    Hall.C2.value: "C2 · 物流自动化与仓储",
    Hall.D1.value: "D1 · 检测测量与仪器",
    Hall.D2.value: "D2 · 新材料与工艺",
}

HALL_ORDER: list[str] = [hall.value for hall in Hall]


class Category(StrEnum):
    ROBOT = "robot"
    VISION = "vision"
    DRIVE = "drive"
    SENSOR = "sensor"
    SOFTWARE = "software"
    LOGISTICS = "logistics"
    ELECTRIC = "electric"
    METROLOGY = "metrology"


CATEGORY_LABELS: dict[str, str] = {
    Category.ROBOT.value: "工业机器人",
    Category.VISION.value: "机器视觉",
    Category.DRIVE.value: "传动伺服",
    Category.SENSOR.value: "传感仪表",
    Category.SOFTWARE.value: "工业软件",
    Category.LOGISTICS.value: "物流自动化",
    Category.ELECTRIC.value: "电气配电",
    Category.METROLOGY.value: "检测测量",
}

CATEGORY_ORDER: list[str] = [category.value for category in Category]


class TargetIndustry(StrEnum):
    AUTO = "auto"
    ELECTRONICS = "electronics"
    ENERGY = "energy"
    FOOD = "food"
    GENERAL = "general"
    PHARMA = "pharma"


TARGET_INDUSTRY_LABELS: dict[str, str] = {
    TargetIndustry.AUTO.value: "汽车零部件",
    TargetIndustry.ELECTRONICS.value: "3C 电子",
    TargetIndustry.ENERGY.value: "新能源",
    TargetIndustry.FOOD.value: "食品饮料",
    TargetIndustry.GENERAL.value: "通用制造",
    TargetIndustry.PHARMA.value: "医药包装",
}

TARGET_INDUSTRY_ORDER: list[str] = [item.value for item in TargetIndustry]


class RouteStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


ROUTE_STATUS_LABELS: dict[str, str] = {
    RouteStatus.QUEUED.value: "排队中",
    RouteStatus.RUNNING.value: "排程中",
    RouteStatus.SUCCESS.value: "成功",
    RouteStatus.PARTIAL.value: "部分成功",
    RouteStatus.FAILED.value: "失败",
}


class VisitStatus(StrEnum):
    PLANNED = "planned"
    CONFIRMED = "confirmed"
    ADJUSTED = "adjusted"
    DEFERRED = "deferred"


VISIT_STATUS_LABELS: dict[str, str] = {
    VisitStatus.PLANNED.value: "待确认",
    VisitStatus.CONFIRMED.value: "已确认",
    VisitStatus.ADJUSTED.value: "已调整",
    VisitStatus.DEFERRED.value: "已改期",
}

VISIT_STATUS_ORDER: list[str] = [
    VisitStatus.PLANNED.value,
    VisitStatus.CONFIRMED.value,
    VisitStatus.ADJUSTED.value,
    VisitStatus.DEFERRED.value,
]


class ConflictKind(StrEnum):
    APPOINTMENT = "appointment"
    OVERTIME = "overtime"


CONFLICT_KIND_LABELS: dict[str, str] = {
    ConflictKind.APPOINTMENT.value: "预约时段重叠",
    ConflictKind.OVERTIME.value: "超出当日时长",
}


class TriggerKind(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    SEED = "seed"


TRIGGER_LABELS: dict[str, str] = {
    TriggerKind.MANUAL.value: "手动",
    TriggerKind.SCHEDULE.value: "定时",
    TriggerKind.SEED.value: "初始化",
}


# 展会固定两天（2026 华南工业博览会），用于把「第几天 + 分钟」换算成绝对时间
SHOW_DAY_DATES: dict[int, str] = {
    1: "2026-11-18",
    2: "2026-11-19",
    3: "2026-11-20",
}

SHOW_DAY_LABELS: dict[int, str] = {
    1: "Day 1 · 11/18",
    2: "Day 2 · 11/19",
    3: "Day 3 · 11/20",
}
