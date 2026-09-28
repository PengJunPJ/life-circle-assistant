from __future__ import annotations

from typing import Any

from ..mock_data import CATEGORIES

COMPONENT_WEIGHTS = {
    "quantity": 0.4,
    "walking_time": 0.4,
    "spatial_distribution": 0.2,
}


def score_report(
    selected_categories: list[str],
    facilities: list[dict[str, Any]],
    center: tuple[float, float],
    failed_categories: set[str] | None = None,
    calculation_failed_categories: set[str] | None = None,
) -> dict[str, Any]:
    """生成类别评分及只基于有效类别的综合评分。"""

    failed = failed_categories or set()
    calculation_failed = calculation_failed_categories or set()
    category_scores = [
        score_category(
            category,
            [facility for facility in facilities if facility["category"] == category],
            center,
            facility_search_failed=category in failed,
            calculation_failed=category in calculation_failed,
        )
        for category in selected_categories
    ]
    overall = aggregate_overall_score(category_scores)

    return {
        "overall": overall,
        "category_scores": category_scores,
    }


def aggregate_overall_score(category_scores: list[dict[str, Any]]) -> dict[str, Any]:
    """按当前有效类别重新归一化权重，供完整分析和单类别模拟共同使用。"""

    valid_scores = [item for item in category_scores if item["valid_for_overall"]]
    configured_total = sum(item["configured_weight"] for item in valid_scores)

    for item in category_scores:
        item["applied_weight"] = (
            round(item["configured_weight"] / configured_total, 6)
            if item["valid_for_overall"] and configured_total
            else 0
        )

    if not valid_scores:
        overall_score = None
        status = "unavailable"
        explanation = "没有可完整核验的有效类别，因此不展示综合生活圈指数。"
    else:
        overall_score = round(sum(item["score"] * item["applied_weight"] for item in valid_scores))
        if len(valid_scores) == len(category_scores):
            status = "complete"
            explanation = f"综合分按 {len(valid_scores)} 个有效已选类别的实际权重计算。"
        else:
            status = "partial"
            explanation = (
                f"仅按 {len(valid_scores)} 个有效类别重新归一化权重计算；"
                f"另有 {len(category_scores) - len(valid_scores)} 个类别因数据不完整被排除。"
            )

    return {
        "score": overall_score,
        "status": status,
        "selected_category_count": len(category_scores),
        "valid_category_count": len(valid_scores),
        "component_weights": {
            key: {"weight": weight, "weight_percent": round(weight * 100)} for key, weight in COMPONENT_WEIGHTS.items()
        },
        "category_weights": [
            {
                "category": item["category"],
                "label": item["label"],
                "configured_weight": item["configured_weight"],
                "applied_weight": item["applied_weight"],
                "included": item["valid_for_overall"],
                "reason": item["status_explanation"],
            }
            for item in category_scores
        ],
        "explanation": explanation,
    }


def score_category(
    category: str,
    facilities: list[dict[str, Any]],
    center: tuple[float, float],
    *,
    facility_search_failed: bool = False,
    calculation_failed: bool = False,
) -> dict[str, Any]:
    category_config = CATEGORIES[category]
    count = len(facilities)
    walking_values = [float(item["walk_minutes"]) for item in facilities if item.get("walk_minutes") is not None]
    nearest = min(walking_values, default=None)
    missing_walking_count = count - len(walking_values)

    if facility_search_failed:
        status = "data_unavailable"
        status_label = "数据不可用"
        status_explanation = "设施检索失败，不能把未知数量解释为真实零设施。"
        valid_for_overall = False
    elif calculation_failed:
        status = "calculation_incomplete"
        status_label = "计算不完整"
        status_explanation = "该类别存在步行超时、限流、格式错误或部分网格失败，不纳入综合分。"
        valid_for_overall = False
    elif count == 0:
        status = "poor_coverage"
        status_label = "真实覆盖较差"
        status_explanation = "设施检索成功但未发现有效设施，该类别按真实零覆盖计分。"
        valid_for_overall = True
    elif missing_walking_count:
        status = "calculation_incomplete"
        status_label = "计算不完整"
        status_explanation = f"{count} 个设施中有 {missing_walking_count} 个缺少步行结果，该类别不纳入综合分。"
        valid_for_overall = False
    else:
        status = "valid"
        status_label = "数据有效"
        status_explanation = "设施数量、最近步行时间和空间分布均可核验。"
        valid_for_overall = True

    components = [
        _quantity_component(count, facility_search_failed),
        _walking_component(count, walking_values, facility_search_failed, calculation_failed),
        _distribution_component(facilities, center, facility_search_failed),
    ]
    component_scores = [component["score"] for component in components]
    score = (
        round(sum(component["weighted_score"] for component in components))
        if valid_for_overall and all(value is not None for value in component_scores)
        else None
    )

    return {
        "category": category,
        "label": category_config["label"],
        "count": count,
        "nearest_walk_minutes": nearest,
        "score": score,
        "color": category_config["color"],
        "status": status,
        "status_label": status_label,
        "status_explanation": status_explanation,
        "valid_for_overall": valid_for_overall,
        "configured_weight": category_config["weight"] / 100,
        "applied_weight": 0,
        "components": components,
    }


def _quantity_component(count: int, unavailable: bool) -> dict[str, Any]:
    if unavailable:
        return _component(
            "quantity",
            "设施数量",
            None,
            None,
            "设施检索失败，数量数据不可用。",
            None,
            "个",
        )
    score = min(100, count * 35)
    if count == 0:
        reason = "未检索到有效设施，数量得分为 0。"
    elif count == 1:
        reason = "仅有 1 个设施，数量保障有限。"
    elif count == 2:
        reason = "共有 2 个设施，仍有补充空间。"
    else:
        reason = f"共有 {count} 个设施，达到数量满分标准。"
    return _component("quantity", "设施数量", score, score * COMPONENT_WEIGHTS["quantity"], reason, count, "个")


def _walking_component(
    count: int,
    walking_values: list[float],
    unavailable: bool,
    calculation_failed: bool = False,
) -> dict[str, Any]:
    if unavailable:
        return _component(
            "walking_time",
            "最近步行时间",
            None,
            None,
            "设施检索失败，无法计算最近步行时间。",
            None,
            "分钟",
        )
    if calculation_failed:
        return _component(
            "walking_time",
            "最近步行时间",
            None,
            None,
            "步行结果不完整，该类别不生成可用于综合分的步行子分。",
            min(walking_values, default=None),
            "分钟",
        )
    if count == 0:
        return _component(
            "walking_time",
            "最近步行时间",
            0,
            0,
            "确认没有有效设施，最近步行时间得分为 0。",
            None,
            "分钟",
        )
    if not walking_values:
        return _component(
            "walking_time",
            "最近步行时间",
            None,
            None,
            "已发现设施，但步行时间全部计算失败。",
            None,
            "分钟",
        )
    nearest = min(walking_values)
    score = max(0, round((1 - nearest / 20) * 100))
    suffix = "" if len(walking_values) == count else f"；仅 {len(walking_values)}/{count} 个设施有有效步行结果"
    reason = f"最近设施步行约 {nearest:g} 分钟，按 20 分钟线性降分规则计 {score} 分{suffix}。"
    return _component(
        "walking_time",
        "最近步行时间",
        score,
        score * COMPONENT_WEIGHTS["walking_time"],
        reason,
        nearest,
        "分钟",
    )


def _distribution_component(
    facilities: list[dict[str, Any]],
    center: tuple[float, float],
    unavailable: bool,
) -> dict[str, Any]:
    if unavailable:
        return _component(
            "spatial_distribution",
            "空间分布",
            None,
            None,
            "设施检索失败，空间分布数据不可用。",
            None,
            "方向象限",
        )
    if not facilities:
        return _component(
            "spatial_distribution",
            "空间分布",
            0,
            0,
            "没有有效设施，空间分布得分为 0。",
            0,
            "方向象限",
        )

    occupied_quadrants = len({_quadrant(item, center) for item in facilities})
    score = round((occupied_quadrants / 4) * 80 + (min(len(facilities), 4) / 4) * 20)
    reason = f"{len(facilities)} 个设施覆盖中心点周边 4 个方向象限中的 {occupied_quadrants} 个，空间分布计 {score} 分。"
    return _component(
        "spatial_distribution",
        "空间分布",
        score,
        score * COMPONENT_WEIGHTS["spatial_distribution"],
        reason,
        occupied_quadrants,
        "方向象限",
    )


def _quadrant(facility: dict[str, Any], center: tuple[float, float]) -> tuple[bool, bool]:
    return float(facility["lng"]) >= center[0], float(facility["lat"]) >= center[1]


def _component(
    key: str,
    label: str,
    score: int | None,
    weighted_score: float | None,
    reason: str,
    observed_value: int | float | None,
    observed_unit: str,
) -> dict[str, Any]:
    weight = COMPONENT_WEIGHTS[key]
    return {
        "key": key,
        "label": label,
        "weight": weight,
        "weight_percent": round(weight * 100),
        "score": score,
        "weighted_score": round(weighted_score, 2) if weighted_score is not None else None,
        "observed_value": observed_value,
        "observed_unit": observed_unit,
        "reason": reason,
    }
