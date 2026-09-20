from fastapi.testclient import TestClient

from app.main import app, create_app
from app.maps.provider import FacilityResult, LocationResult, MapProviderError, ProviderDescriptor, WalkingResult

client = TestClient(app)

def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_map_status_and_mock_geocode():
    status = client.get("/api/map/status")
    assert status.status_code == 200
    assert status.json()["mock_available"] is True
    geocode = client.get("/api/geocode", params={"address": "萝岗街道"})
    assert geocode.json()["source"] == "local_snapshot"
    unsupported = client.get("/api/geocode", params={"address": "广州市其他任意地址"})
    assert unsupported.status_code == 422
    assert "只支持内置" in unsupported.json()["detail"]


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
    assert body["data_quality"]["overall_status"] == "limited"
    assert "不代表最新真实地图测算" in body["data_quality"]["summary"]


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


def test_provider_can_be_replaced_without_real_baidu_requests():
    provider = FixtureMapProvider()
    fixture_client = TestClient(create_app(provider))

    geocode = fixture_client.get("/api/geocode", params={"address": "测试地址"})
    assert geocode.status_code == 200
    assert geocode.json()["result"]["location"] == {"lng": 113.5, "lat": 23.1}

    response = fixture_client.post("/api/analyze", json={"minutes": 15, "mode": "demo", "categories": ["market", "school"]})
    assert response.status_code == 200
    report = fixture_client.get(f"/api/report/{response.json()['id']}").json()

    assert report["source"] == "baidu"
    assert report["completeness"] == "complete"
    assert report["calculation_mode"]["provider_mode"] == "fixture"
    assert report["data_quality"]["sources"][0]["provider"] == "deterministic-test-provider"
    assert provider.calls.count("geocode") == 1
    assert "search_facilities:market" in provider.calls
    assert "search_facilities:school" in provider.calls
    assert "walking_matrix" in provider.calls


def test_category_failure_produces_partial_report_and_quality_event():
    provider = FixtureMapProvider(failing_category="school")
    fixture_client = TestClient(create_app(provider))
    response = fixture_client.post("/api/analyze", json={"categories": ["market", "school"]})
    report = fixture_client.get(f"/api/report/{response.json()['id']}").json()

    assert report["status"] == "completed"
    assert report["completeness"] == "partial"
    assert report["data_quality"]["overall_status"] == "partial"
    assert report["data_quality"]["partial_failures"][0]["category"] == "school"
    assert any(event["code"] == "category_partial" for event in report["data_quality"]["events"])


def test_analysis_request_rejects_empty_unknown_categories_and_invalid_coordinates():
    assert client.post("/api/analyze", json={"categories": []}).status_code == 422
    assert client.post("/api/analyze", json={"categories": ["park"]}).status_code == 422
    assert client.post("/api/analyze", json={"lng": 181}).status_code == 422
