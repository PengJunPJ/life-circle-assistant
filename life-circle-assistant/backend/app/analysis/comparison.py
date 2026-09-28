from __future__ import annotations

from typing import Any

from ..mock_data import CATEGORIES

REGION_KINDS = ("normal", "sparse", "critical")


def compare_reports(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """比较两份不可变报告，不修改来源报告，也不推测缺失或无效数据。"""

    left_categories = _selected_categories(left)
    right_categories = _selected_categories(right)
    left_set = set(left_categories)
    right_set = set(right_categories)
    common = [category for category in left_categories if category in right_set]
    only_left = [category for category in left_categories if category not in right_set]
    only_right = [category for category in right_categories if category not in left_set]

    category_comparisons = [
        _compare_category(category, left, right, category in left_set, category in right_set)
        for category in dict.fromkeys([*left_categories, *right_categories])
    ]
    comparable_categories = [item["category"] for item in category_comparisons if item["comparable"]]
    invalid_categories = [
        {
            "category": item["category"],
            "label": item["label"],
            "reason": item["reason"],
        }
        for item in category_comparisons
        if not item["comparable"]
    ]

    same_category_set = left_set == right_set
    comparable_set_matches = same_category_set and set(comparable_categories) == left_set
    summary = {
        "overall_score": _overall_score_comparison(left, right, same_category_set),
        "reachable_area_sqm": _numeric_comparison(
            _summary_value(left, "area_sqm"),
            _summary_value(right, "area_sqm"),
            unavailable_reason="任一报告缺少可达面积，无法计算差值。",
        ),
        "facility_count": _numeric_comparison(
            _summary_value(left, "poi_count"),
            _summary_value(right, "poi_count"),
            comparable=comparable_set_matches,
            unavailable_reason="类别集合不同或存在无效类别，设施总数不可直接比较。",
        ),
        "service_area_counts": {
            kind: _numeric_comparison(
                _total_region_count(left, kind),
                _total_region_count(right, kind),
                comparable=comparable_set_matches,
                unavailable_reason="类别集合不同或存在无效类别，服务区域总数不可直接比较。",
            )
            for kind in REGION_KINDS
        },
    }

    return {
        "report_ids": [left["report_id"], right["report_id"]],
        "reports": [_report_reference(left), _report_reference(right)],
        "parameter_differences": _parameter_differences(left, right),
        "category_scope": {
            "same_category_set": same_category_set,
            "common": common,
            "only_left": only_left,
            "only_right": only_right,
            "comparable": comparable_categories,
            "incomparable": invalid_categories,
        },
        "summary": summary,
        "categories": category_comparisons,
    }


def _report_reference(report: dict[str, Any]) -> dict[str, Any]:
    request = _request(report)
    center = report.get("analysis_center") or report.get("center") or {}
    report_id = report["report_id"]
    return {
        "report_id": report_id,
        "task_id": report.get("task_id"),
        "completed_at": report.get("completed_at"),
        "completeness": report.get("completeness", "complete"),
        "center": {
            "address": center.get("address") or "未命名分析中心",
            "lng": center.get("lng"),
            "lat": center.get("lat"),
        },
        "minutes": request.get("minutes"),
        "mode": request.get("mode"),
        "categories": list(request.get("categories") or []),
        "report_url": f"/api/reports/{report_id}",
    }


def _parameter_differences(left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, Any]]:
    left_request = _request(left)
    right_request = _request(right)
    left_center = left.get("analysis_center") or left.get("center") or {}
    right_center = right.get("analysis_center") or right.get("center") or {}
    left_categories = list(left_request.get("categories") or [])
    right_categories = list(right_request.get("categories") or [])
    fields = [
        ("center", "分析中心", _center_value(left_center), _center_value(right_center), None),
        ("completed_at", "生成时间", left.get("completed_at"), right.get("completed_at"), None),
        ("minutes", "步行阈值", left_request.get("minutes"), right_request.get("minutes"), None),
        ("mode", "分析模式", left_request.get("mode"), right_request.get("mode"), None),
        (
            "categories",
            "设施类别",
            left_categories,
            right_categories,
            set(left_categories) != set(right_categories),
        ),
    ]
    return [
        {
            "field": field,
            "label": label,
            "left": left_value,
            "right": right_value,
            "changed": left_value != right_value if changed is None else changed,
        }
        for field, label, left_value, right_value, changed in fields
    ]


def _compare_category(
    category: str,
    left: dict[str, Any],
    right: dict[str, Any],
    present_left: bool,
    present_right: bool,
) -> dict[str, Any]:
    left_score = _category_score(left, category)
    right_score = _category_score(right, category)
    comparable = present_left and present_right and _score_is_valid(left_score) and _score_is_valid(right_score)
    if not present_left:
        reason = "左侧报告未选择该类别。"
    elif not present_right:
        reason = "右侧报告未选择该类别。"
    elif not _score_is_valid(left_score):
        reason = f"左侧报告该类别数据无效：{_score_reason(left_score)}"
    elif not _score_is_valid(right_score):
        reason = f"右侧报告该类别数据无效：{_score_reason(right_score)}"
    else:
        reason = "两侧类别数据均有效，可直接比较。"

    left_regions = _region_counts(left, category)
    right_regions = _region_counts(right, category)
    return {
        "category": category,
        "label": _category_label(category, left_score, right_score),
        "present": {"left": present_left, "right": present_right},
        "comparable": comparable,
        "reason": reason,
        "score": _numeric_comparison(
            _score_value(left_score),
            _score_value(right_score),
            comparable=comparable,
            unavailable_reason=reason,
        ),
        "facility_count": _numeric_comparison(
            _category_facility_count(left, category, left_score) if present_left else None,
            _category_facility_count(right, category, right_score) if present_right else None,
            comparable=comparable,
            unavailable_reason=reason,
        ),
        "service_area_counts": {
            kind: _numeric_comparison(
                left_regions[kind] if present_left else None,
                right_regions[kind] if present_right else None,
                comparable=comparable,
                unavailable_reason=reason,
            )
            for kind in REGION_KINDS
        },
    }


def _overall_score_comparison(left: dict[str, Any], right: dict[str, Any], same_category_set: bool) -> dict[str, Any]:
    left_score = _summary_value(left, "score")
    right_score = _summary_value(right, "score")
    left_valid = set(_valid_categories(left))
    right_valid = set(_valid_categories(right))
    comparable = same_category_set and left_score is not None and right_score is not None and left_valid == right_valid
    if not same_category_set:
        reason = "两份报告选择的设施类别不同，综合分不可直接比较。"
    elif left_score is None or right_score is None:
        reason = "任一报告未形成有效综合分，无法计算差值。"
    elif left_valid != right_valid:
        reason = "两份报告纳入综合分的有效类别不同，综合分不可直接比较。"
    else:
        reason = "两份报告采用相同的有效类别范围。"
    return _numeric_comparison(left_score, right_score, comparable=comparable, unavailable_reason=reason)


def _numeric_comparison(
    left: Any,
    right: Any,
    *,
    comparable: bool = True,
    unavailable_reason: str,
) -> dict[str, Any]:
    values_available = (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        and isinstance(right, (int, float))
        and not isinstance(right, bool)
    )
    can_compare = comparable and values_available
    return {
        "left": left,
        "right": right,
        "delta": round(right - left, 2) if can_compare else None,
        "comparable": can_compare,
        "reason": None if can_compare else unavailable_reason,
    }


def _selected_categories(report: dict[str, Any]) -> list[str]:
    return list(_request(report).get("categories") or [])


def _request(report: dict[str, Any]) -> dict[str, Any]:
    return report.get("request") or report.get("parameters") or {}


def _category_score(report: dict[str, Any], category: str) -> dict[str, Any] | None:
    scores = report.get("category_scores") or report.get("categories") or []
    return next((item for item in scores if item.get("category") == category), None)


def _score_is_valid(score: dict[str, Any] | None) -> bool:
    return bool(score and score.get("valid_for_overall") and isinstance(score.get("score"), (int, float)))


def _score_value(score: dict[str, Any] | None) -> int | float | None:
    return score.get("score") if score else None


def _score_reason(score: dict[str, Any] | None) -> str:
    if not score:
        return "缺少类别评分数据。"
    return score.get("status_explanation") or score.get("status_label") or "类别数据不可用于比较。"


def _valid_categories(report: dict[str, Any]) -> list[str]:
    return [category for category in _selected_categories(report) if _score_is_valid(_category_score(report, category))]


def _category_label(category: str, *scores: dict[str, Any] | None) -> str:
    for score in scores:
        if score and score.get("label"):
            return str(score["label"])
    return CATEGORIES.get(category, {}).get("label", category)


def _category_facility_count(report: dict[str, Any], category: str, score: dict[str, Any] | None) -> int | None:
    if score and isinstance(score.get("count"), int):
        return score["count"]
    facilities = report.get("facilities") or report.get("pois")
    if not isinstance(facilities, list):
        return None
    return sum(item.get("category") == category for item in facilities)


def _region_counts(report: dict[str, Any], category: str) -> dict[str, int]:
    counts = {kind: 0 for kind in REGION_KINDS}
    collection = report.get("service_areas") or report.get("zones") or {}
    for feature in collection.get("features") or []:
        properties = feature.get("properties") or {}
        kind = properties.get("kind") or properties.get("region_type")
        if properties.get("category") == category and kind in counts:
            counts[kind] += 1
    return counts


def _total_region_count(report: dict[str, Any], kind: str) -> int:
    return sum(_region_counts(report, category)[kind] for category in _selected_categories(report))


def _summary_value(report: dict[str, Any], key: str) -> Any:
    return (report.get("summary") or {}).get(key)


def _center_value(center: dict[str, Any]) -> dict[str, Any]:
    return {"address": center.get("address"), "lng": center.get("lng"), "lat": center.get("lat")}
