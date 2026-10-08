import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import app, create_app
from app.maps.provider import FacilityResult, LocationResult, MapProviderError, ProviderDescriptor, WalkingResult
from app.storage import Database, TaskRepository

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "2.2.0"


def test_map_status_and_mock_geocode():
    status = client.get("/api/map/status")
    assert status.status_code == 200
    assert status.json()["mock_available"] is True
    geocode = client.get("/api/geocode", params={"address": "红山街道海韵东路"})
    assert geocode.json()["source"] == "local_snapshot"
    unsupported = client.get("/api/geocode", params={"address": "广州市其他任意地址"})
    assert unsupported.status_code == 422
    assert "只支持内置" in unsupported.json()["detail"]

    reverse = client.get("/api/locations/reverse", params={"lng": 113.4872, "lat": 23.1068})
    assert reverse.status_code == 200
    assert reverse.json()["result"]["address"] == "广州市黄埔区红山街道海韵东路离线样例中心"

    outside = client.get("/api/locations/reverse", params={"lng": 113.6, "lat": 23.2})
    assert outside.status_code == 422
    assert "超出本地快照支持范围" in outside.json()["detail"]


def test_snapshot_place_search_keeps_legacy_category_label_behavior():
    response = client.get("/api/pois", params={"query": "药店"})
    assert response.status_code == 200
    assert response.json()["source"] == "local_snapshot"
    assert response.json()["results"]


def test_map_config_does_not_expose_secret():
    response = client.get("/api/map/config")
    assert response.status_code == 200
    assert "browser_ak" in response.json()
    assert "secret" not in response.json()


def test_create_and_get_analysis():
    response = client.post("/api/analyze", json={"minutes": 15, "mode": "demo"})
    assert response.status_code == 200
    task_id = response.json()["id"]
    report = client.get(f"/api/report/{task_id}")
    assert report.status_code == 200
    body = report.json()
    assert body["summary"]["score"] >= 0
    assert body["isochrone"]["geometry"]["type"] == "Polygon"
    assert body["zones"]["type"] == "FeatureCollection"
    assert body["schema_version"] == "2.0"
    assert body["execution"]["current_stage"] == "completed"
    assert body["execution"]["total_duration_ms"] >= 0
    assert body["execution"]["stage_durations_ms"]["walking_calculation"] >= 0
    assert body["execution"]["stage_durations_ms"]["center_resolution"] >= 0
    assert body["execution"]["cache"]["hits"] == body["execution"]["metrics"]["walking_cache_hits"]
    assert body["execution"]["api_calls"] == (
        body["execution"]["metrics"]["facility_api_calls"] + body["execution"]["metrics"]["walking_api_calls"]
    )
    assert all("duration_ms" in stage for stage in body["execution"]["stages"])
    assert [stage["code"] for stage in body["execution"]["stages"][:2]] == [
        "request_validation",
        "center_resolution",
    ]
    assert body["data_quality"]["overall_status"] == "limited"
    assert "不代表最新真实地图测算" in body["data_quality"]["summary"]
    assert body["center"] == {
        "lng": 113.4872,
        "lat": 23.1068,
        "address": "广州市黄埔区红山街道海韵东路离线样例中心",
        "selection_method": "default",
        "source": "local_snapshot",
        "support_status": "supported",
    }


def test_analysis_tracks_center_resolution_failure_inside_task():
    response = client.post("/api/analyze", json={"lng": 113.6, "lat": 23.2})
    assert response.status_code == 200
    task = client.get(f"/api/analyze/{response.json()['id']}").json()
    assert task["status"] == "failed"
    assert task["stage_label"] == "中心点解析失败"
    assert "超出本地快照支持范围" in task["error"]


def test_location_endpoints_reject_points_outside_huangpu_delivery_scope():
    provider = FixtureMapProvider()
    fixture_client = TestClient(create_app(provider))
    reverse = fixture_client.get("/api/locations/reverse", params={"lng": 121.47, "lat": 31.23})
    assert reverse.status_code == 422
    assert "仅支持广州市黄埔区" in reverse.json()["detail"]

    analyze = fixture_client.post("/api/analyze", json={"lng": 121.47, "lat": 31.23})
    assert analyze.status_code == 422
    assert "仅支持广州市黄埔区" in analyze.json()["detail"]


class FixtureMapProvider:
    def __init__(self, failing_category: str | None = None):
        self.failing_category = failing_category
        self.calls: list[str] = []

    @property
    def descriptor(self):
        return ProviderDescriptor(
            id="deterministic-test-provider",
            mode="fixture",
            source="real_api",
            label="确定性测试地图提供方",
            is_latest_real_measurement=True,
        )

    async def geocode(self, address: str, city: str = "广州"):
        self.calls.append("geocode")
        return [LocationResult(lng=113.5, lat=23.1, address=f"{city}{address}")]

    async def reverse_geocode(self, lng: float, lat: float):
        self.calls.append("reverse_geocode")
        return LocationResult(lng=lng, lat=lat, address="测试中心点")

    async def search_places(self, query: str, center: tuple[float, float], radius_m: int = 1000):
        self.calls.append("search_places")
        return [FacilityResult(id="place-1", name=query, category="unknown", lng=center[0], lat=center[1])]

    async def search_facilities(self, category: str, center: tuple[float, float], radius_m: int = 1000):
        self.calls.append(f"search_facilities:{category}")
        if category == self.failing_category:
            raise MapProviderError("测试类别检索失败")
        return [
            FacilityResult(
                id=f"{category}-1",
                name=f"测试{category}",
                category=category,
                lng=center[0] + 0.001,
                lat=center[1] + 0.001,
            )
        ]

    async def walking_matrix(self, origins: list[tuple[float, float]], destinations: list[tuple[float, float]]):
        self.calls.append("walking_matrix")
        return [
            [
                WalkingResult(
                    origin=origin,
                    destination=destination,
                    success=True,
                    distance_m=600,
                    duration_s=480,
                    source="real_api",
                    method="fixture_walking_matrix",
                )
                for destination in destinations
            ]
            for origin in origins
        ]


class PartialWalkingFixtureMapProvider(FixtureMapProvider):
    def __init__(self):
        super().__init__()
        self.failed_pair = None

    async def walking_matrix(self, origins: list[tuple[float, float]], destinations: list[tuple[float, float]]):
        rows = await super().walking_matrix(origins, destinations)
        if len(origins) > 1 and rows and rows[0] and self.failed_pair is None:
            self.failed_pair = (origins[0], destinations[0])
        if rows and rows[0] and self.failed_pair == (origins[0], destinations[0]):
            rows[0][0] = WalkingResult(
                origin=origins[0],
                destination=destinations[0],
                success=False,
                distance_m=None,
                duration_s=None,
                source="real_api",
                method="fixture_walking_matrix",
                error_code="fixture_timeout",
                error_message="确定性步行超时",
            )
        return rows


class LongWalkingFixtureMapProvider(FixtureMapProvider):
    async def walking_matrix(self, origins: list[tuple[float, float]], destinations: list[tuple[float, float]]):
        self.calls.append("walking_matrix")
        return [
            [
                WalkingResult(
                    origin=origin,
                    destination=destination,
                    success=True,
                    distance_m=1_800,
                    duration_s=1_200,
                    source="real_api",
                    method="fixture_walking_matrix",
                )
                for destination in destinations
            ]
            for origin in origins
        ]


class EmptyFacilityFixtureMapProvider(FixtureMapProvider):
    async def search_facilities(self, category: str, center: tuple[float, float], radius_m: int = 1000):
        self.calls.append(f"search_facilities:{category}")
        return []


def test_provider_can_be_replaced_without_real_baidu_requests(tmp_path):
    provider = FixtureMapProvider()
    fixture_client = TestClient(create_app(provider, tmp_path / "replace-provider.db"))

    geocode = fixture_client.get("/api/geocode", params={"address": "测试地址"})
    assert geocode.status_code == 200
    assert geocode.json()["result"]["location"] == {"lng": 113.5, "lat": 23.1}

    response = fixture_client.post(
        "/api/analyze", json={"minutes": 15, "mode": "demo", "categories": ["market", "school"]}
    )
    assert response.status_code == 200
    report = fixture_client.get(f"/api/report/{response.json()['id']}").json()

    assert report["source"] == "baidu"
    assert report["completeness"] == "complete"
    assert report["calculation_mode"]["provider_mode"] == "fixture"
    assert report["data_quality"]["sources"][0]["provider"] == "deterministic-test-provider"
    assert report["facility_normalization"]["input_count"] == 2
    assert report["facility_normalization"]["output_count"] == 2
    assert all(item["canonical_name"] for item in report["facilities"])
    assert all(item["semantic_type"] for item in report["facilities"])
    assert any(event["code"] == "facility_semantic_normalization" for event in report["data_quality"]["events"])
    assert report["scoring"]["status"] == "complete"
    assert report["scoring"]["valid_category_count"] == 2
    assert all(len(item["components"]) == 3 for item in report["category_scores"])
    assert all(sum(component["weight"] for component in item["components"]) == 1 for item in report["category_scores"])
    assert provider.calls.count("geocode") == 1
    assert provider.calls.count("reverse_geocode") == 1
    assert "search_facilities:market" in provider.calls
    assert "search_facilities:school" in provider.calls
    assert "walking_matrix" in provider.calls


def test_service_areas_are_complete_per_category_and_include_walking_evidence(tmp_path):
    provider = FixtureMapProvider()
    fixture_client = TestClient(create_app(provider, tmp_path / "service-areas.db"))
    response = fixture_client.post("/api/analyze", json={"minutes": 15, "categories": ["market", "school"]})
    report = fixture_client.get(f"/api/report/{response.json()['id']}").json()

    features = report["service_areas"]["features"]
    assert len(features) == 32
    assert {feature["properties"]["category"] for feature in features} == {"market", "school"}
    assert all(feature["properties"]["coordinate_system"] == "BD-09" for feature in features)
    assert all(feature["properties"]["kind"] in {"normal", "sparse", "critical"} for feature in features)
    assert all("basis" in feature["properties"] for feature in features)
    assert all("nearest_walk_minutes" in feature["properties"] for feature in features)
    assert all("nearest_walk_distance_m" in feature["properties"] for feature in features)
    assert provider.calls.count("walking_matrix") >= 2


def test_public_report_marks_missing_route_evidence_incomplete_without_blind_spot(tmp_path):
    provider = EmptyFacilityFixtureMapProvider()
    fixture_client = TestClient(create_app(provider, tmp_path / "empty-facilities.db"))
    response = fixture_client.post("/api/analyze", json={"minutes": 15, "categories": ["school"]})
    report = fixture_client.get(f"/api/report/{response.json()['id']}").json()

    properties = report["service_areas"]["features"][0]["properties"]
    assert properties["kind"] == "unknown"
    assert properties["walk_threshold_exceeded"] is None
    assert properties["critical_conditions_met"] is False
    assert report["summary"]["critical_zone_count"] == 0
    assert report["category_scores"][0]["status"] == "calculation_incomplete"
    assert report["category_scores"][0]["valid_for_overall"] is False
    assert report["scoring"]["score"] is None
    assert report["recommendations"] == []
    assert report["recommendation_summary"]["status"] == "calculation_incomplete"
    assert any(event["code"] == "service_area_calculation_incomplete" for event in report["data_quality"]["events"])


def test_partial_grid_walking_result_is_disclosed_without_failing_whole_report(tmp_path):
    provider = PartialWalkingFixtureMapProvider()
    fixture_client = TestClient(create_app(provider, tmp_path / "partial-grid.db"))
    response = fixture_client.post("/api/analyze", json={"categories": ["market"]})
    report = fixture_client.get(f"/api/report/{response.json()['id']}").json()

    assert report["status"] == "completed"
    assert report["completeness"] == "partial"
    assert any(
        event["code"] == "service_area_walking_partial" and event["category"] == "market"
        for event in report["data_quality"]["events"]
    )
    first_cell = report["service_areas"]["features"][0]["properties"]
    assert first_cell["failed_route_count"] == 1
    assert first_cell["confidence"] == "low"
    assert report["category_scores"][0]["valid_for_overall"] is False
    assert report["scoring"]["score"] is None
    metrics = report["execution"]["metrics"]
    assert metrics["walking_api_calls"] > 0
    assert metrics["walking_failures"] > 0


def test_report_discloses_cache_hits_and_reuses_persisted_walking_results(tmp_path):
    database_path = tmp_path / "analysis-walking-cache.db"
    provider = FixtureMapProvider()
    fixture_client = TestClient(create_app(provider, database_path))

    first = fixture_client.post("/api/analyze", json={"categories": ["market"]}).json()
    first_report = fixture_client.get(f"/api/report/{first['id']}").json()
    provider_call_count = provider.calls.count("walking_matrix")
    assert first_report["execution"]["metrics"]["walking_cache_misses"] > 0
    assert first_report["execution"]["metrics"]["walking_api_calls"] > 0

    second = fixture_client.post("/api/analyze", json={"categories": ["market"]}).json()
    second_report = fixture_client.get(f"/api/report/{second['id']}").json()
    assert provider.calls.count("walking_matrix") == provider_call_count
    assert second_report["execution"]["metrics"]["walking_cache_hits"] > 0
    assert second_report["execution"]["metrics"]["walking_api_calls"] == 0
    assert any(item["source"] == "cache" for item in second_report["facilities"])
    assert any(event["code"] == "walking_cache_used" for event in second_report["data_quality"]["events"])
    assert any(source["kind"] == "cache" for source in second_report["data_quality"]["sources"])


def test_category_failure_produces_partial_report_and_quality_event(tmp_path):
    provider = FixtureMapProvider(failing_category="school")
    fixture_client = TestClient(create_app(provider, tmp_path / "category-failure.db"))
    response = fixture_client.post("/api/analyze", json={"categories": ["market", "school"]})
    report = fixture_client.get(f"/api/report/{response.json()['id']}").json()

    assert report["status"] == "completed"
    assert report["completeness"] == "partial"
    assert report["data_quality"]["overall_status"] == "partial"
    assert report["data_quality"]["partial_failures"][0]["category"] == "school"
    assert any(event["code"] == "category_partial" for event in report["data_quality"]["events"])
    scores = {item["category"]: item for item in report["category_scores"]}
    assert scores["school"]["status"] == "data_unavailable"
    assert scores["school"]["score"] is None
    assert scores["school"]["valid_for_overall"] is False
    assert scores["market"]["applied_weight"] == 1
    assert report["scoring"]["status"] == "partial"
    assert report["summary"]["score"] == scores["market"]["score"]


def test_analysis_request_rejects_empty_unknown_categories_and_invalid_coordinates():
    assert client.post("/api/analyze", json={"categories": []}).status_code == 422
    assert client.post("/api/analyze", json={"categories": ["not_a_facility"]}).status_code == 422
    assert client.post("/api/analyze", json={"lng": 181}).status_code == 422


def test_tasks_reports_history_and_rerun_survive_storage_reinitialization(tmp_path):
    database_path = tmp_path / "analysis-history.db"
    provider = FixtureMapProvider()

    first_client = TestClient(create_app(provider, database_path))
    created = first_client.post(
        "/api/analyze",
        json={"lng": 113.51, "lat": 23.12, "minutes": 20, "mode": "analysis", "categories": ["market", "school"]},
    ).json()
    original_task = first_client.get(f"/api/analyze/{created['id']}").json()
    assert original_task["status"] == "completed"
    original_report_id = original_task["report_id"]

    # 用同一数据库重新创建应用，模拟服务进程重启和存储层重新初始化。
    restarted_client = TestClient(create_app(provider, database_path))
    persisted_task = restarted_client.get(f"/api/analyze/{created['id']}")
    assert persisted_task.status_code == 200
    assert persisted_task.json()["request"]["minutes"] == 20
    assert persisted_task.json()["result"]["report_id"] == original_report_id

    history = restarted_client.get("/api/reports/history").json()
    assert history["total"] == 1
    assert history["items"][0]["report_id"] == original_report_id
    assert history["items"][0]["center"]["lng"] == 113.51
    opened = restarted_client.get(f"/api/reports/{original_report_id}").json()
    assert opened["isochrone"]["geometry"]["type"] == "Polygon"
    assert opened["request"]["categories"] == ["market", "school"]
    assert {item["category"] for item in opened["category_scores"]} == {"market", "school"}
    assert {feature["properties"]["category"] for feature in opened["service_areas"]["features"]} == {
        "market",
        "school",
    }

    rerun = restarted_client.post(f"/api/reports/{original_report_id}/rerun").json()
    rerun_task = restarted_client.get(f"/api/analyze/{rerun['id']}").json()
    assert rerun_task["status"] == "completed"
    assert rerun_task["rerun_of_report_id"] == original_report_id
    assert rerun_task["report_id"] != original_report_id
    assert rerun_task["request"] == original_task["request"]
    assert {item["category"] for item in rerun_task["result"]["category_scores"]} == {"market", "school"}
    assert {feature["properties"]["category"] for feature in rerun_task["result"]["service_areas"]["features"]} == {
        "market",
        "school",
    }

    history_after_rerun = restarted_client.get("/api/reports/history").json()
    assert history_after_rerun["total"] == 2
    assert history_after_rerun["items"][0]["report_id"] == rerun_task["report_id"]

    database = Database(database_path)
    with database.connect() as connection, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute(
            "UPDATE analysis_reports SET center_address = ? WHERE id = ?",
            ("不应被修改", original_report_id),
        )


def test_running_task_is_marked_failed_after_restart(tmp_path):
    database_path = tmp_path / "interrupted.db"
    database = Database(database_path)
    database.migrate()
    repository = TaskRepository(database)
    task = repository.create({"lng": 113.4872, "lat": 23.1068, "minutes": 15, "mode": "demo", "categories": ["market"]})
    repository.mark_running(task["id"])

    restarted_client = TestClient(create_app(FixtureMapProvider(), database_path))
    recovered = restarted_client.get(f"/api/analyze/{task['id']}")
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "failed"
    assert recovered.json()["stage_label"] == "服务重启已中断"
    assert "重新运行" in recovered.json()["error"]


def test_report_keeps_selected_center_address_and_method():
    provider = FixtureMapProvider()
    fixture_client = TestClient(create_app(provider))
    response = fixture_client.post(
        "/api/analyze",
        json={
            "lng": 113.51,
            "lat": 23.11,
            "center_address": "广州市黄埔区测试候选地址",
            "center_selection_method": "address",
        },
    )
    report = fixture_client.get(f"/api/report/{response.json()['id']}").json()
    assert report["center"]["lng"] == 113.51
    assert report["center"]["lat"] == 23.11
    assert report["center"]["address"] == "广州市黄埔区测试候选地址"
    assert report["center"]["selection_method"] == "address"


def test_report_recommendations_trace_back_to_actual_critical_regions():
    provider = LongWalkingFixtureMapProvider()
    fixture_client = TestClient(create_app(provider))
    response = fixture_client.post("/api/analyze", json={"minutes": 15, "categories": ["market", "school"]})
    report = fixture_client.get(f"/api/report/{response.json()['id']}").json()

    actual_critical_ids = {
        feature["properties"]["grid_id"]
        for feature in report["service_areas"]["features"]
        if feature["properties"]["kind"] == "critical"
    }
    assert report["recommendation_summary"]["status"] == "needs_action"
    assert report["recommendations"]
    for recommendation in report["recommendations"]:
        assert set(recommendation["target_region_ids"]) <= actual_critical_ids
        assert all(
            region_id.startswith(f"{recommendation['category']}-") for region_id in recommendation["target_region_ids"]
        )
        assert recommendation["priority_level"] in {"high", "medium"}
        assert recommendation["problem_basis"]
        assert recommendation["candidate_locations"]
        assert all(
            candidate["region_id"] in recommendation["target_region_ids"]
            for candidate in recommendation["candidate_locations"]
        )


def test_report_history_supports_keyword_filter_and_pagination(tmp_path):
    database_path = tmp_path / "history-search.db"
    provider = FixtureMapProvider()
    client = TestClient(create_app(provider, database_path))

    addresses = [
        "广州市黄埔区红山街道海韵东路",
        "广州市黄埔区大沙地东路",
        "深圳市南山区科技园",
    ]
    report_ids: list[str] = []
    for index, address in enumerate(addresses):
        created = client.post(
            "/api/analyze",
            json={
                "lng": 113.51 + index * 0.001,
                "lat": 23.11,
                "minutes": 15,
                "mode": "analysis",
                "categories": ["market"],
                "center_address": address,
                "center_selection_method": "address",
            },
        ).json()
        task = client.get(f"/api/analyze/{created['id']}").json()
        assert task["status"] == "completed"
        report_ids.append(task["report_id"])

    all_history = client.get("/api/reports/history").json()
    assert all_history["total"] == 3

    huangpu = client.get("/api/reports/history", params={"q": "黄埔"}).json()
    assert huangpu["total"] == 2
    assert {item["center"]["address"] for item in huangpu["items"]} == set(addresses[:2])

    haiyun = client.get("/api/reports/history", params={"q": "海韵东路"}).json()
    assert haiyun["total"] == 1
    assert haiyun["items"][0]["report_id"] == report_ids[0]

    shenzhen = client.get("/api/reports/history", params={"q": "深圳"}).json()
    assert shenzhen["total"] == 1
    assert shenzhen["items"][0]["report_id"] == report_ids[2]

    no_match = client.get("/api/reports/history", params={"q": "不存在的地址"}).json()
    assert no_match["total"] == 0
    assert no_match["items"] == []

    blank = client.get("/api/reports/history", params={"q": "   "}).json()
    assert blank["total"] == 3

    paginated = client.get("/api/reports/history", params={"q": "黄埔", "limit": 1, "offset": 0}).json()
    assert paginated["total"] == 2
    assert len(paginated["items"]) == 1
    paginated_next = client.get("/api/reports/history", params={"q": "黄埔", "limit": 1, "offset": 1}).json()
    assert paginated_next["total"] == 2
    assert len(paginated_next["items"]) == 1
    assert paginated_next["items"][0]["report_id"] != paginated["items"][0]["report_id"]

    escaped = client.get("/api/reports/history", params={"q": "%"}).json()
    assert escaped["total"] == 0
    underscore = client.get("/api/reports/history", params={"q": "_"}).json()
    assert underscore["total"] == 0
