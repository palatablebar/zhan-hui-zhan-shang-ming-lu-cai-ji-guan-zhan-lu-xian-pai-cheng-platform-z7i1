"""批次补录 · 清洗规范化与来源读取单测（纯函数，无数据库）。"""
from __future__ import annotations

import json

import pytest

from src.services.batch_import import normalizer as N
from src.services.batch_import import readers


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("A1-023", "A1-023"),
        ("a1馆23号", "A1-023"),
        ("A1馆02排3号", "A1-023"),
        ("A1-02-3", "A1-023"),
        ("A1－023", "A1-023"),  # 全角连字符
        ("  b2-091  ", "B2-091"),
        ("Ｂ１－０１２", "B1-012"),  # 全角字母数字
    ],
)
def test_booth_formats_normalize_to_canonical(raw, expected):
    booth, reasons = N.normalize_booth(raw)
    assert reasons == []
    assert booth["booth_no"] == expected
    assert booth["hall"] == expected.split("-")[0]


@pytest.mark.parametrize("raw", ["E1-023", "A1-0a3", "", "A1馆", "Z9-011", "A1-9"])
def test_bad_booth_is_quarantined_not_guessed(raw):
    booth, reasons = N.normalize_booth(raw)
    assert booth is None
    assert N.REASON_BOOTH_FORMAT in reasons or N.REASON_HALL_UNKNOWN in reasons


def test_compact_number_booth_is_recovered_by_documented_rule():
    # 「A1-23」按「末位列、其余排」规则恢复为 A1-023（README 痛点里的写法之一）
    booth, reasons = N.normalize_booth("A1-23")
    assert reasons == []
    assert booth["booth_no"] == "A1-023"


def test_explicit_hall_mismatch_is_flagged():
    booth, reasons = N.normalize_booth("A1-023", "A2")
    assert booth is None
    assert N.REASON_HALL_MISMATCH in reasons


def test_normalize_row_collects_multiple_reasons():
    row = N.normalize_row(1, {"name": "X", "booth_no": "BAD", "priority": "P9", "category": "nope"})
    assert not row.ok
    assert N.REASON_BOOTH_FORMAT in row.reason_codes
    assert N.REASON_PRIORITY_INVALID in row.reason_codes
    assert N.REASON_CATEGORY_INVALID in row.reason_codes


def test_normalize_row_good_case_defaults_and_cleaning():
    row = N.normalize_row(
        2,
        {
            "name": "  恒擎智能装备  ",
            "hall": "a1",
            "booth_no": "a1馆23号",
            "priority": "p0",
            "category": "robot",
            "target_industry": "auto",
            "contact_phone": "138-0000-1234",
        },
    )
    assert row.ok, row.reason_codes
    assert row.cleaned["name"] == "恒擎智能装备"
    assert row.cleaned["booth_no"] == "A1-023"
    assert row.cleaned["priority"] == "P0"
    # P0 默认停留 12 分钟（与 PRIORITY_DWELL_MIN 对齐）
    assert row.cleaned["dwell_min"] == 12
    # 规范化结果可稳定生成内容指纹
    assert len(N.row_fingerprint(row.cleaned)) == 64


def test_invalid_phone_is_quarantined():
    row = N.normalize_row(1, {"name": "测试公司甲", "booth_no": "A1-011", "contact_phone": "abc123"})
    assert N.REASON_PHONE_INVALID in row.reason_codes


def test_appointment_outside_show_days_rejected():
    row = N.normalize_row(
        1, {"name": "测试公司乙", "booth_no": "A1-011", "appointment_at": "2030-01-01 10:00"}
    )
    assert N.REASON_APPOINTMENT_INVALID in row.reason_codes


def test_appointment_inside_show_days_accepted():
    row = N.normalize_row(
        1, {"name": "测试公司丙", "booth_no": "A1-011", "appointment_at": "2026-11-18 10:30"}
    )
    assert row.ok, row.reason_codes
    assert row.cleaned["appointment_at"] is not None


def test_fingerprint_stable_and_distinguishes_content():
    base = {"name": "甲", "hall": "A1", "booth_no": "A1-011", "priority": "P1", "category": "robot",
            "target_industry": "general", "contact_phone": "", "row_no": 1, "col_no": 1, "dwell_min": 8,
            "contact_name": "", "contact_title": "", "note": None}
    fp1 = N.row_fingerprint(base)
    fp2 = N.row_fingerprint(dict(base))
    changed = dict(base, priority="P0")
    fp3 = N.row_fingerprint(changed)
    assert fp1 == fp2
    assert fp1 != fp3


def test_csv_reader_accepts_chinese_headers_and_bom(tmp_path):
    path = tmp_path / "batch.csv"
    path.write_text(
        "﻿展商名称,馆号,展位号,优先级,品类\n"
        "甲公司,A1,A1馆23号,P0,robot\n"
        "乙公司,B2,b2-091,P1,vision\n",
        encoding="utf-8",
    )
    rows = readers.read_rows(str(path))
    assert len(rows) == 2
    assert rows[0]["name"] == "甲公司"
    assert rows[0]["booth_no"] == "A1馆23号"
    assert rows[1]["hall"] == "B2"


def test_csv_reader_missing_required_column_raises(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("馆号,品类\nA1,robot\n", encoding="utf-8")
    with pytest.raises(readers.SourceReadError):
        readers.read_rows(str(path))


def test_json_reader_supports_rows_wrapper(tmp_path):
    path = tmp_path / "batch.json"
    path.write_text(
        json.dumps({"rows": [{"name": "丙公司", "hall": "C1", "booth_no": "C1-032", "category": "software"}]}),
        encoding="utf-8",
    )
    rows = readers.read_rows(str(path))
    assert rows == [{"name": "丙公司", "hall": "C1", "booth_no": "C1-032", "category": "software"}]
