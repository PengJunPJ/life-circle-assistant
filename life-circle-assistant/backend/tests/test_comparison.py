from __future__ import annotations

from copy import deepcopy

from fastapi.testclient import TestClient

from app.analysis.comparison import compare_reports
from app.main import create_app


def make_report(
    report_id: str,
    *,
    completed_at: str = "2026-09-20T08:00:00Z",
    address: str = "萝岗社区",
    lng: float = 113.4872,
    lat: float = 23.1068,
    categories: list[str] | None = None,
    score: int | None = 80,
    completeness: str = "complete",
) -> dict:
    selected = categories or ["market", "school"]
    scores = [
        {
            "category": category,
            "label": {"market": "菜市场", "school": "小学", "pharmacy": "药店"}.get(category, category),
            "count": index + 1,
            "score": 70 + index * 10,
            "valid_for_overall": True,
            "status": "valid",
            "status_label": "数据有效",
            "status_explanation": "类别数据完整。",
        }
        for index, category in enumerate(selected)
    ]
    features = []
    for category in selected:
        features.extend(
            {
                "type": "Feature",
                "properties": {"category": category, "kind": kind},
                "geometry": {"type": "Polygon", "coordinates": []},
            }
            for kind in ("normal", "sparse", "critical")
        )
    return {
        "report_id": report_id,
        "task_id": f"task-{report_id}",
        "status": "completed",
        "completeness": completeness,
        "completed_at": completed_at,
        "request": {"lng": lng, "lat": lat, "minutes": 15, "mode": "demo", "categories": selected},
        "analysis_center": {"address": address, "lng": lng, "lat": lat},
        "summary": {
            "score": score,
            "area_sqm": 1_000_000,
            "poi_count": sum(item["count"] for item in scores),
        },
        "category_scores": scores,
        "facilities": [],
        "service_areas": {"type": "FeatureCollection", "features": features},
    }


def test_compare_same_location_at_different_times_and_metric_deltas():
    left = make_report("left", completed_at="2026-09-20T08:00:00Z")
    right = make_report("right", completed_at="2026-09-21T08:00:00Z")
    right["summary"].update(score=86, area_sqm=1_120_000, poi_count=5)
    right["category_scores"][0].update(score=76, count=3)
    right["service_areas"]["features"].append(
        {
            "type": "Feature",
            "properties": {"category": "market", "kind": "normal"},
            "geometry": {"type": "Polygon", "coordinates": []},
        }
    )

    result = compare_reports(left, right)

    differences = {item["field"]: item for item in result["parameter_differences"]}
    assert differences["center"]["changed"] is False
    assert differences["completed_at"]["changed"] is True
    assert result["summary"]["overall_score"]["delta"] == 6
    assert result["summary"]["reachable_area_sqm"]["delta"] == 120_000
    assert result["summary"]["facility_count"]["delta"] == 2
    market = next(item for item in result["categories"] if item["category"] == "market")
    assert market["score"]["delta"] == 6
    assert market["facility_count"]["delta"] == 2
    assert market["service_area_counts"]["normal"]["delta"] == 1


def test_compare_different_locations_discloses_center_difference():
    left = make_report("left")
    right = make_report("right", address="科学城社区", lng=113.51, lat=23.13)

    result = compare_reports(left, right)

    center_difference = next(item for item in result["parameter_differences"] if item["field"] == "center")
    assert center_difference["changed"] is True
    assert result["reports"][1]["center"]["address"] == "科学城社区"
    assert result["reports"][0]["report_url"] == "/api/reports/left"


def test_different_category_combinations_are_explicitly_incomparable():
    left = make_report("left", categories=["market", "school"])
    right = make_report("right", categories=["market", "pharmacy"])

    result = compare_reports(left, right)

    assert result["category_scope"]["same_category_set"] is False
    assert result["category_scope"]["common"] == ["market"]
    assert result["category_scope"]["only_left"] == ["school"]
    assert result["category_scope"]["only_right"] == ["pharmacy"]
    assert result["summary"]["overall_score"]["delta"] is None
    assert "类别不同" in result["summary"]["overall_score"]["reason"]
    school = next(item for item in result["categories"] if item["category"] == "school")
    assert school["comparable"] is False
    assert "右侧报告未选择" in school["reason"]


def test_partial_report_invalid_category_is_not_silently_compared():
    left = make_report("left")
    right = deepcopy(make_report("right", completeness="partial", score=70))
    invalid = right["category_scores"][1]
    invalid.update(
        score=None,
        count=0,
        valid_for_overall=False,
        status="data_unavailable",
        status_label="数据不可用",
        status_explanation="设施检索失败。",
    )

    result = compare_reports(left, right)

    school = next(item for item in result["categories"] if item["category"] == "school")
    assert school["comparable"] is False
    assert school["score"]["delta"] is None
    assert "设施检索失败" in school["reason"]
    assert result["summary"]["overall_score"]["delta"] is None
    assert "有效类别不同" in result["summary"]["overall_score"]["reason"]


def test_comparison_api_limits_two_distinct_completed_reports(tmp_path):
    client = TestClient(create_app(database_path=tmp_path / "comparison.db"))
    first_task = client.post("/api/analyze", json={"categories": ["market", "school"]}).json()
    second_task = client.post(
        "/api/analyze",
        json={"minutes": 20, "mode": "analysis", "categories": ["market", "school"]},
    ).json()
    first_id = client.get(f"/api/analyze/{first_task['id']}").json()["report_id"]
    second_id = client.get(f"/api/analyze/{second_task['id']}").json()["report_id"]

    compared = client.post("/api/reports/compare", json={"report_ids": [first_id, second_id]})
    assert compared.status_code == 200
    assert compared.json()["report_ids"] == [first_id, second_id]
    assert next(item for item in compared.json()["parameter_differences"] if item["field"] == "minutes")["changed"] is True

    assert client.post("/api/reports/compare", json={"report_ids": [first_id]}).status_code == 422
    assert client.post("/api/reports/compare", json={"report_ids": [first_id, second_id, "extra"]}).status_code == 422
    duplicate = client.post("/api/reports/compare", json={"report_ids": [first_id, first_id]})
    assert duplicate.status_code == 422
    assert "两份不同" in duplicate.text
    invalid = client.post("/api/reports/compare", json={"report_ids": [first_id, "missing-report"]})
    assert invalid.status_code == 404
    assert "不存在或尚未完成" in invalid.json()["detail"]
