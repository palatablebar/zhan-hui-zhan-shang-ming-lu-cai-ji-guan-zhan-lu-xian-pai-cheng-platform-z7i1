"""算法 A：展位坐标解析、步行距离与「同馆成组」建议。

口径（README §10 与前端展馆平面图共用）：
- 展位号 `馆号-排号(两位)+列号(一位)`，例如 `A1-023` = A1 馆第 02 排第 3 列；
- 馆内坐标 `x = 列号 * 3.2m`，`y = 排号 * 2.4m`；
- 同馆：曼哈顿距离 |dx| + |dy|；
- 跨馆：各自到本馆大门（坐标原点）的曼哈顿距离 + 150m 换乘 + 对方到馆大门距离。

纯函数、无数据库依赖，可单独单测。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

COL_WIDTH_M = 3.2
ROW_DEPTH_M = 2.4
HALL_TRANSFER_M = 150.0
MIN_LEG_M = 0.0
BOOTH_PATTERN = re.compile(r"^(?P<hall>[A-D][1-2])-(?P<row>\d{2})(?P<col>\d)$")


class BoothFormatError(ValueError):
    """展位号不符合 `A1-023` 约定。"""


@dataclass(frozen=True)
class BoothPosition:
    hall: str
    row: int
    col: int
    x: float
    y: float

    @property
    def booth_no(self) -> str:
        return f"{self.hall}-{self.row:02d}{self.col}"


def parse_booth_no(booth_no: str) -> BoothPosition:
    text = (booth_no or "").strip().upper()
    match = BOOTH_PATTERN.match(text)
    if match is None:
        raise BoothFormatError(f"展位号不合法：{booth_no!r}，应形如 A1-023")
    row = int(match.group("row"))
    col = int(match.group("col"))
    if row < 1 or col < 1:
        raise BoothFormatError(f"展位排号/列号必须从 1 开始：{booth_no!r}")
    return BoothPosition(
        hall=match.group("hall"),
        row=row,
        col=col,
        x=round(col * COL_WIDTH_M, 3),
        y=round(row * ROW_DEPTH_M, 3),
    )


def gate_distance(position: BoothPosition) -> float:
    """展位到本馆大门（原点）的曼哈顿距离。"""
    return round(abs(position.x) + abs(position.y), 3)


def walking_distance(a: BoothPosition, b: BoothPosition) -> float:
    """两个展位之间的步行距离（m）。"""
    if a.hall == b.hall:
        return round(abs(a.x - b.x) + abs(a.y - b.y), 3)
    return round(gate_distance(a) + HALL_TRANSFER_M + gate_distance(b), 3)


def walking_minutes(distance_m: float, speed_m_per_min: float = 55.0) -> float:
    if speed_m_per_min <= 0:
        raise ValueError("步行速度必须为正数")
    return round(distance_m / speed_m_per_min, 4)


def _snake_rows(rows: list[dict]) -> list[dict]:
    """同一排按列升序、相邻排反向，形成蛇形走位，减少回头路。"""
    ordered: list[dict] = []
    for index, row_no in enumerate(sorted({row["row"] for row in rows})):
        same_row = sorted((row for row in rows if row["row"] == row_no), key=lambda item: item["col"])
        if index % 2 == 1:
            same_row.reverse()
        ordered.extend(same_row)
    return ordered


def build_hall_groups(exhibitors: list[dict]) -> dict:
    """按馆分组，输出蛇形建议顺序、馆内跨度与同馆成组建议。

    exhibitors 每项至少包含 id / hall / booth_no / priority，可选 name。
    """
    parsed: list[dict] = []
    invalid: list[dict] = []
    for item in exhibitors:
        try:
            position = parse_booth_no(item.get("booth_no", ""))
        except BoothFormatError as exc:
            invalid.append({"id": item.get("id"), "booth_no": item.get("booth_no"), "error": str(exc)})
            continue
        parsed.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "booth_no": position.booth_no,
                "priority": item.get("priority"),
                "hall": position.hall,
                "row": position.row,
                "col": position.col,
                "x": position.x,
                "y": position.y,
            }
        )

    halls: list[dict] = []
    for hall in sorted({item["hall"] for item in parsed}):
        rows = [item for item in parsed if item["hall"] == hall]
        ordered = _snake_rows(rows)
        walk = 0.0
        for previous, current in zip(ordered, ordered[1:]):
            walk += walking_distance(
                BoothPosition(previous["hall"], previous["row"], previous["col"], previous["x"], previous["y"]),
                BoothPosition(current["hall"], current["row"], current["col"], current["x"], current["y"]),
            )
        row_summary: dict[int, list[int]] = {}
        for item in rows:
            row_summary.setdefault(item["row"], []).append(item["col"])
        halls.append(
            {
                "hall": hall,
                "count": len(rows),
                "row_count": len(row_summary),
                "span_x_m": round(max(item["x"] for item in rows), 1),
                "span_y_m": round(max(item["y"] for item in rows), 1),
                "avg_gate_m": round(sum(gate_distance(BoothPosition(item["hall"], item["row"], item["col"], item["x"], item["y"])) for item in rows) / len(rows), 1),
                "snake_walk_m": round(walk, 1),
                "rows": [
                    {"row": row_no, "cols": sorted(cols), "count": len(cols)}
                    for row_no, cols in sorted(row_summary.items())
                ],
                "order": [
                    {"id": item["id"], "booth_no": item["booth_no"], "priority": item["priority"], "row": item["row"], "col": item["col"]}
                    for item in ordered
                ],
            }
        )
    return {
        "halls": halls,
        "transfer_m": HALL_TRANSFER_M,
        "col_width_m": COL_WIDTH_M,
        "row_depth_m": ROW_DEPTH_M,
        "invalid": invalid,
    }


def distance_matrix(exhibitors: list[dict]) -> dict:
    """N×N 距离矩阵（同馆曼哈顿 / 跨馆 150m 换乘）。"""
    positions: list[tuple[int, BoothPosition]] = []
    invalid: list[dict] = []
    for item in exhibitors:
        try:
            positions.append((int(item["id"]), parse_booth_no(item.get("booth_no", ""))))
        except (BoothFormatError, TypeError, ValueError) as exc:
            invalid.append({"id": item.get("id"), "booth_no": item.get("booth_no"), "error": str(exc)})
    cells: list[dict] = []
    for source_id, source_pos in positions:
        for target_id, target_pos in positions:
            if source_id == target_id:
                continue
            distance = walking_distance(source_pos, target_pos)
            cells.append(
                {
                    "from_id": source_id,
                    "to_id": target_id,
                    "distance_m": distance,
                    "same_hall": source_pos.hall == target_pos.hall,
                    "walk_min": round(distance / 55.0, 1),
                }
            )
    grouped: list[dict] = []
    for source_id, source_pos in positions:
        same_hall = [
            cell for cell in cells if cell["from_id"] == source_id and cell["same_hall"]
        ]
        grouped.append(
            {
                "id": source_id,
                "hall": source_pos.hall,
                "booth_no": source_pos.booth_no,
                "x": source_pos.x,
                "y": source_pos.y,
                "same_hall_min_m": min((cell["distance_m"] for cell in same_hall), default=None),
                "same_hall_count": len(same_hall),
            }
        )
    return {
        "ids": [item[0] for item in positions],
        "positions": grouped,
        "cells": cells,
        "invalid": invalid,
        "transfer_m": HALL_TRANSFER_M,
    }
