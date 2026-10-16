import asyncio

import pytest

from app.analysis.sampling import (
    GaussianKernelRegressor,
    Prediction,
    SamplingPoint,
    evaluate_report_sampling,
    run_sampling_experiment,
    select_active_samples,
)
from app.maps.provider import MapProviderError, WalkingResult


def test_gaussian_regression_has_lower_uncertainty_near_observed_points():
    model = GaussianKernelRegressor()
    model.fit([((0, 0), 5), ((500, 0), 12)])
    near = model.predict((0, 0))
    far = model.predict((5000, 0))
    assert near.mean_minutes == pytest.approx(5, abs=0.2)
    assert near.std_minutes < far.std_minutes


def test_sampling_prioritizes_risk_then_threshold_uncertainty():
    class Model:
        def predict(self, features):
            return {0: Prediction(5, 1), 1: Prediction(15, 2), 2: Prediction(3, 1)}[features[0]]

    points = [SamplingPoint("stable", (0,)), SamplingPoint("threshold", (1,)), SamplingPoint("risk", (2,), True)]
    assert select_active_samples(points, Model(), threshold_minutes=15, limit=3) == ["risk", "threshold", "stable"]


def test_sampling_budget_includes_validation_and_never_trains_on_validation_labels():
    class RecordingModel:
        def __init__(self):
            self.values = []

        def fit(self, samples):
            self.values = [value for _, value in samples]

        def predict(self, _features):
            return Prediction(10, 1)

    model = RecordingModel()
    calls = []

    async def measure(point):
        calls.append(point.id)
        minutes = 25 if point.id == "heldout" else 10
        return WalkingResult((0, 0), (1, 1), True, 500, minutes * 60, "real_api", "fixture")

    points = [SamplingPoint(key, (i * 100.0, 0)) for i, key in enumerate(["a", "b", "c", "heldout"])]
    result = asyncio.run(
        run_sampling_experiment(points, measure, route_pair_budget=3, validation_ids=["heldout"], regressor=model)
    )
    assert len(calls) == 3
    assert result["route_pairs_used"] == 3
    assert result["training_ids"] == ["a", "b"]
    assert model.values == [10, 10]
    assert result["evaluation"]["false_reachable_count"] == 1
    assert result["evaluation"]["mae_minutes"] == 15
    assert result["baseline"]["mae_minutes"] == 15
    assert all(
        item["affects_official_score"] is False and item["requires_measurement"] for item in result["predictions"]
    )


def test_failed_measurements_stay_unknown_without_fake_fallback():
    async def measure(point):
        return WalkingResult((0, 0), (1, 1), False, None, None, "real_api", "fixture")

    points = [SamplingPoint("a", (0, 0)), SamplingPoint("b", (1, 0))]
    result = asyncio.run(run_sampling_experiment(points, measure, route_pair_budget=2))
    assert result["evaluation"]["mae_minutes"] is None
    assert all(item["minutes"] is None for item in result["observations"])
    assert all(item["status"] == "unresolved" for item in result["predictions"])


def test_invalid_budget_or_heldout_fails_before_measurement():
    async def forbidden(_point):
        raise AssertionError("无效配置不得测量")

    points = [SamplingPoint("a", (0, 0)), SamplingPoint("b", (1, 0))]
    with pytest.raises(ValueError):
        asyncio.run(run_sampling_experiment(points, forbidden, route_pair_budget=2, validation_ids=["a", "b"]))


def test_report_evaluation_is_offline_and_uses_recorded_source_and_discloses_scope():
    report = {
        "report_id": "r1",
        "analysis_center": {"lng": 113.4, "lat": 23.1},
        "request": {"minutes": 15},
        "facilities": [
            {
                "id": str(i),
                "lng": 113.4 + i * 0.006,
                "lat": 23.1,
                "walk_minutes": i + 5,
                "walk_distance_m": 500,
                "source": "local_snapshot",
                "calculation_method": "fixture",
            }
            for i in range(4)
        ],
    }
    result = asyncio.run(evaluate_report_sampling(report, route_pair_budget=3))
    assert result["external_route_pairs_used"] == 0
    assert result["source_modes"] == ["local_snapshot"]
    assert result["route_pairs_used"] == 3
    assert result["data_scope"] == "recorded_report_center_to_facility_routes"
    assert "不能外推" in result["disclosure"]
    assert result["label_precision_minutes"] == 0.1
    assert result["label_origin"] == "report_rounded_walk_minutes"
    assert result["raw_duration_seconds_available"] is False
    assert "无法恢复原始秒级测量" in result["disclosure"]


def test_report_deduplicates_same_route_and_holds_entire_spatial_block_out():
    report = {
        "report_id": "r1",
        "analysis_center": {"lng": 113.4, "lat": 23.1},
        "request": {"minutes": 15},
        "facilities": [
            {"id": key, "lng": lng, "lat": 23.1, "walk_minutes": 10, "walk_distance_m": 500, "source": "real_api"}
            for key, lng in [("a", 113.4), ("alias-a", 113.4), ("b", 113.401), ("c", 113.407), ("d", 113.408)]
        ],
    }
    result = asyncio.run(evaluate_report_sampling(report, route_pair_budget=4))
    assert result["deduplicated_record_count"] == 1
    assert result["sample_aliases"]["a"] == ["a", "alias-a"]
    assert set(result["validation_ids"]) == {"c", "d"}
    assert set(result["training_ids"]) == {"a", "b"}
    assert result["validation_scope"] == "entire_500m_spatial_block_excluded_from_training"
    assert result["evaluation_strength"] == "exploratory_single_spatial_block"


def test_estimated_routes_and_provider_errors_are_not_training_labels():
    async def measure(point):
        if point.id == "a":
            raise MapProviderError("failed", code="timeout")
        return WalkingResult((0, 0), (1, 1), True, 500, 600, "interpolation", "predicted")

    points = [SamplingPoint("a", (0, 0)), SamplingPoint("b", (1, 0))]
    result = asyncio.run(run_sampling_experiment(points, measure, route_pair_budget=2))
    assert all(item["status"] == "unknown" for item in result["observations"])
    assert result["evaluation"]["mae_minutes"] is None


@pytest.mark.parametrize(
    ("source", "underlying_source", "reason"),
    [
        ("cache", "interpolation", "estimated_underlying_source"),
        ("cache", "degraded_estimate", "estimated_underlying_source"),
        ("cache", None, "unverified_cache_origin"),
        ("cache", "cache", "unverified_cache_origin"),
        ("real_api", "interpolation", "estimated_underlying_source"),
        ("real_api", "unknown", "unverified_underlying_source"),
        ("unknown", None, "unsupported_route_source"),
    ],
)
def test_sampling_rejects_unverified_or_estimated_route_origins_in_training_and_validation(
    source, underlying_source, reason
):
    async def measure(_point):
        return WalkingResult((0, 0), (1, 1), True, 500, 600, source, "fixture", underlying_source=underlying_source)

    result = asyncio.run(
        run_sampling_experiment([SamplingPoint("a", (0, 0)), SamplingPoint("b", (1, 0))], measure, route_pair_budget=2)
    )
    assert {item["phase"] for item in result["observations"]} == {"training", "validation"}
    assert all(item["status"] == "unknown" and item["exclusion_reason"] == reason for item in result["observations"])
    assert all(item["underlying_source"] == underlying_source for item in result["observations"])
    assert result["evaluation"]["evaluated_count"] == 0
    assert result["baseline"]["mae_minutes"] is None
    assert all(item["mean_minutes"] is None for item in result["predictions"])


@pytest.mark.parametrize(
    ("distance", "duration", "success"),
    [
        (500, 0, True),
        (0, 600, True),
        (0, 0, True),
        (None, 600, True),
        (True, 600, True),
        (500, False, True),
        (float("inf"), 600, True),
        (500, float("nan"), True),
        (-1, 600, True),
        (500, -1, True),
        (500, 600, 1),
    ],
)
def test_sampling_noncoincident_routes_require_success_and_valid_positive_distance_and_time(
    distance, duration, success
):
    async def measure(_point):
        return WalkingResult((0, 0), (1, 1), success, distance, duration, "real_api", "fixture")

    result = asyncio.run(
        run_sampling_experiment([SamplingPoint("a", (0, 0)), SamplingPoint("b", (1, 0))], measure, route_pair_budget=2)
    )
    assert all(item["status"] == "unknown" for item in result["observations"])
    assert result["evaluation"]["evaluated_count"] == 0


def test_sampling_accepts_verified_cache_and_true_same_coordinate_zero_route():
    async def measure(_point):
        return WalkingResult((0, 0), (0, 0), True, 0, 0, "cache", "fixture", underlying_source="real_api")

    result = asyncio.run(
        run_sampling_experiment([SamplingPoint("a", (0, 0)), SamplingPoint("b", (1, 0))], measure, route_pair_budget=2)
    )
    assert all(item["minutes"] == 0 and item["status"] == "measured" for item in result["observations"])
    assert result["evaluation"]["evaluated_count"] == 1


def report_facility(point_id, lng, minutes=10, *, source="real_api", underlying_source=None, distance=500):
    return {
        "id": point_id,
        "lng": lng,
        "lat": 23.1,
        "walk_minutes": minutes,
        "walk_distance_m": distance,
        "source": source,
        "underlying_source": underlying_source,
    }


def sampling_report(facilities):
    return {
        "report_id": "r1",
        "analysis_center": {"lng": 113.4, "lat": 23.1},
        "request": {"minutes": 15},
        "facilities": facilities,
    }


def test_report_excludes_unverified_cache_and_preserves_verified_cache_provenance():
    report = sampling_report(
        [
            report_facility("a", 113.4, source="cache", underlying_source="real_api"),
            report_facility("b", 113.401, source="cache", underlying_source="local_snapshot"),
            report_facility("c", 113.407),
            report_facility("predicted", 113.408, source="cache", underlying_source="interpolation"),
            report_facility("estimated", 113.409, source="cache", underlying_source="degraded_estimate"),
            report_facility("unknown", 113.410, source="cache"),
        ]
    )
    result = asyncio.run(evaluate_report_sampling(report, route_pair_budget=3))
    assert result["sample_count"] == 3
    assert result["excluded_record_count"] == 3
    assert {item["facility_id"] for item in result["sample_exclusions"]} == {"predicted", "estimated", "unknown"}
    assert result["sample_sources"]["a"] == [{"facility_id": "a", "source": "cache", "underlying_source": "real_api"}]
    by_id = {item["point_id"]: item for item in result["observations"]}
    assert by_id["a"]["underlying_source"] == "real_api"
    assert by_id["b"]["underlying_source"] == "local_snapshot"
    assert result["source_modes"] == ["cache", "real_api"]


@pytest.mark.parametrize("labels", [[10, 10, 12, 10], [12, 10, 10, 10]])
def test_report_rejects_all_conflicting_coordinate_labels_regardless_of_record_order(labels):
    conflict_ids = [f"conflict-{i}" for i in range(len(labels))]
    report = sampling_report(
        [report_facility(point_id, 113.4, minutes) for point_id, minutes in zip(conflict_ids, labels)]
        + [report_facility("a", 113.401), report_facility("alias-a", 113.401)]
        + [report_facility("b", 113.407), report_facility("c", 113.408)]
    )
    result = asyncio.run(evaluate_report_sampling(report, route_pair_budget=3))
    assert result["sample_count"] == 3
    assert result["usable_record_count"] == 8
    assert result["deduplicated_record_count"] == 1
    assert result["conflicting_record_count"] == result["excluded_record_count"] == 4
    assert result["conflicting_sample_groups"] == [
        {
            "destination": {"lng": 113.4, "lat": 23.1},
            "facility_ids": conflict_ids,
            "labels_minutes": [10, 12],
            "reason": "conflicting_report_minutes_same_destination",
        }
    ]
    assert result["sample_aliases"] == {"a": ["a", "alias-a"], "b": ["b"], "c": ["c"]}
    assert not set(conflict_ids) & set(result["training_ids"] + result["validation_ids"])


def test_report_without_valid_distance_or_source_discloses_precision_and_exclusions_without_training():
    report = sampling_report(
        [report_facility("a", 113.401, distance=None), report_facility("b", 113.407, source="cache")]
    )
    result = asyncio.run(evaluate_report_sampling(report, route_pair_budget=3))
    assert result["status"] == "insufficient_recorded_samples"
    assert result["sample_count"] == 0
    assert result["label_precision_minutes"] == 0.1
    assert result["raw_duration_seconds_available"] is False
    assert result["sample_exclusions"] == [
        {"facility_id": "a", "reason": "invalid_route_measurement"},
        {"facility_id": "b", "reason": "unverified_cache_origin"},
    ]
    assert "无法恢复原始秒级测量" in result["disclosure"]
