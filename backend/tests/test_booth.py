"""算法 A 单测：展位号解析、坐标、同馆/跨馆距离、成组建议、距离矩阵。"""
from __future__ import annotations

import pytest

from src.services import booth_service


def test_parse_booth_no_coordinates():
    position = booth_service.parse_booth_no("A1-023")
    assert position.hall == "A1"
    assert (position.row, position.col) == (2, 3)
    assert position.x == pytest.approx(9.6)
    assert position.y == pytest.approx(4.8)
    assert position.booth_no == "A1-023"


def test_parse_booth_no_is_case_insensitive():
    assert booth_service.parse_booth_no(" b2-091 ").hall == "B2"


@pytest.mark.parametrize("bad", ["A1-23", "E1-023", "A1-0a3", "", "A1-0039"])
def test_parse_rejects_bad_format(bad):
    with pytest.raises(booth_service.BoothFormatError):
        booth_service.parse_booth_no(bad)


def test_same_hall_uses_manhattan_distance():
    first = booth_service.parse_booth_no("A1-011")
    second = booth_service.parse_booth_no("A1-032")
    # A1-032 = 第 3 排第 2 列：dx = 3.2, dy = 4.8
    assert booth_service.walking_distance(first, second) == pytest.approx(8.0)


def test_cross_hall_adds_transfer_distance():
    first = booth_service.parse_booth_no("A1-011")
    other = booth_service.parse_booth_no("B2-011")
    expected = booth_service.gate_distance(first) + 150.0 + booth_service.gate_distance(other)
    assert booth_service.walking_distance(first, other) == pytest.approx(expected)
    assert booth_service.walking_distance(first, other) >= 150.0


def test_gate_distance():
    assert booth_service.gate_distance(booth_service.parse_booth_no("C1-021")) == pytest.approx(8.0)


def test_build_hall_groups_snake_order_and_invalid():
    rows = [
        {"id": 1, "hall": "A1", "booth_no": "A1-011", "priority": "P0"},
        {"id": 2, "hall": "A1", "booth_no": "A1-012", "priority": "P1"},
        {"id": 3, "hall": "A1", "booth_no": "A1-021", "priority": "P2"},
        {"id": 4, "hall": "A1", "booth_no": "A1-0X1", "priority": "P2"},
    ]
    result = booth_service.build_hall_groups(rows)
    hall = result["halls"][0]
    assert hall["count"] == 3
    assert len(result["invalid"]) == 1
    # 第 1 排从左到右，第 2 排反向
    assert [item["booth_no"] for item in hall["order"]] == ["A1-011", "A1-012", "A1-021"]
    assert result["transfer_m"] == 150.0


def test_distance_matrix_shape_and_flags():
    rows = [
        {"id": 1, "hall": "A1", "booth_no": "A1-011"},
        {"id": 2, "hall": "A1", "booth_no": "A1-012"},
        {"id": 3, "hall": "B1", "booth_no": "B1-011"},
    ]
    matrix = booth_service.distance_matrix(rows)
    assert matrix["ids"] == [1, 2, 3]
    assert len(matrix["cells"]) == 6
    same = [cell for cell in matrix["cells"] if cell["from_id"] == 1 and cell["to_id"] == 2][0]
    cross = [cell for cell in matrix["cells"] if cell["from_id"] == 1 and cell["to_id"] == 3][0]
    assert same["same_hall"] is True and same["distance_m"] < 10
    assert cross["same_hall"] is False and cross["distance_m"] > 150
