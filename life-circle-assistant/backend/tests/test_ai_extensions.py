"""公共 AI 增量接口：来源约束、预算披露及原报告不可变性。"""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.baidu import BaiduMapClient, haversine_meters
from app.main import create_app
from app.maps.baidu import BaiduMapProvider
from app.maps.provider import FacilityResult, LocationResult, ProviderDescriptor, WalkingResult


class ExtensionFixtureProvider(BaiduMapProvider):
    """受控远端设施与解析路线；只供接口集成测试，不产生真实 HTTP。"""

    descriptor = ProviderDescriptor("extensions-fixture", "fixture", "local_snapshot", "测试样本", False)

    def __init__(self):
        super().__init__(BaiduMapClient())

    async def reverse_geocode(self, lng, lat):
        return LocationResult(lng, lat, "受控测试中心")

    async def search_facilities(self, category, center, radius_m=1000):
        return [FacilityResult("far-market", "远端菜市场", category, center[0] + 0.026, center[1])]

    async def walking_matrix(self, origins, destinations):
        return [
            [
                WalkingResult(
                    origin,
                    destination,
                    True,
                    haversine_meters(origin, destination),
                    haversine_meters(origin, destination) / 1.2,
                    "local_snapshot",
                    "fixture",
                )
                for destination in destinations
            ]
            for origin in origins
        ]


@pytest.fixture
def report_client(tmp_path):
    app = create_app(ExtensionFixtureProvider(), database_path=tmp_path / "extensions.db")
    app.state.llm_provider = None
    with TestClient(app) as client:
        task = client.post(
            "/api/analyze", json={"lng": 113.5, "lat": 23.1, "mode": "demo", "categories": ["market"]}
        ).json()
        completed = client.get(f"/api/analyze/{task['id']}").json()
        assert completed["status"] == "completed", completed.get("error")
        report = completed["result"]
        yield client, report


def test_extension_source_validation_and_strict_inputs(report_client):
    client, report = report_client
    for suffix, body in (
        ("ai/semantic-review", {}),
        ("experiments/sampling", {}),
        ("planning/coverage", {"candidate_ids": ["a"], "max_facilities": 1}),
    ):
        assert client.post(f"/api/reports/missing/{suffix}", json=body).status_code == 404
    prefix = f"/api/reports/{report['report_id']}"
    assert client.post(f"{prefix}/experiments/sampling", json={"route_pair_budget": True}).status_code == 422
    for body in (
        {"candidate_ids": ["forged"], "max_facilities": 1},
        {"candidate_ids": ["forged"], "max_facilities": True},
        {"candidate_ids": ["forged"], "max_facilities": 1, "coordinates": [0, 0]},
        {"candidate_ids": ["forged"], "max_facilities": 1, "costs": {"forged": True}},
    ):
        assert client.post(f"{prefix}/planning/coverage", json=body).status_code == 422


def test_review_sampling_and_optimizer_do_not_modify_source_report(report_client):
    client, report = report_client
    original = deepcopy(client.app.state.report_repository.get(report["report_id"]))
    prefix = f"/api/reports/{report['report_id']}"
    reviewed = client.post(f"{prefix}/ai/semantic-review", json={}).json()
    assert reviewed["affects_original_report"] is False
    assert reviewed["model_calls"] == 0
    sampled = client.post(f"{prefix}/experiments/sampling", json={}).json()
    assert sampled["report_id"] == report["report_id"]
    candidates = [item["id"] for rec in report["recommendations"] for item in rec["candidate_locations"]]
    assert candidates, "受控远端设施应形成已知重点盲区候选"
    response = client.post(f"{prefix}/planning/coverage", json={"candidate_ids": candidates[:2], "max_facilities": 1})
    assert response.status_code == 200, response.text
    optimized = response.json()
    assert optimized["affects_original_report"] is False
    assert optimized["selected_count"] <= 1
    assert optimized["execution_budget"]["physical_route_pairs_used"] == 0  # offline fixture
    assert client.app.state.report_repository.get(report["report_id"]) == original


def test_conversation_review_and_coverage_share_budget_and_keep_quantity(report_client):
    client, report = report_client

    class FakeModel:
        model = "offline-fixture"
        calls = 0

        async def generate(self, **kwargs):
            self.calls += 1
            return {"category_proposals": [], "entity_proposals": []}

        async def close(self):
            pass

    model = FakeModel()
    client.app.state.llm_provider = model
    center = report["center"]
    workspace = client.post(
        "/api/workspaces",
        json={
            "state": {
                "center": {"lng": center["lng"], "lat": center["lat"], "address": center["address"]},
                "mode": "demo",
                "categories": ["market"],
                "visible_categories": ["market"],
                "report_id": report["report_id"],
            }
        },
    ).json()
    endpoint = f"/api/workspaces/{workspace['id']}/messages"
    proposal = client.post(
        endpoint, json={"message": "语义审核设施", "request_id": "review", "expected_revision": 0}
    ).json()
    result = client.post(
        endpoint,
        json={
            "message": "确认",
            "request_id": "review-confirm",
            "expected_revision": proposal["revision"],
            "confirm_token": proposal["pending"]["token"],
        },
    ).json()
    assert result["status"] == "completed", result
    assert result["semantic_review"]["model_calls"] == result["execution"]["model_calls"] == model.calls == 1
    proposal = client.post(
        endpoint,
        json={"message": "覆盖优化，最多三家菜市场", "request_id": "coverage", "expected_revision": result["revision"]},
    ).json()
    assert "3个" in proposal["pending"]["label"]
    result = client.post(
        endpoint,
        json={
            "message": "确认",
            "request_id": "coverage-confirm",
            "expected_revision": proposal["revision"],
            "confirm_token": proposal["pending"]["token"],
        },
    ).json()
    assert result["status"] == "completed", result
    assert result["optimization"]["constraints"]["max_facilities"] == 3
    assert result["execution"]["model_calls"] == 0
