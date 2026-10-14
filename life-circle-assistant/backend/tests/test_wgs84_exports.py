import json
import math
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from test_geospatial_report import ContractProvider

from app.exports import build_geojson_export, build_wgs84_geojson_export
from app.exports.wgs84 import bd09_to_wgs84
from app.main import create_app
from app.maps.provider import WalkingResult


def polygon(west=116.40, south=39.91, size=0.02):
    # 外环有意顺时针，内环有意逆时针，检验标准出口独立规范环方向。
    outer = [
        [west, south],
        [west, south + size],
        [west + size, south + size],
        [west + size, south],
        [west, south],
    ]
    inset = size / 4
    hole = [
        [west + inset, south + inset],
        [west + size - inset, south + inset],
        [west + size - inset, south + size - inset],
        [west + inset, south + size - inset],
        [west + inset, south + inset],
    ]
    return [outer, hole]


def standard_report():
    center = {
        "lng": 116.41036949371029,
        "lat": 39.92133699351021,
        "address": "北京测试点",
        "coordinate_system": "BD-09",
    }
    return {
        "report_id": "wgs84-test-report",
        "completed_at": "2026-10-14T08:00:00+00:00",
        "request": {"lng": center["lng"], "lat": center["lat"], "minutes": 15},
        "analysis_center": center,
        "isochrone": {
            "type": "Feature",
            "bbox": [116.40, 39.91, 116.42, 39.93],
            "crs": {"type": "name", "properties": {"name": "BD-09"}},
            "properties": {"coordinate_system": "BD-09", "area_sqm": 100},
            "geometry": {"type": "Polygon", "coordinates": polygon(), "bbox": [116.40, 39.91, 116.42, 39.93]},
        },
        "service_areas": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"kind": "critical", "coordinate_system": "BD-09"},
                    "geometry": {"type": "MultiPolygon", "coordinates": [polygon(), polygon(116.43)]},
                },
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {"type": "Point", "coordinates": [center["lng"], center["lat"], 13]},
                },
            ],
        },
        "recommendations": [{"id": "recommendation-1", "candidate_locations": [{**center, "id": "candidate-1"}]}],
        "data_quality": {"summary": "契约数据，并非真实现场标签"},
    }


def signed_area(ring):
    # 使用第一点平移后的独立鞋带式，避免大经纬度导致消减误差。
    lng, lat = ring[0][:2]
    points = [(point[0] - lng, point[1] - lat) for point in ring]
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:])) / 2


def point_in_ring(point, ring):
    inside = False
    lng, lat = point
    for first, second in zip(ring, ring[1:]):
        if (first[1] > lat) != (second[1] > lat):
            crossing_lng = first[0] + (lat - first[1]) * (second[0] - first[0]) / (second[1] - first[1])
            if lng < crossing_lng:
                inside = not inside
    return inside


def test_local_inverse_matches_independent_beijing_coordinate_anchor():
    # 常用北京锚点：GCJ-02(116.404,39.915)对应下列BD-09，
    # 其独立WGS84迭代参考值为(116.3977555,39.91359572)。
    # 数值容差只验证公式回归，不表示真实测绘误差。
    lng, lat = bd09_to_wgs84(116.41036949371029, 39.92133699351021)
    assert lng == pytest.approx(116.3977555, abs=1e-6)
    assert lat == pytest.approx(39.91359572, abs=1e-6)


def test_standard_export_preserves_geometry_holes_and_report_and_marks_source_parameters():
    report = standard_report()
    original = deepcopy(report)
    legacy_before = build_geojson_export(report).content
    artifact = build_wgs84_geojson_export(report)
    exported = json.loads(artifact.content)
    assert artifact.media_type == "application/geo+json"
    assert artifact.filename.endswith(".geojson")
    assert exported["coordinate_system"] == "WGS84"
    assert exported["source_coordinate_system"] == "BD-09"
    assert exported["parameters"] == report["request"]
    assert exported["parameters_coordinate_system"] == "BD-09"
    assert exported["conversion_method"] == "bd09_analytic_inverse_then_gcj02_iterative_inverse"
    assert exported["conversion_version"]
    assert exported["conversion_precision"]["approximate"] is True
    assert exported["conversion_precision"]["survey_grade"] is False
    assert exported["conversion_precision"]["verified_accuracy_m"] is None
    assert "测绘" in exported["conversion_precision"]["disclosure"]
    assert report == original
    assert build_geojson_export(report).content == legacy_before

    candidate = next(
        feature for feature in exported["features"] if feature["properties"]["layer"] == "planning_candidate"
    )
    center = exported["analysis_center"]
    assert center["coordinate_system"] == "WGS84"
    assert candidate["properties"]["coordinate_system"] == "WGS84"
    assert candidate["geometry"]["coordinates"] == [candidate["properties"]["lng"], candidate["properties"]["lat"]]
    assert candidate["geometry"]["coordinates"] == [center["lng"], center["lat"]]
    assert center["lng"] == pytest.approx(116.3977555, abs=1e-6)
    assert all(feature["properties"]["coordinate_system"] == "WGS84" for feature in exported["features"])
    assert exported["features"][2]["geometry"]["coordinates"][2] == 13
    assert exported["features"][0]["properties"]["area_sqm"] == 100

    geometries = [exported["features"][0]["geometry"], exported["features"][1]["geometry"]]
    transformed_center = [center["lng"], center["lat"]]
    # 锚点在原外环与孔洞内，转换后孔洞仍包含它且第二个离散片不包含它。
    assert point_in_ring([report["analysis_center"]["lng"], report["analysis_center"]["lat"]], polygon()[1])
    assert point_in_ring(transformed_center, geometries[0]["coordinates"][0])
    assert point_in_ring(transformed_center, geometries[0]["coordinates"][1])
    assert not point_in_ring(transformed_center, geometries[1]["coordinates"][1][0])
    for geometry in geometries:
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        assert len(polygons) == (1 if geometry["type"] == "Polygon" else 2)
        for rings in polygons:
            assert len(rings) == 2
            assert signed_area(rings[0]) > 0
            assert signed_area(rings[1]) < 0
            for ring in rings:
                assert len(ring) == 5
                assert ring[0] == ring[-1]
                assert all(math.isfinite(value) for point in ring for value in point)

    def no_legacy_spatial_members(value):
        if isinstance(value, dict):
            assert "crs" not in value and "bbox" not in value
            for nested in value.values():
                no_legacy_spatial_members(nested)
        elif isinstance(value, list):
            for nested in value:
                no_legacy_spatial_members(nested)

    no_legacy_spatial_members(exported)


@pytest.mark.parametrize(
    "position",
    [[math.nan, 30], [120, math.inf], [181, 30], [120, -91], [True, 30], [120, "30"], [120], [120, 30, math.nan]],
)
def test_invalid_positions_fail_explicitly_without_mutating_report(position):
    report = standard_report()
    report["service_areas"]["features"][1]["geometry"]["coordinates"] = position
    before = deepcopy(report)
    with pytest.raises(ValueError):
        build_wgs84_geojson_export(report)
    assert report["analysis_center"] == before["analysis_center"]
    assert report["isochrone"] == before["isochrone"]


@pytest.mark.parametrize("position", [[math.nan, 30], [120, math.inf], [181, 30], [120, -91], [True, 30], [120, "30"]])
def test_inverse_rejects_nonfinite_out_of_range_or_coerced_coordinates(position):
    with pytest.raises(ValueError):
        bd09_to_wgs84(*position)


def test_inverse_rejects_unrepresentable_large_integer_as_invalid_coordinate():
    with pytest.raises(ValueError):
        bd09_to_wgs84(10**1000, 30)


def test_gcj_window_boundary_nonconvergence_is_explicit_instead_of_claiming_precise_conversion():
    # 对应 GCJ-02(72.0041,35)的BD-09常数；逆解落出近似矩形窗口会反复跳跃。
    with pytest.raises(ValueError, match="未收敛"):
        bd09_to_wgs84(72.01048183224984, 35.00620348161468)


@pytest.mark.parametrize("scope", ["report", "center", "layer", "candidate"])
def test_inconsistent_declared_coordinate_system_cannot_be_double_converted(scope):
    report = standard_report()
    if scope == "report":
        report["calculation_mode"] = {"coordinate_system": "WGS84"}
    elif scope == "center":
        report["analysis_center"]["coordinate_system"] = "WGS84"
    elif scope == "layer":
        report["isochrone"]["properties"]["coordinate_system"] = "WGS84"
    else:
        report["recommendations"][0]["candidate_locations"][0]["coordinate_system"] = "WGS84"
    with pytest.raises(ValueError):
        build_wgs84_geojson_export(report)


@pytest.mark.parametrize("ring", [[[116.4, 39.91], [116.4, 39.92], [116.41, 39.92]], [[116.4, 39.91]] * 4])
def test_unclosed_or_degenerate_rings_are_not_silently_repaired(ring):
    report = standard_report()
    report["isochrone"]["geometry"]["coordinates"] = [ring]
    with pytest.raises(ValueError):
        build_wgs84_geojson_export(report)


class ExportContractProvider(ContractProvider):
    async def walking_matrix(self, origins, destinations):
        results = []
        for origin in origins:
            row = []
            for destination in destinations:
                distance = math.hypot(
                    (destination[0] - origin[0]) * 111_320 * math.cos(math.radians(origin[1])),
                    (destination[1] - origin[1]) * 111_320,
                )
                row.append(WalkingResult(origin, destination, True, distance, distance, "real_api", "contract_fixture"))
            results.append(row)
        return results


def test_actual_http_standard_export_is_wgs84_and_legacy_export_stays_bd09(tmp_path):
    with TestClient(create_app(ExportContractProvider(), tmp_path / "standard-export.db")) as client:
        created = client.post("/api/analyze", json={"categories": ["market"], "mode": "demo"})
        assert created.status_code == 200
        task = client.get(f"/api/analyze/{created.json()['id']}").json()
        assert task["status"] == "completed"
        report = task["result"]
        report_id = report["report_id"]
        standard = client.get(f"/api/reports/{report_id}/exports/geojson-wgs84")
        legacy = client.get(f"/api/reports/{report_id}/exports/geojson")
        assert standard.status_code == legacy.status_code == 200
        assert standard.headers["content-type"].startswith("application/geo+json")
        assert standard.headers["x-coordinate-system"] == "WGS84"
        assert legacy.headers["x-coordinate-system"] == "BD-09"
        assert standard.json()["coordinate_system"] == "WGS84"
        assert legacy.json()["coordinate_system"] == "BD-09"
        assert standard.json()["parameters"] == report["request"]
        assert standard.json()["analysis_center"]["lng"] != legacy.json()["analysis_center"]["lng"]
        candidate = next(
            feature for feature in standard.json()["features"] if feature["properties"]["layer"] == "planning_candidate"
        )
        assert candidate["geometry"]["coordinates"] == [candidate["properties"]["lng"], candidate["properties"]["lat"]]
        assert client.get(f"/api/reports/{report_id}").json() == report
        assert client.get("/api/reports/missing/exports/geojson-wgs84").status_code == 404


def test_http_rejects_degenerate_standard_geometry_and_preserves_legacy_report(tmp_path):
    with TestClient(create_app(ContractProvider(), tmp_path / "degenerate-export.db")) as client:
        created = client.post("/api/analyze", json={"categories": ["market"], "mode": "demo"})
        report = client.get(f"/api/analyze/{created.json()['id']}").json()["result"]
        report_id = report["report_id"]
        legacy_before = client.get(f"/api/reports/{report_id}/exports/geojson")
        rejected = client.get(f"/api/reports/{report_id}/exports/geojson-wgs84")
        assert rejected.status_code == 422
        assert "标准 GeoJSON 导出失败" in rejected.json()["detail"]
        assert "三个不同位置" in rejected.json()["detail"]
        assert legacy_before.status_code == 200
        assert client.get(f"/api/reports/{report_id}/exports/geojson").content == legacy_before.content
        assert client.get(f"/api/reports/{report_id}").json() == report
