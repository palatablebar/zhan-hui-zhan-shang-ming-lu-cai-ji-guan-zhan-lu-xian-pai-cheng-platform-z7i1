"""批次补录 · 清洗与规范化（纯函数、无数据库依赖，可单测）。

负责把官网复制来的、展位号写法不一的原始行（如 ``A1-023`` / ``a1馆23号`` /
``A1-02-3``）规范化成系统统一口径，并给出隔离原因码，而不是让脏数据直接进库。
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

from src.constants.enums import (
    CATEGORY_ORDER,
    HALL_ORDER,
    PRIORITY_DWELL_MIN,
    PRIORITY_ORDER,
    TARGET_INDUSTRY_ORDER,
)
from src.services import booth_service

# ---- 隔离原因码（坏行隔离时写明原因，供前端/审计展示）----
REASON_BOOTH_FORMAT = "booth_format_invalid"          # 展位号无法识别
REASON_HALL_UNKNOWN = "hall_unknown"                  # 馆号不在 A1…D2
REASON_HALL_MISMATCH = "hall_booth_mismatch"          # 显式 hall 与展位号解析出的馆不一致
REASON_NAME_MISSING = "name_missing"                  # 展商名称为空
REASON_PRIORITY_INVALID = "priority_invalid"          # 优先级不在 P0/P1/P2
REASON_CATEGORY_INVALID = "category_invalid"          # 品类非法
REASON_INDUSTRY_INVALID = "industry_invalid"          # 目标行业非法
REASON_DUPLICATE_BATCH = "duplicate_booth_in_batch"   # 同批同馆同展位重复
REASON_APPOINTMENT_INVALID = "appointment_invalid"    # 预约时间无法解析或不在展期
REASON_PHONE_INVALID = "phone_invalid"                # 联系电话含非法字符

REASON_LABELS: dict[str, str] = {
    REASON_BOOTH_FORMAT: "展位号格式无法识别",
    REASON_HALL_UNKNOWN: "馆号不在 A1…D2 范围",
    REASON_HALL_MISMATCH: "馆号字段与展位号所属馆不一致",
    REASON_NAME_MISSING: "展商名称缺失",
    REASON_PRIORITY_INVALID: "优先级非法（仅允许 P0/P1/P2）",
    REASON_CATEGORY_INVALID: "品类非法",
    REASON_INDUSTRY_INVALID: "目标行业非法",
    REASON_DUPLICATE_BATCH: "同批次内同馆同展位重复",
    REASON_APPOINTMENT_INVALID: "预约时间无法解析或不在展期 09:00-18:00",
    REASON_PHONE_INVALID: "联系电话含非法字符",
}

_PHONE_PATTERN = re.compile(r"^[0-9+\- ]*$")
_HALL_TOKEN = re.compile(r"^[A-D][1-2]$")
# 形如 A1馆23号 / a1 馆 02-3 / A1－023 里的馆字母+数字
_HALL_PREFIX = re.compile(r"^(?P<hall>[A-Da-d][1-2])")


@dataclass
class NormalizedRow:
    """一行原始数据的规范化结果。"""

    row_no: int
    raw: dict
    cleaned: dict = field(default_factory=dict)
    booth_no: str | None = None
    hall: str | None = None
    row: int | None = None
    col: int | None = None
    reason_codes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.reason_codes


def normalize_text(value: object) -> str:
    """全角转半角、统一大小写与空白；None -> 空串。"""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    return text.strip()


def normalize_booth(raw_booth: object, raw_hall: object = "") -> tuple[dict | None, list[str]]:
    """把各种展位号写法规范化为 (hall, booth_no, row, col)。

    支持：``A1-023``、``a1馆23号``、``A1馆02排3号``、``A1-02-3``、``A1－023``、
    全角字符等。无法确定馆号或排/列时返回原因码而不猜测，避免错并入相邻展位。
    """
    reasons: list[str] = []
    text = normalize_text(raw_booth).upper()
    explicit_hall = normalize_text(raw_hall).upper()
    if not text:
        return None, [REASON_BOOTH_FORMAT]

    match = _HALL_PREFIX.match(text)
    if not match:
        return None, [REASON_BOOTH_FORMAT]
    hall = match.group("hall").upper()
    if hall not in HALL_ORDER:
        return None, [REASON_HALL_UNKNOWN]
    if explicit_hall and explicit_hall != hall:
        # 显式填写的 hall 与展位号自身馆号不一致，属坏行，不擅自二选一
        reasons.append(REASON_HALL_MISMATCH)

    tail = text[match.end():]
    # 去掉「馆 / 排 / 号 / 位」等中文与分隔符，只保留数字，再按排、列还原
    digits = re.findall(r"\d+", tail)
    joined = "".join(digits)
    if not joined:
        return None, reasons + [REASON_BOOTH_FORMAT]

    row: int | None = None
    col: int | None = None
    if len(digits) == 1:
        # 「23」「023」：约定末位为列、其余为排（A1馆23号 -> 02 排 3 列）
        if len(joined) < 2:
            return None, reasons + [REASON_BOOTH_FORMAT]
        row, col = int(joined[:-1]), int(joined[-1])
    elif len(digits) == 2:
        # 「02-3」「02，03」：两段即排、列
        row, col = int(digits[0]), int(digits[1])
    else:
        return None, reasons + [REASON_BOOTH_FORMAT]

    if row is None or col is None or row < 1 or col < 1:
        return None, reasons + [REASON_BOOTH_FORMAT]

    candidate = f"{hall}-{row:02d}{col}"
    try:
        position = booth_service.parse_booth_no(candidate)
    except booth_service.BoothFormatError:
        return None, reasons + [REASON_BOOTH_FORMAT]
    if reasons:
        return None, reasons
    return (
        {
            "hall": position.hall,
            "booth_no": position.booth_no,
            "row": position.row,
            "col": position.col,
            "x": position.x,
            "y": position.y,
        },
        [],
    )


def _clean_priority(value: str) -> tuple[str | None, list[str]]:
    token = normalize_text(value).upper()
    if not token:
        return "P2", []  # 与登记接口一致的默认值
    if token not in PRIORITY_ORDER:
        return None, [REASON_PRIORITY_INVALID]
    return token, []


def _clean_choice(value: str, allowed: list[str], reason: str, default: str | None = None) -> tuple[str | None, list[str]]:
    token = normalize_text(value).lower()
    if not token:
        return default, []
    if token not in allowed:
        return None, [reason]
    return token, []


def normalize_row(row_no: int, raw: dict) -> NormalizedRow:
    """清洗并校验一行；任何字段不合法都会累积原因码（坏行可同时有多个问题）。"""
    result = NormalizedRow(row_no=row_no, raw=dict(raw))
    reasons: list[str] = []

    name = normalize_text(raw.get("name"))
    if len(name) < 2:
        reasons.append(REASON_NAME_MISSING)

    booth, booth_reasons = normalize_booth(raw.get("booth_no"), raw.get("hall"))
    reasons.extend(booth_reasons)

    priority, r = _clean_priority(raw.get("priority"))
    reasons.extend(r)
    category, r = _clean_choice(raw.get("category"), CATEGORY_ORDER, REASON_CATEGORY_INVALID, default="robot")
    reasons.extend(r)
    industry, r = _clean_choice(
        raw.get("target_industry"), TARGET_INDUSTRY_ORDER, REASON_INDUSTRY_INVALID, default="general"
    )
    reasons.extend(r)

    phone = normalize_text(raw.get("contact_phone"))
    if phone and not _PHONE_PATTERN.match(phone):
        reasons.append(REASON_PHONE_INVALID)
        phone = ""

    appointment_at = None
    appointment_text = normalize_text(raw.get("appointment_at"))
    if appointment_text:
        appointment_at, appt_reason = _parse_appointment(appointment_text)
        reasons.extend(appt_reason)

    # 去重后保留稳定原因码顺序
    result.reason_codes = list(dict.fromkeys(reasons))
    if result.reason_codes:
        return result

    assert booth is not None and priority and category and industry
    dwell_raw = normalize_text(raw.get("dwell_min"))
    dwell_min = int(PRIORITY_DWELL_MIN[priority])
    if dwell_raw.isdigit():
        dwell_min = max(3, min(60, int(dwell_raw)))

    result.booth_no = booth["booth_no"]
    result.hall = booth["hall"]
    result.row = booth["row"]
    result.col = booth["col"]
    result.cleaned = {
        "name": name,
        "hall": booth["hall"],
        "booth_no": booth["booth_no"],
        "row_no": booth["row"],
        "col_no": booth["col"],
        "category": category,
        "target_industry": industry,
        "contact_name": normalize_text(raw.get("contact_name"))[:60],
        "contact_title": normalize_text(raw.get("contact_title"))[:40],
        "contact_phone": phone[:32],
        "priority": priority,
        "dwell_min": dwell_min,
        "appointment_at": appointment_at,
        "appointment_window_min": _clean_window(raw.get("appointment_window_min")),
        "note": normalize_text(raw.get("note")) or None,
    }
    return result


def _clean_window(value: object) -> int:
    text = normalize_text(value)
    if not text.isdigit():
        return 30
    return max(15, min(120, int(text)))


def _parse_appointment(text: str):
    """解析 ISO 或 ``YYYY/MM/DD HH:MM`` 预约时间，并校验展期与 09:00-18:00 窗口。"""
    from datetime import datetime

    from src.constants.enums import SHOW_DAY_DATES
    from src.services.exhibitor_service import _apply_appointment  # 复用同一套硬窗口口径

    parsed = None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        return None, [REASON_APPOINTMENT_INVALID]
    if parsed.date().isoformat() not in SHOW_DAY_DATES.values():
        return None, [REASON_APPOINTMENT_INVALID]

    class _Probe:
        appointment_day = None
        appointment_start_min = None
        appointment_end_min = None
        appointment_at = None

    probe = _Probe()
    try:
        _apply_appointment(probe, parsed, 30)
    except Exception:  # noqa: BLE001 - 口径异常统一转成隔离原因
        return None, [REASON_APPOINTMENT_INVALID]
    return parsed, []


def row_fingerprint(cleaned: dict) -> str:
    """规范化行的内容指纹：用于人工修改识别与重复批次判定（不含易变空白）。"""
    payload = {key: cleaned.get(key) for key in sorted(cleaned) if key != "appointment_window_min"}
    if isinstance(payload.get("appointment_at"), datetime):
        payload["appointment_at"] = payload["appointment_at"].isoformat(timespec="minutes")
    raw = repr(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
