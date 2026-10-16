"""多社区独立、同预算采样评估；离线标签回放不能替代真实现场收益验证。"""

from __future__ import annotations

import math
import time
from typing import Any

from ..analysis.sampling import SamplingPoint, run_sampling_experiment
from ..maps.provider import WalkingResult

STRATEGIES = ("active", "radial", "uniform", "rule_densification", "idw")


def _communities(fixture):
    communities = fixture.get("communities")
    if not isinstance(communities, list) or len(communities) < 2:
        raise ValueError("跨社区评估至少需要两个独立社区")
    ids = [item.get("id") for item in communities]
    if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("社区ID必须唯一")
    for community in communities:
        points = community.get("points")
        if not isinstance(points, list) or not 3 <= len(points) <= 256:
            raise ValueError("每个社区至少3个且不超过256个测量点")
        point_ids = [item.get("id") for item in points]
        if any(not isinstance(value, str) or not value for value in point_ids) or len(set(point_ids)) != len(point_ids):
            raise ValueError("每个社区采样点ID必须唯一")
        coordinates = []
        for point in points:
            features = point.get("features_m")
            if (
                not isinstance(features, list)
                or len(features) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in features)
            ):
                raise ValueError("采样特征必须为两个有限米制偏移")
            coordinates.append(tuple(features))
            truth = point.get("duration_s")
            if isinstance(truth, bool) or not isinstance(truth, (int, float)) or not math.isfinite(truth) or truth <= 0:
                raise ValueError("评估标签必须为独立实测的正有限原始秒数")
            if point.get("source") not in {"real_api", "local_snapshot"}:
                raise ValueError("估算或无来源标签不能进入独立评估")
            if point.get("source") == "real_api" and (not point.get("measured_at") or not point.get("measurement_ref")):
                raise ValueError("真实标签需要采集时间和原始测量证据引用")
        if len(set(coordinates)) != len(coordinates):
            raise ValueError("同社区重复坐标须先去重，冲突标签不得进入评估")
    return communities


def _boundary_metrics(points, prediction_by_id, validation_ids, threshold):
    # 边界由留出点的四个最近邻中阈值跨越边中点表示；不宣称连续等时圈的Hausdorff距离。
    positions = {point["id"]: tuple(point["features_m"]) for point in points if point["id"] in validation_ids}
    truth = {point["id"]: point["duration_s"] / 60 for point in points}
    edges = set()
    for key, position in positions.items():
        neighbors = sorted(
            (other for other in positions if other != key),
            key=lambda other: (sum((a - b) ** 2 for a, b in zip(position, positions[other])), other),
        )[:4]
        edges.update(tuple(sorted((key, other))) for other in neighbors)
    observed, estimated = [], []
    unknown_edges = 0
    for first, second in sorted(edges):
        midpoint = tuple((a + b) / 2 for a, b in zip(positions[first], positions[second]))
        if (truth[first] <= threshold) != (truth[second] <= threshold):
            observed.append(midpoint)
        values = [prediction_by_id[key]["mean_minutes"] for key in (first, second)]
        if None in values:
            unknown_edges += 1
        elif (values[0] <= threshold) != (values[1] <= threshold):
            estimated.append(midpoint)
    if not observed or not estimated:
        distance = None
    else:
        distance = max(
            max(min(math.dist(a, b) for b in estimated) for a in observed),
            max(min(math.dist(b, a) for a in observed) for b in estimated),
        )
    return {
        "method": "heldout_nearest_neighbor_threshold_crossing_midpoints",
        "boundary_location_error_m": distance,
        "observed_crossing_count": len(observed),
        "estimated_crossing_count": len(estimated),
        "unknown_edge_count": unknown_edges,
        "disclosure": "仅为留出点邻接边阈值跨越位置误差，不是连续区域边界或现场通行认证；无跨越时误差保持未知。",
    }


async def evaluate_spatial_sampling(
    fixture: dict[str, Any],
    *,
    budgets=(12, 20, 32),
    threshold_minutes=15,
    target_mae_minutes=2.0,
    max_false_reachable_rate=0.05,
) -> dict:
    communities = _communities(fixture)
    if not budgets or any(
        isinstance(value, bool) or not isinstance(value, int) or not 2 <= value <= 200 for value in budgets
    ):
        raise ValueError("对照预算必须在2到200路线对内")
    if (
        any(not math.isfinite(v) or v < 0 for v in (target_mae_minutes, max_false_reachable_rate))
        or not 0 <= max_false_reachable_rate <= 1
    ):
        raise ValueError("误差门槛必须有限且假可达率在0到1内")
    calibration_ids = set(fixture.get("calibration_community_ids", []))
    if not calibration_ids <= {item["id"] for item in communities}:
        raise ValueError("校准社区不在数据集内")
    evaluation_communities = [item for item in communities if item["id"] not in calibration_ids]
    if len(evaluation_communities) < 2:
        raise ValueError("独立评估必须保留至少两个非校准社区")
    results = []
    for community in evaluation_communities:
        records = {point["id"]: point for point in community["points"]}
        points = [
            SamplingPoint(key, tuple(value["features_m"]), bool(value.get("high_risk", False)))
            for key, value in sorted(records.items())
        ]
        blocks = {}
        for point in points:
            blocks.setdefault(tuple(math.floor(value / 500) for value in point.features), []).append(point.id)
        eligible = [(key, values) for key, values in blocks.items() if len(values) < min(budgets)]
        if len(blocks) < 2 or not eligible:
            raise ValueError(f"社区{community['id']}无法按最小预算保留独立空间块")
        heldout_block, heldout = max(eligible, key=lambda item: (sum(value * value for value in item[0]), item[0]))
        for budget in sorted(set(budgets)):
            for strategy in STRATEGIES:
                calls = []

                async def measure(point):
                    calls.append(point.id)
                    record = records[point.id]
                    # 构造坐标用于路线有效性；标签保留原秒数，绝不重新计算真值。
                    destination = (113 + point.features[0] / 111_320, 23 + point.features[1] / 111_320)
                    return WalkingResult(
                        (113, 23),
                        destination,
                        True,
                        record.get("distance_m", 100),
                        record["duration_s"],
                        record["source"],
                        "independent_label_replay",
                    )

                start = time.perf_counter()
                result = await run_sampling_experiment(
                    points,
                    measure,
                    route_pair_budget=budget,
                    threshold_minutes=threshold_minutes,
                    validation_ids=heldout,
                    strategy=strategy,
                )
                runtime_ms = (time.perf_counter() - start) * 1000
                evaluated = result["evaluation"]["evaluated_count"]
                false_rate = result["evaluation"]["false_reachable_count"] / evaluated if evaluated else None
                predictions = {item["point_id"]: item for item in result["predictions"]}
                meets = (
                    result["evaluation"]["mae_minutes"] is not None
                    and result["evaluation"]["mae_minutes"] <= target_mae_minutes
                    and false_rate <= max_false_reachable_rate
                )
                latencies = [records[key].get("measured_latency_ms") for key in calls]
                results.append(
                    {
                        "community_id": community["id"],
                        "strategy": strategy,
                        "budget": budget,
                        "training_ids": result["training_ids"],
                        "validation_ids": heldout,
                        "heldout_spatial_block": list(heldout_block),
                        "route_pairs_replayed": len(calls),
                        "external_route_pairs_used": 0,
                        "offline_runtime_ms": runtime_ms,
                        "recorded_latency_sum_ms": sum(latencies)
                        if all(
                            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0
                            for v in latencies
                        )
                        else None,
                        "evaluation": result["evaluation"],
                        "false_reachable_rate": false_rate,
                        "unresolved_ratio": sum(item["status"] == "unresolved" for item in result["predictions"])
                        / len(points),
                        "boundary": _boundary_metrics(community["points"], predictions, heldout, threshold_minutes),
                        "meets_error_target": meets,
                    }
                )
    equal_error = []
    for community in evaluation_communities:
        achieved = {
            strategy: min(
                (
                    item["route_pairs_replayed"]
                    for item in results
                    if item["community_id"] == community["id"]
                    and item["strategy"] == strategy
                    and item["meets_error_target"]
                ),
                default=None,
            )
            for strategy in STRATEGIES
        }
        equal_error.append(
            {
                "community_id": community["id"],
                "minimum_replayed_pairs_at_target": achieved,
                "active_savings_vs_uniform": achieved["uniform"] - achieved["active"]
                if achieved["uniform"] is not None and achieved["active"] is not None
                else None,
            }
        )
    is_snapshot = any(
        point["source"] == "local_snapshot" for community in evaluation_communities for point in community["points"]
    )
    return {
        "schema_version": "spatial-evaluation-v1",
        "status": "offline_snapshot_replay" if is_snapshot else "offline_real_label_replay",
        "community_ids": [item["id"] for item in evaluation_communities],
        "calibration_community_ids": sorted(calibration_ids),
        "cross_community_policy": "independent_local_models_no_label_or_hyperparameter_pooling",
        "strategies": list(STRATEGIES),
        "budgets": sorted(set(budgets)),
        "results": results,
        "same_error_comparison": equal_error,
        "enabled_for_official_analysis": False,
        "source_manifest": fixture.get("manifest", {}),
        "error_target": {"mae_minutes": target_mae_minutes, "max_false_reachable_rate": max_false_reachable_rate},
        "disclosure": "使用独立社区原始标签离线回放，同预算独立选点且空间块留出。校准社区与评估社区隔离；不代表真实API耗时、实际配额节约或现场边界精度。默认规则评分未使用预测。",
    }
