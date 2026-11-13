"""算法 B：带时间窗的两日观展路线排程（纯函数，可单测）。

口径（README §10）：
- 每天可用 480 分钟（默认 09:00 入场），权重 P0=5 / P1=3 / P2=1；
- 预约时段是硬窗：到访必须落在 [appointment_start, appointment_end] 内；
- 先按预约锚点落位，再按「权重 / 插入增量距离」贪心插入其余展商，最后 2-opt 改进馆内顺序；
- 预约窗口重叠 → 冲突双方都打标记，只保留权重高者，另一个转「改期」；
- 输出：两日路线（含 ETA / 步行增量）、总步行、覆盖权重、冲突与超时项。

不依赖数据库，也不做任何网络访问；同样输入两次结果逐字一致。
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from src.constants.enums import (
    CONFLICT_KIND_LABELS,
    PRIORITY_WEIGHT,
    VISIT_STATUS_LABELS,
)
from src.services import booth_service

DEFAULT_DAY_MINUTES = 480
DEFAULT_DAY_START_MINUTE = 540  # 09:00
DEFAULT_SPEED_M_PER_MIN = 55.0
DEFAULT_PRIORITIES = ("P0", "P1")
MIN_INSERT_DELTA_M = 10.0
DEFERRED_SEQ_BASE = 9000

_WEIGHT = PRIORITY_WEIGHT


@dataclass
class Candidate:
    exhibitor_id: int
    name: str
    hall: str
    booth_no: str
    priority: str
    dwell_min: int
    weight: int
    position: booth_service.BoothPosition
    appt_day: int | None = None
    appt_start: int | None = None
    appt_end: int | None = None
    conflict: bool = False
    conflict_kind: str | None = None
    conflict_note: str | None = None
    status: str = "planned"

    @property
    def is_anchor(self) -> bool:
        return self.appt_day is not None and self.appt_start is not None


def format_minute(minute: int) -> str:
    """把「当天第几分钟」转成 HH:MM。"""
    minute = int(round(minute))
    return f"{minute // 60:02d}:{minute % 60:02d}"


def build_candidate(row: dict, *, default_dwell: int | None = None) -> Candidate:
    """把一行展商数据转成排程候选。展位号非法会抛 BoothFormatError。"""
    position = booth_service.parse_booth_no(row.get("booth_no", ""))
    priority = str(row.get("priority") or "P2").upper()
    if priority not in _WEIGHT:
        raise ValueError(f"未知优先级：{priority}")
    dwell = row.get("dwell_min")
    if dwell is None:
        dwell = default_dwell if default_dwell is not None else 8
    return Candidate(
        exhibitor_id=int(row["id"]),
        name=str(row.get("name") or ""),
        hall=position.hall,
        booth_no=position.booth_no,
        priority=priority,
        dwell_min=int(dwell),
        weight=_WEIGHT[priority],
        position=position,
        appt_day=_optional_int(row.get("appointment_day")),
        appt_start=_optional_int(row.get("appointment_start_min")),
        appt_end=_optional_int(row.get("appointment_end_min")),
    )


def _optional_int(value) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


@dataclass
class _Timeline:
    feasible: bool
    eta: list[int] = field(default_factory=list)
    walk_m: float = 0.0
    legs: list[float] = field(default_factory=list)
    end_min: int = 0
    conflict_flags: list[bool] = field(default_factory=list)


def _travel(previous: Candidate | None, current: Candidate, speed: float) -> float:
    if previous is None:
        return booth_service.gate_distance(current.position) / speed
    return booth_service.walking_distance(previous.position, current.position) / speed


def evaluate_order(
    order: list[Candidate],
    day: int,
    *,
    day_start_minute: int = DEFAULT_DAY_START_MINUTE,
    day_minutes: int = DEFAULT_DAY_MINUTES,
    speed: float = DEFAULT_SPEED_M_PER_MIN,
) -> _Timeline:
    """按给定顺序走一遍，返回 ETA / 步行距离；硬窗或当日时长不满足则不可行。"""
    clock = float(day_start_minute)
    previous: Candidate | None = None
    total_walk = 0.0
    etas: list[int] = []
    legs: list[float] = []
    for item in order:
        if previous is None:
            distance = booth_service.gate_distance(item.position)
        else:
            distance = booth_service.walking_distance(previous.position, item.position)
        travel = distance / speed
        arrival = clock + travel
        start = arrival
        if item.is_anchor and item.appt_day == day:
            window_start = float(item.appt_start or 0)
            window_end = float(item.appt_end if item.appt_end is not None else window_start + item.dwell_min)
            if start < window_start:
                start = window_start
            if start + item.dwell_min > window_end + 1e-6:
                return _Timeline(feasible=False)
        end = start + item.dwell_min
        total_walk += distance
        legs.append(round(distance, 3))
        etas.append(int(round(start)))
        clock = end
        previous = item
    if clock > day_start_minute + day_minutes + 1e-6:
        return _Timeline(feasible=False)
    return _Timeline(
        feasible=True,
        eta=etas,
        walk_m=round(total_walk, 3),
        legs=legs,
        end_min=int(round(clock)),
    )


def _anchor_clusters(anchors: list[Candidate]) -> list[list[Candidate]]:
    ordered = sorted(anchors, key=lambda item: (item.appt_start or 0, -item.weight, item.exhibitor_id))
    clusters: list[list[Candidate]] = []
    cluster_end = -1.0
    for anchor in ordered:
        start = float(anchor.appt_start or 0)
        if clusters and start < cluster_end - 1e-6:
            clusters[-1].append(anchor)
            cluster_end = max(cluster_end, float(anchor.appt_end or start + anchor.dwell_min))
        else:
            clusters.append([anchor])
            cluster_end = float(anchor.appt_end or start + anchor.dwell_min)
    return clusters


def _resolve_anchor_conflicts(candidates: list[Candidate], day_count: int) -> tuple[dict[int, list[Candidate]], list[Candidate]]:
    """把预约展商按天落位，窗口重叠的只留权重高者，并给双方打冲突标记。"""
    anchors_by_day: dict[int, list[Candidate]] = {day: [] for day in range(1, day_count + 1)}
    deferred: list[Candidate] = []
    for candidate in candidates:
        if not candidate.is_anchor:
            continue
        if candidate.appt_day not in anchors_by_day:
            candidate.conflict = True
            candidate.conflict_kind = "overtime"
            candidate.conflict_note = f"预约在展期第 {candidate.appt_day} 天，超出本次 {day_count} 天排程"
            candidate.status = "deferred"
            deferred.append(candidate)
            continue
        anchors_by_day[candidate.appt_day].append(candidate)

    for day, anchors in anchors_by_day.items():
        accepted: list[Candidate] = []
        for cluster in _anchor_clusters(anchors):
            if len(cluster) == 1:
                accepted.append(cluster[0])
                continue
            winner = sorted(cluster, key=lambda item: (-item.weight, item.appt_start or 0, item.exhibitor_id))[0]
            others = [item for item in cluster if item is not winner]
            winner.conflict = True
            winner.conflict_kind = "appointment"
            winner.conflict_note = "与 " + "、".join(f"{item.name}({item.booth_no})" for item in others) + " 的预约时段重叠，保留权重高者"
            accepted.append(winner)
            for loser in others:
                loser.conflict = True
                loser.conflict_kind = "appointment"
                loser.conflict_note = f"与 {winner.name}({winner.booth_no}) 预约时段重叠，权重较低转为改期"
                loser.status = "deferred"
                deferred.append(loser)
        accepted.sort(key=lambda item: (item.appt_start or 0, item.exhibitor_id))
        anchors_by_day[day] = accepted
    return anchors_by_day, deferred


def _drop_infeasible_anchor(
    order: list[Candidate],
    day: int,
    ctx: dict,
    deferred: list[Candidate],
) -> tuple[list[Candidate], _Timeline | None]:
    """预约锚点本身超出当日时长时，逐个丢弃权重最低者直到可行。"""
    result = evaluate_order(order, day, **ctx)
    while result is not None and not result.feasible and any(item.is_anchor for item in order):
        droppable = [item for item in order if item.is_anchor]
        victim = sorted(droppable, key=lambda item: (item.weight, item.exhibitor_id))[0]
        victim.conflict = True
        victim.conflict_kind = "overtime"
        victim.conflict_note = f"预约窗口 {format_minute(victim.appt_start or 0)} 导致当日超出 {ctx['day_minutes']} 分钟"
        victim.status = "deferred"
        deferred.append(victim)
        order = [item for item in order if item is not victim]
        result = evaluate_order(order, day, **ctx)
    return order, result


def _greedy_fill(
    order: list[Candidate],
    day: int,
    ctx: dict,
    fillers: list[Candidate],
) -> tuple[list[Candidate], _Timeline | None, list[Candidate]]:
    current = evaluate_order(order, day, **ctx)
    if current is None or not current.feasible:
        return order, current, []
    placed: list[Candidate] = []
    for candidate in fillers:
        best: tuple[float, float, int, int, list[Candidate], _Timeline] | None = None
        for position in range(len(order) + 1):
            trial = order[:position] + [candidate] + order[position:]
            result = evaluate_order(trial, day, **ctx)
            if result is None or not result.feasible:
                continue
            delta = max(result.walk_m - current.walk_m, MIN_INSERT_DELTA_M)
            score = candidate.weight / delta
            if best is None or (score, delta) > (best[0], best[1]) + (1e-12, 1e-12):
                best = (score, delta, position, candidate.exhibitor_id, trial, result)
        if best is None:
            continue
        order = best[4]
        current = best[5]
        placed.append(candidate)
    return order, current, placed


def _two_opt(order: list[Candidate], day: int, ctx: dict, rounds: int = 24) -> tuple[list[Candidate], _Timeline | None]:
    best = list(order)
    best_result = evaluate_order(best, day, **ctx)
    if best_result is None or not best_result.feasible:
        return best, best_result
    improved = True
    tick = 0
    while improved and tick < rounds:
        improved = False
        tick += 1
        length = len(best)
        for i in range(length - 1):
            if best[i].is_anchor:
                continue
            for j in range(i + 1, length):
                if best[j].is_anchor:
                    continue
                if any(item.is_anchor for item in best[i : j + 1]):
                    continue
                trial = best[:i] + list(reversed(best[i : j + 1])) + best[j + 1 :]
                result = evaluate_order(trial, day, **ctx)
                if result is not None and result.feasible and result.walk_m < best_result.walk_m - 1e-6:
                    best, best_result = trial, result
                    improved = True
    return best, best_result


def plan_routes(
    candidates: list[Candidate],
    *,
    day_count: int = 2,
    day_minutes: int = DEFAULT_DAY_MINUTES,
    day_start_minute: int = DEFAULT_DAY_START_MINUTE,
    speed: float = DEFAULT_SPEED_M_PER_MIN,
    priorities: tuple[str, ...] | list[str] = DEFAULT_PRIORITIES,
    max_visits: int | None = None,
) -> dict:
    """排两日路线，返回 visits / metrics / log / status（纯函数）。"""
    if day_count < 1:
        raise ValueError("day_count 至少为 1")
    allowed = {str(item).upper() for item in priorities}
    pool = [replace(item) for item in candidates if item.priority in allowed]
    pool.sort(key=lambda item: (-item.weight, item.priority, item.exhibitor_id))

    anchors_by_day, deferred = _resolve_anchor_conflicts(pool, day_count)
    anchor_ids = {item.exhibitor_id for day in anchors_by_day.values() for item in day}
    deferred_ids = {item.exhibitor_id for item in deferred}
    fillers = [item for item in pool if item.exhibitor_id not in anchor_ids and item.exhibitor_id not in deferred_ids]
    fillers.sort(key=lambda item: (-item.weight, item.exhibitor_id))

    ctx = {
        "day_start_minute": day_start_minute,
        "day_minutes": day_minutes,
        "speed": speed,
    }
    day_orders: dict[int, list[Candidate]] = {}
    day_results: dict[int, _Timeline | None] = {}
    dropped_ids: set[int] = set()
    placed_ids: set[int] = set()
    for day in range(1, day_count + 1):
        order = list(anchors_by_day[day])
        before = {item.exhibitor_id for item in order}
        order, result = _drop_infeasible_anchor(order, day, ctx, deferred)
        dropped_ids |= before - {item.exhibitor_id for item in order}
        available = [
            item
            for item in fillers
            if item.exhibitor_id not in placed_ids and item.exhibitor_id not in dropped_ids
        ]
        order, result, placed = _greedy_fill(order, day, ctx, available)
        placed_ids |= {item.exhibitor_id for item in placed}
        order, result = _two_opt(order, day, ctx)
        day_orders[day] = order
        day_results[day] = result

    visits: list[dict] = []
    total_walk = 0.0
    total_dwell = 0
    covered_weight = 0
    by_day: list[dict] = []
    for day in range(1, day_count + 1):
        order = day_orders[day]
        result = day_results[day]
        if result is None or not result.feasible:
            by_day.append({"day": day, "visits": 0, "walk_m": 0.0, "dwell_min": 0, "end_eta": None, "util_pct": 0.0})
            continue
        for index, item in enumerate(order, start=1):
            visits.append(
                {
                    "exhibitor_id": item.exhibitor_id,
                    "day": day,
                    "seq": index,
                    "eta_min": result.eta[index - 1],
                    "eta_label": format_minute(result.eta[index - 1]),
                    "dwell_min": item.dwell_min,
                    "walk_before_m": round(result.legs[index - 1], 1),
                    "conflict": item.conflict,
                    "conflict_kind": item.conflict_kind,
                    "conflict_note": item.conflict_note,
                    "status": item.status,
                    "priority": item.priority,
                    "weight": item.weight,
                }
            )
        total_walk += result.walk_m
        dwell = sum(item.dwell_min for item in order)
        total_dwell += dwell
        covered_weight += sum(item.weight for item in order)
        by_day.append(
            {
                "day": day,
                "visits": len(order),
                "walk_m": round(result.walk_m, 1),
                "dwell_min": dwell,
                "end_eta": format_minute(result.end_min),
                "util_pct": round(100 * ((result.end_min - day_start_minute) / day_minutes), 1),
            }
        )

    for index, item in enumerate(deferred, start=1):
        visits.append(
            {
                "exhibitor_id": item.exhibitor_id,
                "day": item.appt_day or 1,
                "seq": DEFERRED_SEQ_BASE + index,
                "eta_min": item.appt_start or day_start_minute,
                "eta_label": format_minute(item.appt_start or day_start_minute),
                "dwell_min": item.dwell_min,
                "walk_before_m": 0.0,
                "conflict": True,
                "conflict_kind": item.conflict_kind or "appointment",
                "conflict_note": item.conflict_note,
                "status": "deferred",
                "priority": item.priority,
                "weight": item.weight,
            }
        )

    total_weight = sum(item.weight for item in pool)
    conflict_visits = [item for item in visits if item["conflict"]]
    conflict_pairs = sum(1 for item in deferred if item.conflict_kind == "appointment")
    max_visits_hit = max_visits is not None and len(visits) >= max_visits
    metrics = {
        "day_count": day_count,
        "day_minutes": day_minutes,
        "day_start": format_minute(day_start_minute),
        "speed_m_per_min": speed,
        "priorities": sorted(allowed),
        "candidates": len(pool),
        "visit_count": sum(1 for item in visits if item["status"] != "deferred"),
        "row_count": len(visits),
        "total_walk_m": round(total_walk, 1),
        "total_dwell_min": total_dwell,
        "walk_minutes": round(total_walk / speed, 1) if speed else 0.0,
        "covered_weight": covered_weight,
        "total_weight": total_weight,
        "coverage_pct": round(100 * covered_weight / total_weight, 1) if total_weight else 0.0,
        "conflict_visits": len(conflict_visits),
        "conflict_pairs": conflict_pairs,
        "deferred": len(deferred),
        "deferred_appointment": sum(1 for item in deferred if item.conflict_kind == "appointment"),
        "deferred_overtime": sum(1 for item in deferred if item.conflict_kind == "overtime"),
        "max_visits_hit": max_visits_hit,
        "by_day": by_day,
    }
    log_lines = [
        f"候选 {len(pool)} 家（{'/'.join(sorted(allowed))}），{day_count} 天 × {day_minutes} 分钟，步行速度 {speed:g} m/min",
    ]
    for item in by_day:
        log_lines.append(
            f"Day {item['day']}：{item['visits']} 家，步行 {item['walk_m']:.0f}m，停留 {item['dwell_min']} 分钟，结束 {item['end_eta'] or '—'}，利用率 {item['util_pct']:.1f}%"
        )
    log_lines.append(
        f"合计步行 {metrics['total_walk_m']:.0f}m，覆盖权重 {covered_weight}/{total_weight}（{metrics['coverage_pct']:.1f}%），冲突 {conflict_pairs} 组 / 标记 {len(conflict_visits)} 条"
    )
    if deferred:
        for item in deferred:
            log_lines.append(
                f"冲突：{item.name}（{item.booth_no}，{item.priority}）{CONFLICT_KIND_LABELS.get(item.conflict_kind or '', '')} → {VISIT_STATUS_LABELS.get(item.status, item.status)}"
            )
    status = "success" if visits and any(item["status"] != "deferred" for item in visits) else "partial"
    return {"visits": visits, "metrics": metrics, "log": "\n".join(log_lines), "status": status}
