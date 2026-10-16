import copy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_active_measurement import MeasuredProvider, report

from app.geo_routes import geo_router
from app.maps.provider import MapProviderError, NativeIsochroneResult


def make_client(provider=None, source_report=None, edges=None):
    app = FastAPI()
    original = source_report if source_report is not None else {**report(), "status": "completed"}
    app.state.report_repository = SimpleNamespace(get=lambda identifier: original if identifier == "r" else None)
    app.state.walking_service = provider or MeasuredProvider()
    app.state.map_provider = app.state.walking_service
    app.state.spatial_evidence_repository = SimpleNamespace(get_verified_edges=lambda _center: edges or [])
    app.include_router(geo_router())
    return TestClient(app), original, app.state.walking_service


def test_http_active_measurement_returns_layers_seconds_and_keeps_report_unchanged():
    client, original, provider = make_client()
    before = copy.deepcopy(original)
    response = client.post("/api/reports/r/experiments/active-sampling", json={"route_pair_budget": 8, "grid_size": 5})
    assert response.status_code == 200
    body = response.json()
    assert len(provider.destinations) == body["route_pairs_used"] == 8
    assert body["enabled_for_official_analysis"] is False
    assert len(body["layers"]["time_field"]["features"]) == 25
    assert all(value["affects_official_score"] is False for value in body["layers"].values())
    assert all(item["duration_s"] == 1234.567 for item in body["observations"])
    assert original == before


@pytest.mark.parametrize(
    "payload", [{"route_pair_budget": True}, {"grid_size": "5"}, {"unknown": 1}, {"high_risk_grid_ids": ["bogus"]}]
)
def test_invalid_active_requests_never_send_route_measurements(payload):
    client, _, provider = make_client()
    assert client.post("/api/reports/r/experiments/active-sampling", json=payload).status_code == 422
    assert provider.destinations == []


def test_missing_and_unfinished_reports_do_not_send_measurements():
    client, _, provider = make_client(source_report={**report(), "status": "running"})
    for identifier in ("r", "missing"):
        assert client.post(f"/api/reports/{identifier}/experiments/active-sampling", json={}).status_code == 404
    assert provider.destinations == []


def test_unconfigured_native_probe_discloses_disabled_and_does_not_invent_geometry():
    client, _, provider = make_client()
    capability = client.get("/api/map/isochrone-capability")
    assert capability.status_code == 200
    assert capability.json()["account_verified"] is False
    response = client.post("/api/map/isochrone-probe", json={"lng": 113.4, "lat": 23.1})
    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
    assert response.json()["request_sent"] is False
    assert "geometry" not in response.json()
    assert provider.destinations == []


@pytest.mark.parametrize("patch", [{"lng": True}, {"minutes": True}, {"minutes": "15"}, {"unexpected": 1}])
def test_native_probe_rejects_coerced_booleans_strings_and_extra_fields(patch):
    client, _, _ = make_client()
    assert client.post("/api/map/isochrone-probe", json={"lng": 113.4, "lat": 23.1, **patch}).status_code == 422


class NativeProvider(MeasuredProvider):
    def __init__(self, unavailable=False):
        super().__init__()
        self.unavailable = unavailable
        self.native_calls = []
        self.verified = False

    def isochrone_capability(self):
        return {"configured": True, "account_verified": self.verified, "pricing_verified": False}

    async def native_isochrone(self, center, seconds, strategy):
        self.native_calls.append((center, seconds, strategy))
        if self.unavailable:
            raise MapProviderError("账户未授权", code="account_permission_denied")
        self.verified = True
        return NativeIsochroneResult(
            {"type": "Polygon", "coordinates": [[[113.4, 23.1], [113.41, 23.1], [113.4, 23.11], [113.4, 23.1]]]},
            center,
            seconds,
            strategy,
            "real_api",
            "baidu_native_isochrone",
        )


@pytest.mark.parametrize("unavailable", [False, True])
def test_configured_native_probe_sends_exact_parameters_and_exposes_permission_failure(unavailable):
    provider = NativeProvider(unavailable)
    client, _, _ = make_client(provider)
    response = client.post(
        "/api/map/isochrone-probe", json={"lng": 113.4, "lat": 23.1, "minutes": 17, "strategy": "foot_shortest"}
    )
    assert response.status_code == 200
    body = response.json()
    assert provider.native_calls == [((113.4, 23.1), 1020, "foot_shortest")]
    assert body["request_sent"] is True
    assert body["pricing_verified"] is False
    if unavailable:
        assert body["status"] == "unavailable"
        assert body["error_code"] == "account_permission_denied"
        assert "geometry" not in body
        assert body["account_verified"] is False
    else:
        assert body["status"] == "available"
        assert body["geometry"]["type"] == "Polygon"
        assert body["account_verified"] is True
