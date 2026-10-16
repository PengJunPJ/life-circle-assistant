import asyncio
import copy
import math

import httpx
import pytest
from test_physical_route_budget import client_with_transport

from app.analysis.active_measurement import run_active_measurement, sampling_grid
from app.execution_budget import BudgetMapProvider
from app.maps.baidu import BaiduMapProvider
from app.maps.provider import ProviderDescriptor, WalkingResult


class MeasuredProvider:
    descriptor = ProviderDescriptor("test", "fixture", "real_api", "独立测试契约", False)

    def __init__(self, estimated=False):
        self.destinations = []
        self.estimated = estimated

    async def walking_matrix(self, origins, destinations):
        self.destinations.extend(destinations)
        return [
            [
                WalkingResult(
                    origin,
                    destination,
                    True,
                    800,
                    1234.567,
                    "degraded_estimate" if self.estimated else "real_api",
                    "fixture_route",
                )
                for destination in destinations
            ]
            for origin in origins
        ]


def report():
    return {"report_id": "r", "analysis_center": {"lng": 113.4, "lat": 23.1}, "request": {"minutes": 15}}


def test_active_real_measurement_has_exact_seconds_spatial_holdout_layers_and_immutable_report():
    provider = MeasuredProvider()
    original = report()
    before = copy.deepcopy(original)
    result = asyncio.run(run_active_measurement(provider, original, route_pair_budget=8, grid_size=5))
    assert len(provider.destinations) == result["route_pairs_used"] == 8
    assert result["raw_duration_seconds_available"] is True
    assert result["execution_budget"]["route_pairs_requested"] == 8
    assert all(item["duration_s"] == 1234.567 for item in result["observations"])
    assert not set(result["training_ids"]) & set(result["validation_ids"])
    points, _ = sampling_grid((113.4, 23.1), 5)
    block = tuple(result["heldout_spatial_block"])
    assert set(result["validation_ids"]) == {
        p.id for p in points if tuple(math.floor(v / 500) for v in p.features) == block
    }
    assert len(result["layers"]["observed"]["features"]) == 8
    assert len(result["layers"]["time_field"]["features"]) == 25
    assert all(layer["affects_official_score"] is False for layer in result["layers"].values())
    assert original == before


def test_estimations_are_never_observed_labels_and_unmeasured_field_is_unresolved():
    result = asyncio.run(run_active_measurement(MeasuredProvider(True), report(), route_pair_budget=3, grid_size=3))
    assert result["layers"]["observed"]["features"] == []
    assert len(result["layers"]["unresolved"]["features"]) == 9
    assert result["raw_duration_seconds_available"] is False
    assert result["evaluation"]["mae_minutes"] is None


def test_untrusted_risk_is_not_consumed_as_verified_obstacle_and_invalid_ids_never_call_provider():
    provider = MeasuredProvider()
    with pytest.raises(ValueError):
        asyncio.run(run_active_measurement(provider, report(), high_risk_grid_ids=["bogus"]))
    assert provider.destinations == []
    result = asyncio.run(
        run_active_measurement(
            provider,
            report(),
            route_pair_budget=3,
            grid_size=3,
            adjacency_evidence=[{"blocked": True, "first_grid_id": "r1c1", "second_grid_id": "r1c2"}],
        )
    )
    assert result["risk_evidence"] == []


def test_forged_verified_flag_is_ignored_and_reviewed_category_obstacle_maps_to_sampling_grid():
    provider = MeasuredProvider()
    forged = {"verified": True, "blocked": True, "first_grid_id": "market-r1c1", "second_grid_id": "market-r1c2"}
    trusted = {**forged, "reviewer": "reviewer", "evidence_ref": "field-1", "source": "field_verification"}
    untrusted = asyncio.run(
        run_active_measurement(provider, report(), route_pair_budget=3, grid_size=3, adjacency_evidence=[forged])
    )
    assert untrusted["risk_grid_ids"] == []
    result = asyncio.run(
        run_active_measurement(provider, report(), route_pair_budget=3, grid_size=3, adjacency_evidence=[trusted])
    )
    assert result["risk_evidence"] == [trusted]
    assert result["risk_grid_ids"]
    assert all(value.startswith("r") for value in result["risk_grid_ids"])


def test_active_local_budget_caps_physical_retries_even_when_parent_budget_is_larger():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(429, json={"status": 429})

    client = client_with_transport(handler)
    parent = BudgetMapProvider(BaiduMapProvider(client), 40)

    async def exercise():
        try:
            return await run_active_measurement(parent, report(), route_pair_budget=2, grid_size=3)
        finally:
            await client.aclose()

    result = asyncio.run(exercise())
    assert calls == ["/directionlite/v1/walking", "/directionlite/v1/walking"]
    assert result["external_route_pairs_used"] == 2
    assert result["execution_budget"]["physical_route_pairs_used"] == 2
    assert result["layers"]["observed"]["features"] == []
    assert result["evaluation"]["mae_minutes"] is None


@pytest.mark.parametrize("strategy", ["uniform", "radial", "rule_densification", "idw"])
def test_independent_baselines_spend_same_total_budget_with_same_holdout(strategy):
    result = asyncio.run(
        run_active_measurement(MeasuredProvider(), report(), route_pair_budget=8, grid_size=5, strategy=strategy)
    )
    assert result["strategy"] == strategy
    assert result["route_pairs_used"] == 8
    assert result["evaluation"]["evaluated_count"] == len(result["validation_ids"])
