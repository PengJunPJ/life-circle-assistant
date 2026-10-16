import asyncio
import copy

import pytest

from app.validation.spatial_sampling import evaluate_spatial_sampling


def fixture():
    return {
        "manifest": {"status": "synthetic_contract_only"},
        "communities": [
            {
                "id": community_id,
                "points": [
                    {
                        "id": f"r{row}c{column}",
                        "features_m": [row * 300, column * 300],
                        "duration_s": 500 + row * 150 + column * 80,
                        "source": "local_snapshot",
                    }
                    for row in range(1, 5)
                    for column in range(1, 5)
                ],
            }
            for community_id in ("community-a", "community-b", "calibration-c")
        ],
        "calibration_community_ids": ["calibration-c"],
    }


def test_five_independent_strategies_equal_budget_and_disjoint_spatial_holdout_per_community():
    result = asyncio.run(evaluate_spatial_sampling(fixture(), budgets=(5, 8)))
    assert result["status"] == "offline_snapshot_replay"
    assert result["community_ids"] == ["community-a", "community-b"]
    assert len(result["results"]) == 20
    for item in result["results"]:
        assert item["route_pairs_replayed"] == item["budget"]
        assert item["external_route_pairs_used"] == 0
        assert not set(item["training_ids"]) & set(item["validation_ids"])
    assert all(item["recorded_latency_sum_ms"] is None for item in result["results"])
    assert result["enabled_for_official_analysis"] is False


def test_evaluator_rejects_conflicting_destinations_missing_sources_and_real_labels_without_evidence():
    for mutation in ("duplicate", "unknown", "missing_evidence"):
        value = copy.deepcopy(fixture())
        first, second = value["communities"][0]["points"][:2]
        if mutation == "duplicate":
            second["features_m"] = first["features_m"]
        elif mutation == "unknown":
            first["source"] = "interpolation"
        else:
            first["source"] = "real_api"
        with pytest.raises(ValueError):
            asyncio.run(evaluate_spatial_sampling(value, budgets=(5,)))
