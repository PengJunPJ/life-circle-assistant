from app.analysis.recommendations import build_planning_recommendations


def area_feature(
    grid_id: str,
    category: str,
    *,
    kind: str = "critical",
    lng: float = 113.48,
    lat: float = 23.10,
    nearest_name: str | None = "测试设施",
) -> dict:
    size = 0.002
    return {
        "type": "Feature",
        "properties": {
            "grid_id": grid_id,
            "kind": kind,
            "category": category,
            "candidate_facility_count": 0 if nearest_name is None else 1,
            "nearest_facility_id": f"{category}-facility" if nearest_name else None,
            "nearest_facility_name": nearest_name,
            "nearest_walk_minutes": 21 if nearest_name else None,
            "nearest_walk_distance_m": 1_700 if nearest_name else None,
            "basis": "最近同类设施步行 21 分钟且周边一公里内无同类设施。",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [lng, lat],
                [lng + size, lat],
                [lng + size, lat + size],
                [lng, lat + size],
                [lng, lat],
            ]],
        },
    }


def score(category: str, label: str, value: int, count: int = 1) -> dict:
    return {
        "category": category,
        "label": label,
        "score": value,
        "count": count,
        "status_explanation": "该类别覆盖较差。",
    }


def test_recommendations_reference_only_actual_same_category_critical_regions():
    market_a = area_feature("market-r1c1", "market", nearest_name=None)
    market_b = area_feature("market-r1c2", "market", lng=113.482, nearest_name=None)
    school_normal = area_feature("school-r2c2", "school", kind="normal")
    result = build_planning_recommendations(
        [score("market", "菜市场", 20, count=0), score("school", "小学", 90)],
        {"type": "FeatureCollection", "features": [market_a, market_b, school_normal]},
    )

    assert result["summary"]["status"] == "needs_action"
    assert len(result["recommendations"]) == 1
    recommendation = result["recommendations"][0]
    assert recommendation["category"] == "market"
    assert recommendation["priority_level"] == "high"
    assert recommendation["target_region_ids"] == ["market-r1c1", "market-r1c2"]
    assert recommendation["nearest_facility"]["status"] == "not_found"
    assert recommendation["target_improvement"]["estimated_area_sqm"] > 0
    assert recommendation["candidate_locations"][0]["related_region_ids"] == ["market-r1c1", "market-r1c2"]


def test_candidate_is_inside_referenced_critical_region_and_has_stable_explanation():
    feature = area_feature("medical-r3c4", "medical", lng=113.49, lat=23.11)
    first = build_planning_recommendations(
        [score("medical", "医疗服务", 55)],
        {"type": "FeatureCollection", "features": [feature]},
    )["recommendations"][0]
    second = build_planning_recommendations(
        [score("medical", "医疗服务", 55)],
        {"type": "FeatureCollection", "features": [feature]},
    )["recommendations"][0]

    candidate = first["candidate_locations"][0]
    polygon = feature["geometry"]["coordinates"][0]
    assert min(point[0] for point in polygon) <= candidate["lng"] <= max(point[0] for point in polygon)
    assert min(point[1] for point in polygon) <= candidate["lat"] <= max(point[1] for point in polygon)
    assert candidate["region_id"] == "medical-r3c4"
    assert "重点服务盲区 medical-r3c4 内" in candidate["reason"]
    assert first["id"] == second["id"] == "recommendation-medical-critical"
    assert candidate["id"] == second["candidate_locations"][0]["id"]


def test_no_critical_regions_returns_explicit_no_shortage_state():
    result = build_planning_recommendations(
        [score("school", "小学", 88)],
        {
            "type": "FeatureCollection",
            "features": [area_feature("school-r1c1", "school", kind="normal")],
        },
    )

    assert result["recommendations"] == []
    assert result["summary"] == {
        "status": "no_shortage",
        "message": "所选类别未发现重点服务盲区，当前无需生成补充设施建议。",
        "recommendation_count": 0,
        "target_region_count": 0,
    }
