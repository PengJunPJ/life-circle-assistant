from __future__ import annotations

from fastapi.testclient import TestClient

from app.baidu import haversine_meters
from app.main import create_app
from app.maps.provider import FacilityResult, LocationResult, ProviderDescriptor, WalkingResult


class SimulationFixtureProvider:
    @property
    def descriptor(self):
        return ProviderDescriptor(
            id="simulation-fixture",
            mode="fixture",
            source="real_api",
            label="模拟测试地图提供方",
            is_latest_real_measurement=True,
        )

    async def geocode(self, address: str, city: str = "广州"):
        return [LocationResult(lng=113.5, lat=23.1, address=f"{city}{address}")]

    async def reverse_geocode(self, lng: float, lat: float):
        return LocationResult(lng=lng, lat=lat, address="测试中心点")

    async def search_places(self, query: str, center: tuple[float, float], radius_m: int = 1000):
        return []

    async def search_facilities(self, category: str, center: tuple[float, float], radius_m: int = 1000):
        if category == "market":
            return [
                FacilityResult(
                    id="market-far",
                    name="远端菜市场",
                    category=category,
                    lng=center[0] + 0.026,
                    lat=center[1],
                )
            ]
        return [
            FacilityResult(
                id=f"{category}-near",
                name="邻近小学",
                category=category,
                lng=center[0] + 0.001,
                lat=center[1] + 0.001,
            )
        ]

    async def walking_matrix(
        self,
        origins: list[tuple[float, float]],
        destinations: list[tuple[float, float]],
    ):
        return [
            [
                WalkingResult(
                    origin=origin,
                    destination=destination,
                    success=True,
                    distance_m=haversine_meters(origin, destination),
                    duration_s=haversine_meters(origin, destination) / 1.2,
                    source="real_api",
                    method="distance_based_fixture",
                )
                for destination in destinations
            ]
            for origin in origins
        ]


def test_simulation_only_recalculates_selected_category_and_keeps_source_report_immutable(tmp_path):
    client = TestClient(create_app(SimulationFixtureProvider(), tmp_path / "simulation.db"))
    created = client.post(
        "/api/analyze",
        json={"lng": 113.5, "lat": 23.1, "minutes": 15, "categories": ["market", "school"]},
    ).json()
    source_report = client.get(f"/api/report/{created['id']}").json()
    report_id = source_report["report_id"]
    original_school_score = next(item for item in source_report["category_scores"] if item["category"] == "school")
    original_facilities = source_report["facilities"]

    response = client.post(
        f"/api/reports/{report_id}/simulations",
        json={
            "category": "market",
            "lng": 113.5,
            "lat": 23.1,
            "selection_method": "map",
        },
    )

    assert response.status_code == 200
    simulation = response.json()
    assert simulation["category"] == "market"
    assert simulation["hypothetical_facility"]["is_hypothetical"] is True
    assert simulation["after"]["category_score"] > simulation["before"]["category_score"]
    assert simulation["after"]["coverage_area_sqm"] > simulation["before"]["coverage_area_sqm"]
    assert simulation["after"]["critical_zone_count"] < simulation["before"]["critical_zone_count"]
    assert {feature["properties"]["category"] for feature in simulation["after"]["service_areas"]["features"]} == {
        "market"
    }
    assert simulation["unaffected_category_scores"] == [original_school_score]

    reloaded = client.get(f"/api/reports/{report_id}").json()
    assert reloaded == source_report
    assert reloaded["facilities"] == original_facilities
    assert all(not item.get("is_hypothetical") for item in reloaded["facilities"])


def test_simulation_accepts_recommendation_candidate_and_rejects_unselected_category(tmp_path):
    client = TestClient(create_app(SimulationFixtureProvider(), tmp_path / "candidate-simulation.db"))
    created = client.post(
        "/api/analyze",
        json={"lng": 113.5, "lat": 23.1, "minutes": 15, "categories": ["market", "school"]},
    ).json()
    report = client.get(f"/api/report/{created['id']}").json()
    recommendation = next(item for item in report["recommendations"] if item["category"] == "market")
    candidate = recommendation["candidate_locations"][0]

    accepted = client.post(
        f"/api/reports/{report['report_id']}/simulations",
        json={
            "category": "market",
            "lng": 0,
            "lat": 0,
            "selection_method": "recommendation",
            "candidate_id": candidate["id"],
        },
    )
    assert accepted.status_code == 422

    accepted = client.post(
        f"/api/reports/{report['report_id']}/simulations",
        json={
            "category": "market",
            "lng": candidate["lng"],
            "lat": candidate["lat"],
            "selection_method": "recommendation",
            "candidate_id": candidate["id"],
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["candidate_id"] == candidate["id"]
    assert accepted.json()["hypothetical_facility"]["lng"] == candidate["lng"]

    rejected = client.post(
        f"/api/reports/{report['report_id']}/simulations",
        json={
            "category": "medical",
            "lng": 113.5,
            "lat": 23.1,
            "selection_method": "map",
        },
    )
    assert rejected.status_code == 422
    assert "已选择" in rejected.json()["detail"]
