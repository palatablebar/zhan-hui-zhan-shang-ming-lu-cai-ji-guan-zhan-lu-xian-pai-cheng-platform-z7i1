"""算法 B 单测：权重、硬时间窗、冲突取舍、2-opt、容量与确定性。"""
from __future__ import annotations

from src.services import booth_service, route_service


def candidate(exhibitor_id: int, booth_no: str, priority: str = "P1", dwell: int = 10, **appointment):
    return route_service.build_candidate(
        {
            "id": exhibitor_id,
            "name": f"展商 {exhibitor_id}",
            "booth_no": booth_no,
            "priority": priority,
            "dwell_min": dwell,
            **appointment,
        }
    )


def test_priority_weights_follow_plan():
    assert route_service.Candidate
    p0 = candidate(1, "A1-011", "P0")
    p2 = candidate(2, "A1-012", "P2")
    assert (p0.weight, p2.weight) == (5, 1)


def test_unknown_priority_rejected():
    try:
        candidate(1, "A1-011", "P9")
    except ValueError as exc:
        assert "P9" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("应当拒绝未知优先级")


def test_greedy_covers_high_priority_first():
    rows = [
        candidate(1, "A1-011", "P1", 60),
        candidate(2, "A1-012", "P0", 60),
        candidate(3, "A1-013", "P1", 60),
    ]
    result = route_service.plan_routes(rows, day_count=1, day_minutes=90, priorities=("P0", "P1"))
    scheduled = [visit for visit in result["visits"] if visit["status"] != "deferred"]
    assert [visit["exhibitor_id"] for visit in scheduled] == [2]
    assert result["metrics"]["coverage_pct"] > 0


def test_appointment_window_is_hard_constraint():
    anchor = candidate(
        1,
        "A1-011",
        "P0",
        20,
        appointment_day=1,
        appointment_start_min=600,
        appointment_end_min=630,
    )
    filler = candidate(2, "A1-019", "P1", 15)
    result = route_service.plan_routes([anchor, filler], day_count=1, day_minutes=480)
    visit = [item for item in result["visits"] if item["exhibitor_id"] == 1][0]
    assert 600 <= visit["eta_min"] <= 610
    assert visit["eta_min"] + visit["dwell_min"] <= 630


def test_conflict_keeps_higher_weight_and_marks_both():
    high = candidate(1, "A1-011", "P0", 10, appointment_day=1, appointment_start_min=600, appointment_end_min=630)
    low = candidate(2, "A1-012", "P1", 10, appointment_day=1, appointment_start_min=600, appointment_end_min=630)
    result = route_service.plan_routes([low, high], day_count=1, day_minutes=480)
    metrics = result["metrics"]
    assert metrics["conflict_pairs"] == 1
    assert metrics["conflict_visits"] == 2
    scheduled = [item for item in result["visits"] if item["status"] != "deferred"]
    deferred = [item for item in result["visits"] if item["status"] == "deferred"]
    assert [item["exhibitor_id"] for item in scheduled] == [1]
    assert [item["exhibitor_id"] for item in deferred] == [2]
    assert scheduled[0]["conflict"] is True and deferred[0]["conflict"] is True


def test_two_opt_reduces_backtracking():
    order = [
        candidate(1, "A1-011", "P1", 10),
        candidate(2, "A1-019", "P1", 10),
        candidate(3, "A1-012", "P1", 10),
    ]
    ctx = {"day_start_minute": 540, "day_minutes": 480, "speed": 55.0}
    before = route_service.evaluate_order(order, 1, **ctx)
    improved, after = route_service._two_opt(order, 1, ctx)
    assert improved[0].exhibitor_id == 1
    assert after.walk_m < before.walk_m


def test_day_capacity_limits_visits():
    rows = [candidate(index, f"A1-0{index}1", "P1", 200) for index in range(1, 4)]
    result = route_service.plan_routes(rows, day_count=1, day_minutes=480, priorities=("P1",))
    assert result["metrics"]["visit_count"] == 2


def test_empty_input_is_partial():
    result = route_service.plan_routes([], day_count=2)
    assert result["status"] == "partial"
    assert result["visits"] == []
    assert result["metrics"]["coverage_pct"] == 0.0
    assert result["metrics"]["conflict_pairs"] == 0


def test_result_is_deterministic():
    rows = [
        candidate(1, "A1-011", "P0", 20),
        candidate(2, "A1-019", "P1", 15),
        candidate(3, "A2-011", "P1", 15),
        candidate(4, "B1-021", "P2", 10),
    ]
    first = route_service.plan_routes(rows, day_count=2)
    second = route_service.plan_routes(rows, day_count=2)
    assert first == second


def test_walk_distance_matches_booth_algorithm():
    first = booth_service.parse_booth_no("A1-011")
    second = booth_service.parse_booth_no("A1-091")
    assert booth_service.walking_distance(first, second) == 19.2
