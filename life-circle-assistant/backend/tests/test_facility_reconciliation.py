from app.analysis.facility_reconciliation import reconcile_facilities


def record(
    source: str,
    identifier: str,
    name: str,
    *,
    category: str = "market",
    lng: float = 113.4872,
    lat: float = 23.1068,
    address: str = "广州市黄埔区红山街测试路 1 号",
) -> dict:
    return {
        "source": source,
        "source_record_id": identifier,
        "name": name,
        "category": category,
        "lng": lng,
        "lat": lat,
        "address": address,
        "coordinate_system": "bd09",
        "retrieved_at": "2026-10-10T00:00:00Z",
    }


def test_reconciles_nearby_cross_source_records_and_keeps_provenance():
    result = reconcile_facilities(
        [
            record("baidu", "b-1", "红山菜市场"),
            record("amap", "a-1", "红山农贸市场", lng=113.48745, address="黄埔区红山街测试路 1 号"),
        ]
    )

    assert result.summary["input_count"] == 2
    assert result.summary["merged_count"] == 1
    assert result.summary["unmatched_count"] == 0
    assert len(result.facilities) == 1
    merged = result.facilities[0]
    assert merged["reconciliation"]["status"] == "matched"
    assert merged["reconciliation"]["source_record_ids"] == ["amap:a-1", "baidu:b-1"]
    assert merged["reconciliation"]["match_confidence"] == "high"


def test_does_not_merge_same_name_far_apart_branches():
    result = reconcile_facilities(
        [
            record("baidu", "b-1", "安康药店", category="pharmacy"),
            record("amap", "a-1", "安康药店", category="pharmacy", lng=113.4972),
        ]
    )

    assert result.summary["merged_count"] == 0
    assert result.summary["unmatched_count"] == 2
    assert all(item["reconciliation"]["status"] == "unmatched" for item in result.facilities)


def test_conflicting_nearby_records_are_not_silently_merged():
    result = reconcile_facilities(
        [
            record("baidu", "b-1", "红山菜市场"),
            record("amap", "a-1", "红山便利店", category="convenience", lng=113.4873),
        ]
    )

    assert result.summary["conflict_count"] == 1
    assert result.summary["merged_count"] == 0
    assert result.decisions[0]["decision"] == "category_conflict"


def test_fresh_source_is_selected_as_representative():
    old = record("baidu", "b-1", "旧名称")
    old["retrieved_at"] = "2026-09-01T00:00:00Z"
    fresh = record("amap", "a-1", "新名称", lng=113.4873)
    result = reconcile_facilities([old, fresh])

    assert result.facilities[0]["name"] == "新名称"
    assert result.facilities[0]["reconciliation"]["selected_source"] == "amap"


def test_records_between_50_and_100_metres_require_manual_review():
    result = reconcile_facilities(
        [
            record("baidu", "b-1", "红山菜市场"),
            record("amap", "a-1", "红山菜市场", lng=113.48785),
        ]
    )

    assert result.summary["merged_count"] == 0
    assert result.decisions[0]["decision"] == "needs_review"


def test_records_in_different_coordinate_systems_are_never_distance_matched():
    amap = record("amap", "a-1", "红山菜市场", lng=113.4873)
    amap["coordinate_system"] = "amap_gcj02"
    result = reconcile_facilities([record("baidu", "b-1", "红山菜市场"), amap])

    assert result.summary["merged_count"] == 0
    assert result.decisions[0]["decision"] == "coordinate_system_conflict"
    assert result.decisions[0]["distance_m"] is None


def test_source_priority_breaks_equal_observation_time_ties():
    lower_priority = record("baidu", "b-1", "百度名称")
    lower_priority["source_priority"] = 10
    higher_priority = record("amap", "a-1", "高德名称", lng=113.4873)
    higher_priority["source_priority"] = 20
    result = reconcile_facilities([lower_priority, higher_priority])

    assert result.facilities[0]["name"] == "高德名称"
    assert result.facilities[0]["reconciliation"]["selected_source"] == "amap"
