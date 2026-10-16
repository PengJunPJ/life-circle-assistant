"""有限候选最大覆盖：显式硬约束，实测覆盖证据，确定性基线与小规模精确解。"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from ..maps.provider import MapProvider, MapProviderError, WalkingResult


@dataclass(frozen=True)
class CoverageCandidate:
    id: str
    grid_ids: frozenset[str]
    cost: float | None = None


def optimize_maximum_coverage(
    candidates: Sequence[CoverageCandidate],
    *,
    max_facilities: int,
    budget: float | None = None,
    method: Literal["auto", "exact", "greedy"] = "auto",
) -> dict[str, Any]:
    if isinstance(max_facilities, bool) or not isinstance(max_facilities, int) or not 0 <= max_facilities <= 32:
        raise ValueError("新增设施数量上限必须为 0 到 32 的整数")
    if len(candidates) > 32 or len({item.id for item in candidates}) != len(candidates):
        raise ValueError("候选点最多 32 个且标识不得重复")
    if budget is not None and (isinstance(budget, bool) or not math.isfinite(budget) or budget < 0):
        raise ValueError("预算必须为非负有限数")
    if any(
        item.cost is not None and (isinstance(item.cost, bool) or not math.isfinite(item.cost) or item.cost < 0)
        for item in candidates
    ):
        raise ValueError("候选成本必须为非负有限数")
    if budget is not None and any(item.cost is None for item in candidates):
        raise ValueError("启用预算约束必须提供所有候选点的已知成本")
    if method not in {"auto", "exact", "greedy"}:
        raise ValueError("不支持的优化方法")
    candidates = sorted(candidates, key=lambda item: item.id)
    all_costs_known = all(item.cost is not None for item in candidates)
    limit = min(max_facilities, len(candidates))
    combinations = sum(math.comb(len(candidates), count) for count in range(limit + 1))
    exact_available = combinations <= 100_000
    if method == "exact" and not exact_available:
        raise ValueError("精确枚举超过十万组合预算，请选择贪心或缩小候选集")
    exact = method == "exact" or (method == "auto" and exact_available)

    def union(items: Sequence[CoverageCandidate]) -> frozenset[str]:
        return frozenset(grid_id for item in items for grid_id in item.grid_ids)

    def objective(items: Sequence[CoverageCandidate]) -> tuple:
        return (
            -len(union(items)),
            sum(item.cost for item in items) if all_costs_known else 0,
            len(items),
            tuple(item.id for item in items),
        )

    selected: Sequence[CoverageCandidate] = ()
    if exact:
        for count in range(limit + 1):
            for subset in itertools.combinations(candidates, count):
                if budget is not None and sum(item.cost for item in subset) > budget:
                    continue
                if objective(subset) < objective(selected):
                    selected = subset
    else:
        pending = list(candidates)
        covered: frozenset[str] = frozenset()
        chosen: list[CoverageCandidate] = []
        spent = 0.0
        while pending and len(chosen) < limit:
            feasible = [item for item in pending if budget is None or spent + item.cost <= budget]
            if not feasible:
                break

            def rank(item: CoverageCandidate) -> tuple:
                gain = len(item.grid_ids - covered)
                efficiency = gain / (item.cost or 1e-12) if budget is not None else gain
                return (-efficiency, -gain, item.cost if all_costs_known else 0, item.id)

            next_item = min(feasible, key=rank)
            if not next_item.grid_ids - covered:
                break
            chosen.append(next_item)
            covered |= next_item.grid_ids
            spent += next_item.cost or 0
            pending.remove(next_item)
        selected = sorted(chosen, key=lambda item: item.id)
    covered = union(selected)
    known_costs = all(item.cost is not None for item in selected)
    return {
        "status": "OPTIMAL" if exact else "FEASIBLE",
        "method": "finite_enumeration" if exact else "deterministic_greedy",
        "selected_candidate_ids": [item.id for item in selected],
        "selected_count": len(selected),
        "covered_grid_ids": sorted(covered),
        "covered_grid_count": len(covered),
        "total_cost": sum(item.cost for item in selected) if known_costs else None,
        "constraints": {"max_facilities": max_facilities, "budget": budget},
        "candidate_count": len(candidates),
        "enumeration_combinations": combinations if exact else None,
        "objective": "maximum_distinct_confirmed_grid_coverage",
        "optimality_scope": "provided_finite_candidates_and_confirmed_coverage_sets",
        "disclosure": "仅优化输入候选及已确认网格覆盖；未计入人口、容量、土地合规或未知建设成本。",
    }


async def optimize_report_coverage(
    provider: MapProvider,
    report: dict[str, Any],
    *,
    candidate_ids: Sequence[str],
    max_facilities: int,
    budget: float | None = None,
    costs: dict[str, float] | None = None,
    method: Literal["auto", "exact", "greedy"] = "auto",
) -> dict[str, Any]:
    """从原报告有限候选出发，逐格到候选的新步行路线确认覆盖；不累加单点评分改善。"""
    if not candidate_ids or len(candidate_ids) > 32 or len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("必须选择 1 到 32 个不重复的报告候选点")
    candidates_by_id: dict[str, dict] = {}
    for recommendation in report.get("recommendations", []):
        for item in recommendation.get("candidate_locations", []):
            if item["id"] in candidates_by_id:
                raise ValueError("来源报告候选点标识重复，不能确定唯一候选证据")
            candidates_by_id[item["id"]] = item
    if any(item not in candidates_by_id for item in candidate_ids):
        raise ValueError("候选点不存在于来源报告")
    costs = costs or {}
    if any(key not in candidate_ids for key in costs):
        raise ValueError("成本不能引用本次选择范围之外的候选点")
    # 在外部路线调用之前完成数量、预算、成本与求解预算验证。
    optimize_maximum_coverage(
        [CoverageCandidate(key, frozenset(), costs.get(key)) for key in candidate_ids],
        max_facilities=max_facilities,
        budget=budget,
        method=method,
    )
    threshold = float(report["request"]["minutes"]) * 60
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("来源报告的步行阈值不是正有限数")
    destinations_by_id: dict[str, tuple[float, float]] = {}
    for candidate_id in candidate_ids:
        candidate = candidates_by_id[candidate_id]
        destination = (float(candidate["lng"]), float(candidate["lat"]))
        if not all(math.isfinite(value) for value in destination) or not (
            -180 <= destination[0] <= 180 and -90 <= destination[1] <= 90
        ):
            raise ValueError("来源报告候选点坐标无效")
        destinations_by_id[candidate_id] = destination
    grids = [
        feature
        for feature in (report.get("service_areas") or report.get("zones") or {}).get("features", [])
        if feature.get("properties", {}).get("kind") == "critical"
        and feature["properties"].get("classification_status") == "valid"
        and feature["properties"].get("failed_route_count", 0) == 0
    ]
    evidence: list[dict] = []
    measured_candidates: list[CoverageCandidate] = []
    route_pairs = 0
    unknown_pairs = 0
    for candidate_id in sorted(candidate_ids):
        candidate = candidates_by_id[candidate_id]
        targets = [grid for grid in grids if grid["properties"].get("category") == candidate["category"]]
        origins = [_cell_center(grid) for grid in targets]
        destination = destinations_by_id[candidate_id]
        route_pairs += len(origins)
        try:
            matrix = await provider.walking_matrix(origins, [destination]) if origins else []
        except MapProviderError:
            matrix = []
        covered: set[str] = set()
        unknown: list[str] = []
        sources: set[str] = set()
        for index, target in enumerate(targets):
            grid_id = target["properties"]["grid_id"]
            route = matrix[index][0] if index < len(matrix) and matrix[index] else None
            if not _usable_route(route, origins[index], destination):
                unknown.append(grid_id)
                continue
            sources.add(route.source)
            if route.duration_s <= threshold:
                covered.add(grid_id)
        unknown_pairs += len(unknown)
        measured_candidates.append(CoverageCandidate(candidate_id, frozenset(covered), costs.get(candidate_id)))
        evidence.append(
            {
                "candidate_id": candidate_id,
                "category": candidate["category"],
                "covered_grid_ids": sorted(covered),
                "unknown_grid_ids": unknown,
                "sources": sorted(sources),
                "method": "grid_center_to_hypothetical_facility_walking",
            }
        )
    result = optimize_maximum_coverage(measured_candidates, max_facilities=max_facilities, budget=budget, method=method)
    result.update(
        {
            "report_id": report["report_id"],
            "coordinate_system": "BD-09",
            "candidate_evidence": evidence,
            "route_pairs_used": route_pairs,
            "unknown_route_pairs": unknown_pairs,
            "coverage_evidence_status": "partial_lower_bound" if unknown_pairs else "complete_for_selected_grid_pairs",
            "hypothetical": True,
            "affects_original_report": False,
            "source_mode": provider.descriptor.mode,
            "disclosure": result["disclosure"]
            + " 覆盖指原重点盲区网格中心可达，不是连续面或人口覆盖。候选点未核验用地与建设可行性；组合不代表评分相加。",
        }
    )
    return result


def _usable_route(route: WalkingResult | None, origin: tuple[float, float], destination: tuple[float, float]) -> bool:
    if (
        route is None
        or route.success is not True
        or route.origin != origin
        or route.destination != destination
        or route.source not in {"real_api", "cache", "local_snapshot"}
        or route.underlying_source in {"interpolation", "degraded_estimate"}
    ):
        return False
    numbers = (route.distance_m, route.duration_s)
    if not all(
        isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
        for value in numbers
    ):
        return False
    distance, duration = numbers
    return (distance > 0 and duration > 0) or (origin == destination and distance == duration == 0)


def _cell_center(feature: dict) -> tuple[float, float]:
    points = feature["geometry"]["coordinates"][0]
    if points[0] == points[-1]:
        points = points[:-1]
    return (sum(point[0] for point in points) / len(points), sum(point[1] for point in points) / len(points))
