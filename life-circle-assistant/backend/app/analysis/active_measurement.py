"""真实路线主动补测与独立预测地图，不改写来源报告和正式评分。"""

from __future__ import annotations

import copy
import math
from typing import Any

from ..execution_budget import BudgetMapProvider
from ..maps.provider import MapProviderError
from .sampling import SamplingPoint, run_sampling_experiment
from .service_areas import _build_grid


def sampling_grid(center, grid_size=9, span_m=1250):
    cells = _build_grid(center, grid_size, span_m)
    by_id = {cell["id"]: cell for cell in cells}
    points = [
        SamplingPoint(
            cell["id"],
            (
                (cell["center"][0] - center[0]) * 111_320 * math.cos(math.radians(center[1])),
                (cell["center"][1] - center[1]) * 111_320,
            ),
        )
        for cell in cells
    ]
    return points, by_id


async def run_active_measurement(
    provider,
    report: dict[str, Any],
    *,
    route_pair_budget: int = 20,
    grid_size: int = 9,
    high_risk_grid_ids: list[str] | None = None,
    strategy: str = "active",
    adjacency_evidence: list[dict] | None = None,
) -> dict:
    if isinstance(grid_size, bool) or not isinstance(grid_size, int) or not 3 <= grid_size <= 15:
        raise ValueError("主动测量网格边长必须为3到15")
    center_data = report["analysis_center"]
    center = (float(center_data["lng"]), float(center_data["lat"]))
    points, cells = sampling_grid(center, grid_size)
    explicit_risk = set(high_risk_grid_ids or [])
    if not explicit_risk <= set(cells):
        raise ValueError("高风险网格不属于本次采样网格")
    # 已核验4×4障碍两端转成实际空间点，再标记最近的补测网格；不把未经审核的留言当障碍。
    risk_evidence = [
        item
        for item in adjacency_evidence or []
        if item.get("verified") is True
        and item.get("blocked") is True
        and item.get("reviewer")
        and item.get("evidence_ref")
        and item.get("source") in {"field_verification", "official_inventory", "resident_reviewed", "real_api"}
    ]
    formal_cells = {cell["id"]: cell for cell in _build_grid(center, 4, 1000)}
    trusted_risk = set()
    for evidence in risk_evidence:
        for key in ("first_grid_id", "second_grid_id"):
            grid_id = str(evidence[key]).split("-")[-1]
            if grid_id in formal_cells:
                origin = formal_cells[grid_id]["center"]
                trusted_risk.add(
                    min(
                        cells,
                        key=lambda candidate: sum((a - b) ** 2 for a, b in zip(cells[candidate]["center"], origin)),
                    )
                )
    points = [SamplingPoint(point.id, point.features, point.id in explicit_risk | trusted_risk) for point in points]
    blocks: dict[tuple[int, int], list[str]] = {}
    for point in points:
        blocks.setdefault((math.floor(point.features[0] / 500), math.floor(point.features[1] / 500)), []).append(
            point.id
        )
    eligible = [(key, ids) for key, ids in blocks.items() if len(ids) < route_pair_budget]
    if not eligible:
        raise ValueError("预算不足以留出完整空间块并训练；请提高预算或降低网格密度")
    heldout_block, heldout = max(eligible, key=lambda item: (sum(value * value for value in item[0]), item[0]))
    # 局部预算必须独立于上层更大的可用配额；外层包装将每次重试限制在本轮补测预算内。
    bounded = BudgetMapProvider(provider, route_pair_budget)
    before = bounded.used
    physical_before = bounded.physical_route_pairs_used

    async def measure(point):
        rows = await bounded.walking_matrix([center], [cells[point.id]["center"]])
        if len(rows) != 1 or len(rows[0]) != 1:
            raise MapProviderError("主动采样路线矩阵维度不匹配", code="sampling_route_shape")
        result = rows[0][0]
        if result.origin != center or result.destination != cells[point.id]["center"]:
            raise MapProviderError("主动采样返回坐标与请求不一致", code="sampling_route_coordinates")
        return result

    result = await run_sampling_experiment(
        points,
        measure,
        threshold_minutes=report["request"]["minutes"],
        route_pair_budget=route_pair_budget,
        validation_ids=heldout,
        strategy=strategy,
    )
    result.update(
        {
            "report_id": report["report_id"],
            "coordinate_system": "BD-09",
            "data_scope": "budgeted_center_to_sampling_grid_routes",
            "raw_duration_seconds_available": any(
                item.get("duration_s") is not None for item in result["observations"]
            ),
            "label_origin": "provider_raw_duration_seconds",
            "label_precision_minutes": None,
            "spatial_block_size_m": 500,
            "heldout_spatial_block": list(heldout_block),
            "validation_scope": "entire_500m_spatial_block_excluded_from_training",
            "evaluation_strength": "exploratory_live_spatial_holdout_not_cross_community_validation",
            "source_modes": sorted({item["source"] for item in result["observations"] if item.get("source")}),
            "risk_grid_ids": sorted(explicit_risk | trusted_risk),
            "risk_evidence": copy.deepcopy(risk_evidence),
            "external_route_pairs_used": bounded.physical_route_pairs_used - physical_before,
            "execution_budget": {
                "max_route_pairs": route_pair_budget,
                "route_pairs_requested": bounded.used - before,
                "physical_route_pairs_used": bounded.physical_route_pairs_used - physical_before,
            },
            "layers": sampling_layers(result, cells),
        }
    )
    result["disclosure"] += (
        " 已启用提供方路线补测，失败与估算不作为训练标签；地图仅观测网格中心，预测区及观测格外沿均非整个网格可达性认证。"
    )
    return result


def sampling_layers(result, cells):
    threshold = result["threshold_minutes"]
    observations = {item["point_id"]: item for item in result["observations"]}
    layers = {
        key: {"type": "FeatureCollection", "features": []}
        for key in (
            "observed",
            "observed_boundary",
            "estimated",
            "unresolved",
            "time_field",
        )
    }
    for prediction in result["predictions"]:
        point_id = prediction["point_id"]
        cell = cells[point_id]
        observation = observations.get(point_id)
        measured = observation is not None and observation.get("minutes") is not None
        props = {
            **prediction,
            "coordinate_system": "BD-09",
            "threshold_minutes": threshold,
            "source": "interpolation",
            "evidence_scope": "prediction_only",
            "duration_s": None,
            "measured_minutes": None,
        }
        if measured:
            props.update(
                measured_minutes=observation["minutes"],
                duration_s=observation["duration_s"],
                source=observation["source"],
                underlying_source=observation["underlying_source"],
                method=observation["method"],
                evidence_scope="center_point_only",
                status="measured",
            )
            layers["observed"]["features"].append(
                {
                    "type": "Feature",
                    "properties": copy.deepcopy(props),
                    "geometry": {"type": "Point", "coordinates": list(cell["center"])},
                }
            )
        polygon = {
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Polygon", "coordinates": [copy.deepcopy(cell["coordinates"])]},
        }
        layers["time_field"]["features"].append(copy.deepcopy(polygon))
        if measured and observation["minutes"] <= threshold:
            layers["observed_boundary"]["features"].append(copy.deepcopy(polygon))
        elif not measured and prediction["status"] == "unresolved":
            layers["unresolved"]["features"].append(copy.deepcopy(polygon))
        elif not measured and prediction["mean_minutes"] is not None and prediction["mean_minutes"] <= threshold:
            layers["estimated"]["features"].append(copy.deepcopy(polygon))
    for layer in layers.values():
        layer["coordinate_system"] = "BD-09"
        layer["affects_official_score"] = False
    return layers
