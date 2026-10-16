from copy import deepcopy

from app.analysis.facility_normalization import normalize_facilities


def facility(
    identifier: str,
    name: str,
    category: str = "medical",
    lng: float = 113.4872,
    lat: float = 23.1068,
    address: str = "测试地址",
) -> dict:
    return {
        "id": identifier,
        "name": name,
        "category": category,
        "lng": lng,
        "lat": lat,
        "address": address,
    }


def test_normalizes_semantic_types_without_changing_facility_count():
    result = normalize_facilities(
        [
            facility("m1", "红山农贸市场", "market"),
            facility("p1", "大参林药店(红山店)", "pharmacy"),
            facility("s1", "广州市黄埔区文船小学", "school"),
            facility("h1", "红山街社区卫生服务中心"),
        ]
    )

    assert result.summary["input_count"] == 4
    assert result.summary["output_count"] == 4
    assert [item["semantic_type"] for item in result.facilities] == [
        "farmers_market",
        "pharmacy",
        "primary_school",
        "community_health_center",
    ]


def test_merges_medical_parent_and_subordinate_clinic_at_same_site():
    result = normalize_facilities(
        [
            facility("hospital", "广州亿仁医院"),
            facility("fever", "广州亿仁医院发热门诊", lng=113.48725, lat=23.1068),
            facility("emergency", "广州亿仁医院(急诊科)", lng=113.48718, lat=23.10682),
        ]
    )

    assert result.summary["merged_count"] == 2
    assert result.summary["merged_group_count"] == 1
    assert len(result.facilities) == 1
    normalized = result.facilities[0]
    assert normalized["name"] == "广州亿仁医院"
    assert normalized["canonical_name"] == "广州亿仁医院"
    assert normalized["semantic_type"] == "hospital"
    assert normalized["normalization"]["source_record_count"] == 3
    assert normalized["normalization"]["merged_facility_ids"] == ["hospital", "fever", "emergency"]


def test_merges_same_institution_with_district_prefix_at_same_site():
    result = normalize_facilities(
        [
            facility("center", "红山街社区卫生服务中心"),
            facility(
                "vaccination",
                "黄埔区红山街社区卫生服务中心预防接种门诊",
                lng=113.48722,
                lat=23.10682,
            ),
        ]
    )

    assert len(result.facilities) == 1
    assert result.facilities[0]["normalization"]["confidence"] == "medium"


def test_does_not_merge_same_institution_name_at_different_sites():
    result = normalize_facilities(
        [
            facility("clinic-a", "安康诊所"),
            facility("clinic-b", "安康诊所", lng=113.4972, lat=23.1068),
        ]
    )

    assert len(result.facilities) == 2
    assert result.summary["merged_count"] == 0


def test_does_not_merge_different_colocated_institutions():
    result = normalize_facilities([facility("a", "安康诊所"), facility("b", "惠民诊所")])

    assert len(result.facilities) == 2


def test_keeps_nearby_pharmacy_branches_independent():
    result = normalize_facilities(
        [
            facility("p1", "大参林药店(红山店)", "pharmacy"),
            facility("p2", "大参林药店(文船店)", "pharmacy", lng=113.48725),
        ]
    )

    assert len(result.facilities) == 2


def test_duplicate_provider_id_is_merged_and_preserves_aliases():
    result = normalize_facilities(
        [
            facility("same-id", "红山菜市场", "market"),
            facility("same-id", "红山农贸市场", "market", lng=113.49),
        ]
    )

    assert len(result.facilities) == 1
    assert result.facilities[0]["normalization"]["method"] == "provider_id_merge"
    assert result.facilities[0]["normalization"]["aliases"] == ["红山菜市场", "红山农贸市场"]


def test_missing_provider_ids_do_not_create_false_identity_matches():
    left = facility("left", "安康诊所")
    right = facility("right", "惠民诊所")
    left.pop("id")
    right.pop("id")

    result = normalize_facilities([left, right])

    assert len(result.facilities) == 2
    assert result.summary["merged_count"] == 0


def test_same_name_same_site_merge_without_provider_ids_has_no_fake_id():
    left = facility("left", "安康诊所")
    right = facility("right", "安康诊所", lng=113.48721)
    left.pop("id")
    right.pop("id")

    result = normalize_facilities([left, right])

    assert len(result.facilities) == 1
    normalization = result.facilities[0]["normalization"]
    assert normalization["method"] == "same_name_same_site_merge"
    assert normalization["merged_facility_ids"] == []


def test_normalization_retains_all_source_and_unverified_entrance_evidence():
    sources = [facility("parent", "仁和医院"), facility("clinic", "仁和医院急诊科", lng=113.48722)]
    for index, source in enumerate(sources):
        source["source"] = "baidu"
        source["evidence"] = {
            "provider_uid": source["id"],
            "original_location": {"lng": source["lng"], "lat": source["lat"]},
            "navigation_location": {"lng": 113.6 + index / 100, "lat": 23.2},
            "entrance_verified": False,
        }
    original = deepcopy(sources)
    result = normalize_facilities(sources).facilities[0]
    assert len(result["source_evidence"]) == 2
    assert {item["facility_id"] for item in result["source_evidence"]} == {"parent", "clinic"}
    assert all(item["evidence"]["entrance_verified"] is False for item in result["source_evidence"])
    assert result["lng"] == sources[0]["lng"]  # navigation coordinate never silently replaces the POI
    assert result["evidence"] == sources[0]["evidence"]
    assert sources == original
    result["source_evidence"][1]["evidence"]["navigation_location"]["lng"] = 1
    assert sources == original


def test_source_evidence_survives_repeated_normalization_without_duplicate_history():
    records = [facility("a", "仁和医院"), facility("b", "仁和医院急诊科")]
    records[0]["source_evidence"] = [{"facility_id": "earlier", "evidence": {"entrance_verified": False}}]
    first = normalize_facilities(records).facilities
    second = normalize_facilities(first).facilities
    assert len(first[0]["source_evidence"]) == 3
    assert second[0]["source_evidence"] == first[0]["source_evidence"]


def test_empty_source_history_still_captures_current_source():
    record = facility("a", "仁和医院")
    record["source_evidence"] = []
    record["evidence"] = {"entrance_verified": False}
    normalized = normalize_facilities([record]).facilities[0]
    assert len(normalized["source_evidence"]) == 1
    assert normalized["source_evidence"][0]["facility_id"] == "a"
    assert normalized["source_evidence"][0]["evidence"] == record["evidence"]


def test_current_evidence_change_is_preserved_alongside_previous_history():
    record = facility("a", "仁和医院")
    record["evidence"] = {"entrance_verified": False}
    normalized = normalize_facilities([record]).facilities[0]
    normalized["evidence"] = {"entrance_verified": True, "verified_by": "human"}
    revised = normalize_facilities([normalized]).facilities[0]
    assert len(revised["source_evidence"]) == 2
    assert [trace["evidence"]["entrance_verified"] for trace in revised["source_evidence"]] == [False, True]


def test_missing_ids_preserve_names_for_colocated_parent_and_department():
    records = [facility("a", "仁和医院"), facility("b", "仁和医院急诊科")]
    for record in records:
        record.pop("id")
    normalized = normalize_facilities(records).facilities[0]
    assert len(normalized["source_evidence"]) == 2
    assert {trace["name"] for trace in normalized["source_evidence"]} == {"仁和医院", "仁和医院急诊科"}
