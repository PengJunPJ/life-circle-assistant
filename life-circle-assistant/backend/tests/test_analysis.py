from fastapi.testclient import TestClient
from app.main import app

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
