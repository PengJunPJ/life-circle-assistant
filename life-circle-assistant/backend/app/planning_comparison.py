"""Deterministic comparison of independent, single-facility simulations."""

from __future__ import annotations

import math
from typing import Any

GOALS = {
    "reduce_critical_zones": ("减少重点盲区", "critical_zone_count", -1),
    "increase_coverage": ("扩大分类覆盖面积", "coverage_area_sqm", 1),
    "improve_overall_score": ("提高综合指数", "overall_score", 1),
}

DISCLOSURE = (
    "各方案独立新增一处设施，均与同一原报告比较，不是叠加建设方案。"
    "覆盖面积按该类别正常与稀疏网格面积之和计算，不代表人口覆盖或严格等时圈面积。"
    "未计算成本、用地许可、设施容量或现场可行性；排名仅反映所选目标。"
)


def exclusion_reason(report: dict[str, Any], simulation: dict[str, Any], goal: str) -> str | None:
    before, after = simulation["before"], simulation["after"]
    if simulation["data_quality"].get("partial_failures"):
        return "部分路线计算失败，改善量不参与排名"
    if not all(snap["category_score_detail"].get("valid_for_overall") for snap in (before, after)):
        return "该类别原始或模拟评分不完整，不参与排名"
    if goal == "improve_overall_score" and report.get("scoring", {}).get("status") != "complete":
        return "原报告综合指数缺少类别，权重基线不完整，不参与排名"
    if goal != "improve_overall_score":
        grids = [snap["service_areas"]["features"] for snap in (before, after)]
        if not all(grids):
            return "该类别没有可比较网格，面积与盲区目标不适用"
        if any(f["properties"].get("kind") == "unknown" for group in grids for f in group):
            return "原始或模拟网格存在未知结果，不参与排名"
        # Reject unequal sampling footprints, even if a provider returns plausible deltas.
        footprints = [{f["properties"]["grid_id"]: f["geometry"] for f in group} for group in grids]
        if footprints[0] != footprints[1]:
            return "原始与模拟网格范围不一致，不参与排名"
    metric = GOALS[goal][1]
    value = simulation["delta"].get(metric)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return "目标指标缺失，不参与排名"
    return None


def finalize_comparison(comparison: dict[str, Any]) -> dict[str, Any]:
    goal = comparison["goal"]
    label, metric, direction = GOALS[goal]
    eligible = [option for option in comparison["options"] if option.get("eligible")]
    for option in comparison["options"]:
        option["rank"] = None
    ordered = sorted(eligible, key=lambda option: option["delta"][metric] * direction, reverse=True)
    ranks: dict[float, int] = {}
    for index, option in enumerate(ordered, start=1):
        improvement = option["delta"][metric] * direction
        ranks.setdefault(improvement, index)
        option["objective_improvement"] = improvement
        if len(eligible) >= 2:
            option["rank"] = ranks[improvement]
    best = ordered[0]["objective_improvement"] if ordered else None
    leaders = [option for option in ordered if option["objective_improvement"] == best]
    comparison["preferred_option_ids"] = [option["id"] for option in leaders] if len(eligible) >= 2 and best > 0 else []
    if len(eligible) < 2:
        conclusion = "可比较结果不足，无法确定优先方案。"
    elif best <= 0:
        conclusion = "所有可比较方案均未改善所选目标，不推荐优先方案。"
    else:
        names = "、".join(option["title"] for option in leaders)
        conclusion = f"按“{label}”，{names}{'并列' if len(leaders) > 1 else ''}优先；仍需现场核验。"
    comparison["summary"] = conclusion
    comparison["evidence_refs"] = [
        {
            "type": "comparison",
            "id": comparison["id"],
            "label": f"方案对比：{label}",
            "detail": conclusion + DISCLOSURE,
        }
    ]
    return comparison
