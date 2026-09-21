import asyncio

from app.analysis.service_areas import CellEvidence, build_category_service_areas, classify_service_area_cell
from app.maps.provider import ProviderDescriptor, WalkingResult


def route(minutes: float, distance_m: float = 800, success: bool = True) -> WalkingResult:
    return WalkingResult(
        origin=(113.48, 23.10),
        destination=(113.49, 23.11),
        success=success,
        distance_m=distance_m if success else None,
        duration_s=minutes * 60 if success else None,
        source="real_api",
        method="fixture_walking_matrix",
    )


def evidence(*, nearby: int, candidates: int, walking: WalkingResult | None, failures: int = 0) -> CellEvidence:
    facility = {"id": "facility-1", "name": "测试设施"} if walking else None
    return CellEvidence(nearby, candidates, facility, walking, failures)


def test_no_same_category_candidate_is_unknown_without_walking_evidence():
    result = classify_service_area_cell(evidence(nearby=0, candidates=0, walking=None), 15)
    assert result.kind == "unknown"
    assert result.status == "calculation_incomplete"
    assert "不能据此推断" in result.basis


def test_facility_within_one_kilometer_but_over_time_is_sparse_not_critical():
    result = classify_service_area_cell(evidence(nearby=1, candidates=1, walking=route(18)), 15)
    assert result.kind == "sparse"
    assert "未同时满足重点盲区条件" in result.basis


def test_facility_outside_one_kilometer_but_reachable_is_sparse():
    result = classify_service_area_cell(evidence(nearby=0, candidates=1, walking=route(12, 1_150)), 15)
    assert result.kind == "sparse"
    assert "仍在15分钟阈值内" in result.basis


def test_nearby_and_reachable_facility_is_normal():
    result = classify_service_area_cell(evidence(nearby=1, candidates=1, walking=route(8)), 15)
    assert result.kind == "normal"


def test_partial_walking_failure_keeps_classification_and_reduces_confidence():
    result = classify_service_area_cell(evidence(nearby=1, candidates=2, walking=route(8), failures=1), 15)
    assert result.kind == "normal"
    assert result.confidence == "medium"


def test_all_walking_results_failed_does_not_claim_critical_blind_spot():
    result = classify_service_area_cell(evidence(nearby=0, candidates=1, walking=None, failures=1), 15)
    assert result.kind == "unknown"
    assert result.status == "calculation_incomplete"
    assert result.confidence == "low"


def test_facility_discovery_failure_does_not_claim_no_facility_critical_blind_spot():
    failed = CellEvidence(0, 0, None, None, facility_discovery_succeeded=False)
    result = classify_service_area_cell(failed, 15)
    assert result.kind == "unknown"
    assert result.status == "calculation_incomplete"
    assert result.confidence == "low"


def test_straight_line_distance_only_prefilters_external_walking_candidates():
    class RecordingProvider:
        destinations: list[tuple[float, float]] = []

        @property
        def descriptor(self):
            return ProviderDescriptor("fixture", "fixture", "real_api", "测试", True)

        async def walking_matrix(self, origins, destinations):
            self.destinations = destinations
            return [
                [
                    WalkingResult(origin, destination, True, 1_200, 720, "real_api", "fixture")
                    for destination in destinations
                ]
                for origin in origins
            ]

    provider = RecordingProvider()
    center = (113.48, 23.10)
    facilities = [
        {"id": "near", "name": "可达小学", "category": "school", "lng": 113.49, "lat": 23.10},
        {"id": "far", "name": "过远小学", "category": "school", "lng": 113.52, "lat": 23.10},
    ]
    areas, _, _ = asyncio.run(
        build_category_service_areas(provider, center, ["school"], facilities, 15, grid_size=1, grid_span_m=0)
    )

    assert provider.destinations == [(113.49, 23.10)]
    assert areas["features"][0]["properties"]["nearest_facility_id"] == "near"


def test_no_candidate_feature_does_not_fabricate_threshold_evidence():
    class EmptyProvider:
        @property
        def descriptor(self):
            return ProviderDescriptor("fixture", "fixture", "real_api", "测试", True)

        async def walking_matrix(self, origins, destinations):
            raise AssertionError("无候选设施时不应调用步行矩阵")

    areas, events, failures = asyncio.run(
        build_category_service_areas(EmptyProvider(), (113.48, 23.10), ["school"], [], 15, grid_size=1, grid_span_m=0)
    )

    properties = areas["features"][0]["properties"]
    assert properties["kind"] == "unknown"
    assert properties["classification_status"] == "calculation_incomplete"
    assert properties["walk_threshold_exceeded"] is None
    assert properties["critical_conditions_met"] is False
    assert properties["calculation_method"] == "not_calculated_no_candidate"
    assert events[0]["code"] == "service_area_calculation_incomplete"
    assert failures[0]["code"] == "service_area_calculation_incomplete"
