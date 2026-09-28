from app.analysis.scoring import score_category, score_report

CENTER = (113.4872, 23.1068)


def facility(
    identifier: str,
    lng: float,
    lat: float,
    walk_minutes: float | None,
    category: str = "market",
):
    return {
        "id": identifier,
        "name": identifier,
        "category": category,
        "lng": lng,
        "lat": lat,
        "walk_minutes": walk_minutes,
    }


def component(result, key: str):
    return next(item for item in result["components"] if item["key"] == key)


def test_zero_facilities_receive_no_positive_component_or_category_score():
    result = score_category("market", [], CENTER)

    assert result["status"] == "poor_coverage"
    assert result["valid_for_overall"] is True
    assert result["score"] == 0
    assert [item["score"] for item in result["components"]] == [0, 0, 0]
    assert "最近步行时间得分为 0" in component(result, "walking_time")["reason"]


def test_single_nearby_facility_reports_three_weighted_components():
    result = score_category(
        "market",
        [facility("market-1", 113.488, 23.108, 5)],
        CENTER,
    )

    assert result["status"] == "valid"
    assert result["score"] == 49
    assert [(item["key"], item["weight_percent"]) for item in result["components"]] == [
        ("quantity", 40),
        ("walking_time", 40),
        ("spatial_distribution", 20),
    ]
    assert component(result, "walking_time")["score"] == 75


def test_multiple_well_distributed_facilities_get_full_distribution_score():
    facilities = [
        facility("ne", CENTER[0] + 0.002, CENTER[1] + 0.002, 5),
        facility("nw", CENTER[0] - 0.002, CENTER[1] + 0.002, 6),
        facility("se", CENTER[0] + 0.002, CENTER[1] - 0.002, 7),
        facility("sw", CENTER[0] - 0.002, CENTER[1] - 0.002, 8),
    ]

    result = score_category("market", facilities, CENTER)

    assert component(result, "spatial_distribution")["score"] == 100
    assert component(result, "spatial_distribution")["observed_value"] == 4
    assert result["score"] == 90


def test_missing_walking_data_is_not_misreported_as_poor_coverage_or_a_score():
    result = score_category(
        "market",
        [facility("market-1", 113.488, 23.108, None)],
        CENTER,
    )

    assert result["status"] == "calculation_incomplete"
    assert result["valid_for_overall"] is False
    assert result["score"] is None
    assert component(result, "walking_time")["score"] is None
    assert "步行时间全部计算失败" in component(result, "walking_time")["reason"]


def test_partial_category_failure_is_excluded_and_valid_weights_are_normalized():
    facilities = [
        facility("market-1", 113.488, 23.108, 5, "market"),
        facility("school-1", 113.486, 23.105, 8, "school"),
    ]

    result = score_report(
        ["market", "pharmacy", "school"],
        facilities,
        CENTER,
        failed_categories={"pharmacy"},
    )

    assert result["overall"]["status"] == "partial"
    assert result["overall"]["valid_category_count"] == 2
    assert result["overall"]["score"] == 46
    weights = {item["category"]: item for item in result["overall"]["category_weights"]}
    assert weights["market"]["applied_weight"] == 0.5
    assert weights["school"]["applied_weight"] == 0.5
    assert weights["pharmacy"]["applied_weight"] == 0
    assert weights["pharmacy"]["included"] is False


def test_no_valid_categories_suppresses_the_overall_score():
    result = score_report(["market"], [], CENTER, failed_categories={"market"})

    assert result["overall"]["status"] == "unavailable"
    assert result["overall"]["score"] is None
    assert result["category_scores"][0]["status"] == "data_unavailable"
