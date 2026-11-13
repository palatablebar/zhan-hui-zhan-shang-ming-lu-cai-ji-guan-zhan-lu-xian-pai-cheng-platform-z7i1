"""批次补录 · 来源文件读取：官网补发的 CSV / JSON 行转成统一 dict 列表。

只读标准库，避免引入额外依赖；表头同时兼容中文与英文字段名。
调用方传入的路径视为不可信数据，本模块只做解析，不执行任何代码。
"""
from __future__ import annotations

import csv
import io
import json

# 表头别名 -> 系统字段名（小写、去空白后匹配）
HEADER_ALIASES: dict[str, str] = {
    "展商名称": "name",
    "公司名称": "name",
    "名称": "name",
    "name": "name",
    "馆号": "hall",
    "展馆": "hall",
    "hall": "hall",
    "展位号": "booth_no",
    "展位": "booth_no",
    "booth_no": "booth_no",
    "booth": "booth_no",
    "品类": "category",
    "category": "category",
    "目标行业": "target_industry",
    "行业": "target_industry",
    "target_industry": "target_industry",
    "联系人": "contact_name",
    "contact_name": "contact_name",
    "职务": "contact_title",
    "contact_title": "contact_title",
    "联系电话": "contact_phone",
    "电话": "contact_phone",
    "contact_phone": "contact_phone",
    "优先级": "priority",
    "priority": "priority",
    "停留分钟": "dwell_min",
    "dwell_min": "dwell_min",
    "预约时间": "appointment_at",
    "appointment_at": "appointment_at",
    "预约时长分钟": "appointment_window_min",
    "appointment_window_min": "appointment_window_min",
    "备注": "note",
    "note": "note",
}

REQUIRED_FIELDS = ("name", "booth_no")


class SourceReadError(ValueError):
    """来源文件无法解析（编码、格式或缺少必需列）。"""


def _normalize_header(text: str) -> str:
    return (text or "").strip().lstrip("﻿").lower()


def read_rows(path: str) -> list[dict]:
    """按扩展名读取 CSV 或 JSON，返回原始 dict 行（保留原值，清洗在 normalizer 完成）。"""
    lower = path.lower()
    if lower.endswith((".csv", ".txt")):
        return read_csv(path)
    if lower.endswith(".json"):
        return read_json(path)
    raise SourceReadError(f"不支持的来源文件类型：{path}（仅支持 .csv / .json）")


def read_csv(path: str) -> list[dict]:
    # utf-8-sig 兼容带 BOM 的官网导出；errors=strict 让乱码文件显式失败而非静默脏入
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read()
    if not sample.strip():
        return []
    reader = csv.reader(io.StringIO(sample))
    try:
        header = next(reader)
    except StopIteration:
        return []
    columns = [HEADER_ALIASES.get(_normalize_header(cell), "") for cell in header]
    if not any(columns):
        raise SourceReadError("CSV 表头无法识别，需包含展商名称/展位号等列")
    missing = [field for field in REQUIRED_FIELDS if field not in columns]
    if missing:
        raise SourceReadError(f"CSV 缺少必需列：{', '.join(missing)}")

    rows: list[dict] = []
    for raw in reader:
        if not any((cell or "").strip() for cell in raw):
            continue  # 跳过整行空白
        record: dict = {}
        for index, field_name in enumerate(columns):
            if not field_name:
                continue
            value = raw[index] if index < len(raw) else ""
            # 同名列以第一个非空值为准
            if field_name not in record or not str(record[field_name]).strip():
                record[field_name] = value
        rows.append(record)
    return rows


def read_json(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        payload = payload.get("rows") or payload.get("items") or payload.get("data")
    if not isinstance(payload, list):
        raise SourceReadError("JSON 顶层需为展商行数组，或含 rows/items/data 数组字段")
    rows: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            raise SourceReadError("JSON 数组的每一项必须是对象")
        rows.append({HEADER_ALIASES.get(_normalize_header(str(key)), key): value for key, value in item.items()})
    return rows


def source_sha256(path: str) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
