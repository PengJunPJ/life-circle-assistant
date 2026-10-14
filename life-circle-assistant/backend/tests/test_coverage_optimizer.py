import asyncio
import itertools
import random

import pytest

from app.analysis.coverage_optimizer import CoverageCandidate, optimize_maximum_coverage, optimize_report_coverage
from app.maps.provider import ProviderDescriptor, WalkingResult


def test_exact_solver_avoids_greedy_trap_and_reports_scoped_optimality():
    candidates = [
        CoverageCandidate("a", frozenset("1234")),
        CoverageCandidate("b", frozenset("125")),
        CoverageCandidate("c", frozenset("346")),
    ]
    exact = optimize_maximum_coverage(candidates, max_facilities=2)
    greedy = optimize_maximum_coverage(candidates, max_facilities=2, method="greedy")
    assert exact["selected_candidate_ids"] == ["b", "c"]
    assert exact["covered_grid_count"] == 6
    assert exact["status"] == "OPTIMAL"
    assert greedy["covered_grid_count"] == 5
    assert greedy["status"] == "FEASIBLE"


def test_budget_quantity_overlap_and_deterministic_ties():
    candidates = [
        CoverageCandidate("c", frozenset("12"), 2),
        CoverageCandidate("b", frozenset("13"), 2),
        CoverageCandidate("a", frozenset("12"), 2),
    ]
    result = optimize_maximum_coverage(candidates, max_facilities=3, budget=4)
    assert result["selected_candidate_ids"] == ["a", "b"]
    assert result["covered_grid_count"] == 3
    assert result["total_cost"] == 4
    assert optimize_maximum_coverage(candidates, max_facilities=0)["selected_count"] == 0


def test_exact_result_matches_independent_exhaustive_oracle():
    rng = random.Random(13)
    for _ in range(20):
        candidates = [
            CoverageCandidate(str(i), frozenset(str(j) for j in range(8) if rng.random() < 0.4), rng.randint(1, 4))
            for i in range(7)
        ]
        oracle = max(
            len(set().union(*(item.grid_ids for item in combo)))
            for n in range(4)
            for combo in itertools.combinations(candidates, n)
            if sum(item.cost for item in combo) <= 6
        )
        result = optimize_maximum_coverage(candidates, max_facilities=3, budget=6)
        assert result["covered_grid_count"] == oracle
        assert result["total_cost"] <= 6


def test_unknown_cost_cannot_satisfy_budget_constraint():
    with pytest.raises(ValueError, match="已知成本"):
        optimize_maximum_coverage([CoverageCandidate("a", frozenset("1"))], max_facilities=1, budget=10)


def test_report_optimizer_counts_only_confirmed_routes_and_does_not_mutate_report():
    import copy

    class Provider:
        descriptor = ProviderDescriptor("fixture", "fixture", "real_api", "测试", True)

        async def walking_matrix(self, origins, destinations):
            return [
                [
                    WalkingResult(
                        origin,
                        destinations[0],
                        i == 0,
                        500 if i == 0 else None,
                        600 if i == 0 else None,
                        "real_api",
                        "fixture",
                    )
                ]
                for i, origin in enumerate(origins)
            ]

    grids = [
        {
            "properties": {
                "grid_id": f"market-r1c{i}",
                "category": "market",
                "kind": "critical",
                "classification_status": "valid",
                "failed_route_count": 0,
            },
            "geometry": {"coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
        }
        for i in [1, 2]
    ]
    report = {
        "report_id": "r1",
        "request": {"minutes": 15},
        "service_areas": {"features": grids},
        "recommendations": [{"candidate_locations": [{"id": "a", "category": "market", "lng": 1, "lat": 1}]}],
    }
    original = copy.deepcopy(report)
    result = asyncio.run(optimize_report_coverage(Provider(), report, candidate_ids=["a"], max_facilities=1))
    assert result["covered_grid_ids"] == ["market-r1c1"]
    assert result["unknown_route_pairs"] == 1
    assert result["coverage_evidence_status"] == "partial_lower_bound"
    assert result["candidate_evidence"][0]["unknown_grid_ids"] == ["market-r1c2"]
    assert report == original


def single_grid_report(*, destination=(1.0, 1.0)):
    return {
        "report_id": "r1",
        "request": {"minutes": 15},
        "service_areas": {
            "features": [
                {
                    "properties": {
                        "grid_id": "market-r1c1",
                        "category": "market",
                        "kind": "critical",
                        "classification_status": "valid",
                        "failed_route_count": 0,
                    },
                    "geometry": {"coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
                }
            ]
        },
        "recommendations": [
            {
                "candidate_locations": [
                    {
                        "id": "a",
                        "category": "market",
                        "lng": destination[0],
                        "lat": destination[1],
                    }
                ]
            }
        ],
    }


@pytest.mark.parametrize(
    "distance,duration",
    [
        (0, 0),
        (500, 0),
        (0, 60),
        (None, 60),
        (-1, 60),
        (float("nan"), 60),
        (float("inf"), 60),
        (True, 60),
        ("500", 60),
        (500, -1),
        (500, float("nan")),
        (500, float("inf")),
        (500, True),
    ],
)
def test_optimizer_keeps_invalid_route_evidence_unknown(distance, duration):
    class Provider:
        descriptor = ProviderDescriptor("fixture", "fixture", "real_api", "测试", True)

        async def walking_matrix(self, origins, destinations):
            return [[WalkingResult(origins[0], destinations[0], True, distance, duration, "real_api", "fixture")]]

    result = asyncio.run(
        optimize_report_coverage(Provider(), single_grid_report(), candidate_ids=["a"], max_facilities=1)
    )
    assert result["covered_grid_count"] == 0
    assert result["unknown_route_pairs"] == 1
    assert result["candidate_evidence"][0]["unknown_grid_ids"] == ["market-r1c1"]


def test_optimizer_accepts_verified_same_point_zero_route():
    class Provider:
        descriptor = ProviderDescriptor("fixture", "fixture", "real_api", "测试", True)

        async def walking_matrix(self, origins, destinations):
            return [[WalkingResult(origins[0], destinations[0], True, 0, 0, "real_api", "fixture")]]

    result = asyncio.run(
        optimize_report_coverage(
            Provider(), single_grid_report(destination=(0.5, 0.5)), candidate_ids=["a"], max_facilities=1
        )
    )
    assert result["covered_grid_count"] == 1
    assert result["unknown_route_pairs"] == 0


def test_optimizer_rejects_route_for_different_requested_pair():
    class Provider:
        descriptor = ProviderDescriptor("fixture", "fixture", "real_api", "测试", True)

        async def walking_matrix(self, origins, destinations):
            return [[WalkingResult((0, 0), destinations[0], True, 500, 600, "real_api", "wrong-origin")]]

    result = asyncio.run(
        optimize_report_coverage(Provider(), single_grid_report(), candidate_ids=["a"], max_facilities=1)
    )
    assert result["covered_grid_count"] == 0
    assert result["unknown_route_pairs"] == 1


@pytest.mark.parametrize("duplicate_lng", [1, 2])
def test_duplicate_source_candidate_id_rejected_before_map_call_even_if_records_match(duplicate_lng):
    class Provider:
        async def walking_matrix(self, *_args):
            raise AssertionError("重复候选不得触发外部路线请求")

    report = single_grid_report()
    report["recommendations"].append(
        {
            "candidate_locations": [
                {
                    "id": "a",
                    "category": "market",
                    "lng": duplicate_lng,
                    "lat": 1,
                }
            ]
        }
    )
    with pytest.raises(ValueError, match="标识重复"):
        asyncio.run(optimize_report_coverage(Provider(), report, candidate_ids=["a"], max_facilities=1))
