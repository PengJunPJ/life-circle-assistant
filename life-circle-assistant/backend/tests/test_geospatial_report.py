import asyncio

from app.analysis.service import AnalysisApplicationService
from app.maps.provider import FacilityResult, LocationResult, ProviderDescriptor, WalkingResult
from app.schemas import AnalyzeRequest


class ContractProvider:
    def __init__(self, *, truncated=False):
        self.truncated = truncated

    descriptor = ProviderDescriptor("contract", "fixture", "real_api", "测试地图", True)

    async def reverse_geocode(self, lng, lat):
        return LocationResult(lng, lat, "测试地址")

    async def search_facilities(self, category, center, radius_m):
        return [FacilityResult("a", "测试菜市场", category, center[0] + 0.014, center[1])]

    def get_facility_search_metadata(self, category, center, radius_m):
        return {"category": category, "truncated": self.truncated, "is_full_inventory": False}

    async def walking_matrix(self, origins, destinations):
        return [
            [
                WalkingResult(origin, destination, True, 1600, 1200, "real_api", "fixture")
                for destination in destinations
            ]
            for origin in origins
        ]


def analyze(provider):
    return asyncio.run(
        AnalysisApplicationService(provider).run(
            "task", AnalyzeRequest(lng=113.4872, lat=23.1068, categories=["market"], minutes=15, mode="demo")
        )
    )


def test_truncated_search_propagates_to_report_and_excludes_official_score_and_gap_claims():
    report = analyze(ContractProvider(truncated=True))
    assert report["facility_search"][0]["truncated"] is True
    assert report["summary"]["score"] is None
    assert all(item["properties"]["kind"] == "unknown" for item in report["service_areas"]["features"])
    assert all(item["properties"]["nearby_scarcity"] is None for item in report["service_areas"]["features"])
    assert report["gap_groups"]["features"] == []
    stats = report["spatial_statistics"]["categories"][0]
    assert stats["unknown_walking_count"] == stats["unknown_scarcity_count"] == 16
    assert any(item["code"] == "facility_search_truncated" for item in report["data_quality"]["partial_failures"])


def test_complete_query_generates_independent_time_scarcity_and_noninvented_group_geometry():
    report = analyze(ContractProvider())
    stats = report["spatial_statistics"]["categories"][0]
    assert stats["walking_gap_count"] == 16
    assert stats["nearby_scarcity_count"] < stats["walking_gap_count"]
    groups = report["gap_groups"]["features"]
    assert len(groups) == 3
    groups_by_kind = {group["properties"]["gap_kind"]: group for group in groups}
    assert set(groups_by_kind) == {"scarcity", "walking_timeout", "critical"}
    assert groups_by_kind["walking_timeout"]["properties"]["grid_count"] == 16
    assert groups_by_kind["scarcity"]["properties"]["grid_count"] == stats["nearby_scarcity_count"]
    assert groups_by_kind["critical"]["properties"]["grid_count"] == stats["nearby_scarcity_count"]
    for group in groups:
        assert len(group["geometry"]["coordinates"]) == group["properties"]["grid_count"]
    candidates = report["recommendations"][0]["candidate_locations"]
    assert candidates
    assert all(candidate["gap_group_id"] == groups_by_kind["critical"]["properties"]["id"] for candidate in candidates)
    assert report["facility_search"][0]["is_full_inventory"] is False


def test_report_keeps_underlying_cache_source_for_offline_evidence_review():
    class CachedProvider(ContractProvider):
        async def walking_matrix(self, origins, destinations):
            return [
                [
                    WalkingResult(
                        origin, destination, True, 1600, 1200, "cache", "fixture", underlying_source="local_snapshot"
                    )
                    for destination in destinations
                ]
                for origin in origins
            ]

    report = analyze(CachedProvider())
    assert report["facilities"][0]["source"] == "cache"
    assert report["facilities"][0]["underlying_source"] == "local_snapshot"
