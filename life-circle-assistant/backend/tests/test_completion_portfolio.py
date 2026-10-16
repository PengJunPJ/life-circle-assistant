import copy
import itertools
import random

import pytest
from fastapi.testclient import TestClient
from test_geospatial_report import ContractProvider

from app.main import create_app
from app.mock_data import CENTER
from app.planning_portfolio import PortfolioConstraints, compile_constraints, feasible_portfolios


def test_natural_language_compiles_all_constraints_without_losing_budget():
    value = compile_constraints(
        "覆盖优化，预算10万元，最多3家药店；至少1家菜市场；只考虑parcel-a、parcel-b；必须选parcel-a；禁止parcel-b；容量至少200；只选可建设用地"
    )
    assert value.budget == 100000
    assert value.category_limits["pharmacy"].max == 3
    assert value.category_limits["market"].min == 1
    assert value.candidate_ids == ["parcel-a", "parcel-b"]
    assert value.required_ids == ["parcel-a"]
    assert value.forbidden_ids == ["parcel-b"]
    assert value.minimum_capacity == 200
    assert value.allowed_land_only


def test_pareto_matches_independent_small_enumeration_and_never_relaxes_hard_constraints():
    rng = random.Random(41)
    for _ in range(20):
        candidates = [
            {
                "id": str(i),
                "category": "pharmacy" if i % 2 else "market",
                "cost": rng.randint(1, 10),
                "capacity": 5,
                "land_allowed": i != 5,
            }
            for i in range(6)
        ]
        coverage = {c["id"]: {str(i) for i in range(8) if rng.random() < 0.4} for c in candidates}
        constraints = PortfolioConstraints(
            max_facilities=3,
            budget=18,
            required_ids=["0"],
            forbidden_ids=["5"],
            category_limits={"pharmacy": {"min": 1, "max": 2}},
            minimum_capacity=10,
            allowed_land_only=True,
        )
        frontier, _ = feasible_portfolios(candidates, coverage, constraints)
        oracle = []
        for n in range(4):
            for subset in itertools.combinations(candidates, n):
                if not any(c["id"] == "0" for c in subset) or any(c["id"] == "5" for c in subset):
                    continue
                if not 1 <= sum(c["category"] == "pharmacy" for c in subset) <= 2 or n * 5 < 10:
                    continue
                cost = sum(c["cost"] for c in subset)
                if cost > 18:
                    continue
                covered = len(set().union(*(coverage[c["id"]] for c in subset)))
                oracle.append((-covered, cost, n))
        expected = {p for p in oracle if not any(all(a <= b for a, b in zip(q, p)) and q != p for q in oracle)}
        assert {(-p["covered_grid_count"], p["total_cost"], p["selected_count"]) for p in frontier} == expected


def test_missing_cost_is_clarification_not_zero():
    with pytest.raises(ValueError, match="成本"):
        feasible_portfolios([{"id": "a", "category": "pharmacy"}], {"a": {"grid-1"}}, PortfolioConstraints(budget=100))


def test_public_combination_uses_full_route_recompute_and_immutable_original(tmp_path):
    with TestClient(create_app(provider=ContractProvider(), database_path=tmp_path / "portfolio.db")) as client:
        task = client.post(
            "/api/analyze",
            json={"lng": CENTER["lng"], "lat": CENTER["lat"], "mode": "demo", "categories": ["pharmacy", "market"]},
        ).json()
        report = client.get(f"/api/report/{task['id']}").json()
        report_id = report["report_id"]
        original = copy.deepcopy(report)
        candidates = [
            {
                "id": "parcel-a",
                "category": "pharmacy",
                "lng": CENTER["lng"],
                "lat": CENTER["lat"],
                "cost": 100,
                "capacity": 200,
                "land_allowed": True,
                "source": "测试地块台账",
                "verified": True,
            },
            {
                "id": "parcel-b",
                "category": "market",
                "lng": CENTER["lng"] + 0.001,
                "lat": CENTER["lat"],
                "cost": 120,
                "source": "测试地块台账",
                "verified": True,
            },
        ]
        imported = client.post(f"/api/reports/{report_id}/planning/candidates", json={"candidates": candidates})
        assert imported.status_code == 200, imported.text
        result = client.post(
            f"/api/reports/{report_id}/planning/optimize",
            json={
                "candidate_ids": ["parcel-a", "parcel-b"],
                "max_facilities": 2,
                "required_ids": ["parcel-a", "parcel-b"],
                "budget": 220,
            },
        )
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["selected_candidate_ids"] == ["parcel-a", "parcel-b"]
        combo = body["combination"]
        assert len(combo["hypothetical_facilities"]) == 2
        assert len(combo["after"]["service_areas"]["features"]) == len(report["service_areas"]["features"])
        assert combo["delta"]["overall_score"] == combo["after"]["overall_score"] - combo["before"]["overall_score"]
        assert client.get(f"/api/report/{task['id']}").json() == original


@pytest.mark.parametrize("message", ["预算十万元，药店最多三家", "预算100000元，最多3家药店"])
def test_chinese_budget_and_category_prefix(message):
    constraints = compile_constraints(message)
    assert constraints.budget == 100000
    assert constraints.category_limits["pharmacy"].max == 3


def test_global_limit_does_not_inherit_category_across_clause():
    constraints = compile_constraints("药店最多3家；总共最多2家；覆盖人口至少200")
    assert constraints.max_facilities == 2
    assert constraints.category_limits["pharmacy"].max == 3
    assert constraints.minimum_population == 200
    with pytest.raises(ValueError, match="共用上限"):
        compile_constraints("最多3家药店和菜市场")


def test_population_is_grid_union_and_missing_data_is_not_zero():
    candidates = [{"id": "a", "category": "market", "cost": 1}, {"id": "b", "category": "pharmacy", "cost": 1}]
    constraints = PortfolioConstraints(max_facilities=2, required_ids=["a", "b"], minimum_population=100)
    frontier, _ = feasible_portfolios(candidates, {"a": {"g1"}, "b": {"g1", "g2"}}, constraints, {"g1": 80, "g2": 30})
    assert frontier[0]["confirmed_population_benefit"] == 110
    with pytest.raises(ValueError, match="缺少"):
        feasible_portfolios(candidates, {"a": {"g1"}, "b": {"g2"}}, constraints, {"g1": 80})
    with pytest.raises(ValueError, match="没有可行"):
        feasible_portfolios(candidates, {"a": {"g1"}, "b": {"g1"}}, constraints, {"g1": 80})


def test_pareto_considers_verified_population_when_coverage_count_ties():
    candidates = [{"id": "a", "category": "market", "cost": 1}, {"id": "b", "category": "market", "cost": 1}]
    frontier, _ = feasible_portfolios(
        candidates, {"a": {"g1"}, "b": {"g2"}}, PortfolioConstraints(max_facilities=1), {"g1": 10, "g2": 80}
    )
    assert frontier[0]["candidate_ids"] == ["b"]


def test_combination_validates_actual_set_and_population_import(tmp_path):
    with TestClient(create_app(provider=ContractProvider(), database_path=tmp_path / "constraints.db")) as client:
        task = client.post("/api/analyze", json={"mode": "demo", "categories": ["pharmacy"]}).json()
        report = client.get(f"/api/report/{task['id']}").json()
        root = f"/api/reports/{report['report_id']}/planning"
        items = [
            {
                "id": key,
                "category": "pharmacy",
                "lng": CENTER["lng"],
                "lat": CENTER["lat"],
                "cost": 100,
                "source": "核验台账",
                "verified": True,
            }
            for key in ["a", "b"]
        ]
        assert client.post(root + "/candidates", json={"candidates": items}).status_code == 200
        for constraints in (
            {"max_facilities": 1},
            {"max_facilities": 2, "budget": 100},
            {"max_facilities": 2, "forbidden_ids": ["b"]},
        ):
            result = client.post(root + "/combination", json={"candidate_ids": ["a", "b"], **constraints})
            assert result.status_code == 422, result.text
        assert (
            client.post(root + "/optimize", json={"candidate_ids": ["a"], "minimum_population": 1}).status_code == 422
        )
        grid = report["service_areas"]["features"][0]["properties"]["grid_id"]
        demand = {"grid_id": grid, "population": 42, "source": "核验住户台账", "verified": True}
        assert client.post(root + "/demand", json={"items": [demand, demand]}).status_code == 422
        assert client.post(root + "/demand", json={"items": [{**demand, "verified": False}]}).status_code == 422
        assert client.post(root + "/demand", json={"items": [{**demand, "grid_id": "foreign"}]}).status_code == 422
        assert client.post(root + "/demand", json={"items": [demand]}).status_code == 200
        assert client.get(root + "/demand").json()["items"] == [demand]


def test_degraded_mock_combination_never_claims_score_improvement(tmp_path):
    with TestClient(create_app(database_path=tmp_path / "degraded.db")) as client:
        task = client.post("/api/analyze", json={"mode": "demo", "categories": ["pharmacy"]}).json()
        report = client.get(f"/api/report/{task['id']}").json()
        root = f"/api/reports/{report['report_id']}/planning"
        candidate = {
            "id": "a",
            "category": "pharmacy",
            "lng": CENTER["lng"],
            "lat": CENTER["lat"],
            "source": "核验地块",
            "verified": True,
        }
        assert client.post(root + "/candidates", json={"candidates": [candidate]}).status_code == 200
        result = client.post(root + "/combination", json={"candidate_ids": ["a"]})
        assert result.status_code == 200, result.text
        assert result.json()["after"]["overall_score"] is None
        assert result.json()["delta"]["overall_score"] is None
