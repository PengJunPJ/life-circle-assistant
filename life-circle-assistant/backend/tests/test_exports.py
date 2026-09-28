import csv
import io
from datetime import datetime

from fastapi.testclient import TestClient

from app.exports import build_json_export
from app.main import create_app


def _create_standard_report(client: TestClient) -> dict:
    created = client.post(
        "/api/analyze",
        json={"minutes": 15, "mode": "analysis", "categories": ["market", "school"]},
    )
    assert created.status_code == 200
    task = client.get(f"/api/analyze/{created.json()['id']}").json()
    assert task["status"] == "completed"
    return task["result"]


def test_json_csv_and_geojson_exports_are_consistent_with_the_same_persisted_report(tmp_path):
    client = TestClient(create_app(database_path=tmp_path / "exports.db"))
    report = _create_standard_report(client)
    report_id = report["report_id"]
    completed_date = datetime.fromisoformat(report["completed_at"].replace("Z", "+00:00")).strftime("%Y%m%d")

    json_response = client.get(
        f"/api/reports/{report_id}/exports/json",
        headers={"Origin": "http://localhost:5173"},
    )
    csv_response = client.get(f"/api/reports/{report_id}/exports/csv")
    geojson_response = client.get(f"/api/reports/{report_id}/exports/geojson")

    assert json_response.status_code == csv_response.status_code == geojson_response.status_code == 200
    assert json_response.json() == report
    assert json_response.json()["data_quality"] == report["data_quality"]
    assert json_response.json()["recommendations"] == report["recommendations"]
    assert "Content-Disposition" in json_response.headers["access-control-expose-headers"]

    assert csv_response.content.startswith(b"\xef\xbb\xbf")
    csv_rows = list(csv.DictReader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
    assert {row["记录类型"] for row in csv_rows} == {"汇总", "类别评分", "设施明细"}
    assert {row["报告标识"] for row in csv_rows} == {report_id}
    assert {row["生成时间"] for row in csv_rows} == {report["completed_at"]}
    assert {row["坐标系"] for row in csv_rows} == {"BD-09"}
    assert {row["步行阈值(分钟)"] for row in csv_rows} == {"15"}
    assert {row["数据质量状态"] for row in csv_rows} == {report["data_quality"]["overall_status"]}
    assert all(row["数据质量说明"] for row in csv_rows)
    assert len([row for row in csv_rows if row["记录类型"] == "类别评分"]) == len(report["category_scores"])
    assert len([row for row in csv_rows if row["记录类型"] == "设施明细"]) == len(report["facilities"])
    assert all(row["类别名称"] for row in csv_rows if row["记录类型"] == "设施明细")

    geojson = geojson_response.json()
    assert geojson["type"] == "FeatureCollection"
    assert geojson["report_id"] == report_id
    assert geojson["generated_at"] == report["completed_at"]
    assert geojson["parameters"] == report["request"]
    assert geojson["coordinate_system"] == "BD-09"
    layers = {feature["properties"]["layer"] for feature in geojson["features"]}
    assert layers == {"isochrone", "service_area", "planning_candidate"}
    assert all(feature["properties"]["report_id"] == report_id for feature in geojson["features"])
    assert all(feature["properties"]["coordinate_system"] == "BD-09" for feature in geojson["features"])
    assert len([feature for feature in geojson["features"] if feature["properties"]["layer"] == "service_area"]) == len(
        report["service_areas"]["features"]
    )
    expected_candidates = sum(len(item["candidate_locations"]) for item in report["recommendations"])
    assert (
        len([feature for feature in geojson["features"] if feature["properties"]["layer"] == "planning_candidate"])
        == expected_candidates
    )

    for response, extension in ((json_response, "json"), (csv_response, "csv"), (geojson_response, "geojson")):
        disposition = response.headers["content-disposition"]
        assert completed_date in disposition
        assert report_id[:8] in disposition
        assert f".{extension}" in disposition
        assert (
            "/" not in disposition and "\\" not in disposition and "\r" not in disposition and "\n" not in disposition
        )
        assert response.headers["x-report-id"] == report_id
        assert response.headers["x-coordinate-system"] == "BD-09"


def test_exports_only_allow_existing_completed_reports(tmp_path):
    client = TestClient(create_app(database_path=tmp_path / "missing-export.db"))
    missing = client.get("/api/reports/not-found/exports/json")
    missing_pdf = client.get("/api/reports/not-found/exports/pdf")
    invalid = client.get("/api/reports/not-found/exports/xlsx")

    assert missing.status_code == 404
    assert missing_pdf.status_code == 404
    assert invalid.status_code == 422


def test_export_filename_removes_path_and_control_characters():
    artifact = build_json_export(
        {
            "report_id": "report-unsafe",
            "completed_at": "2026-09-20T08:00:00+00:00",
            "analysis_center": {"address": "黄埔/../../危险\r\n名称"},
        }
    )

    assert artifact.filename.endswith("-20260920-report-u.json")
    assert "/" not in artifact.filename
    assert "\\" not in artifact.filename
    assert "\r" not in artifact.filename
    assert "\n" not in artifact.filename
