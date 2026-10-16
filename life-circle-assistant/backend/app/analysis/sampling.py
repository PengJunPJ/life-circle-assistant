"""可注入回归器的主动采样实验。预测仅用于选择下一次测量，不进入正式评分。"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ..maps.provider import MapProviderError, WalkingResult


@dataclass(frozen=True)
class SamplingPoint:
    id: str
    features: tuple[float, ...]
    high_risk: bool = False


@dataclass(frozen=True)
class Prediction:
    mean_minutes: float
    std_minutes: float


class TravelTimeRegressor(Protocol):
    def fit(self, samples: Sequence[tuple[tuple[float, ...], float]]) -> None: ...
    def predict(self, features: tuple[float, ...]) -> Prediction: ...


class GaussianKernelRegressor:
    """小样本精确高斯过程，Cholesky 求解；输入为米尺度特征，输出为分钟。

    后验标准差依赖指定核与噪声假设，未经现场校准，不是准确率保证。
    """

    def __init__(self, *, length_scale: float = 500, prior_std: float = 8, noise_std: float = 1) -> None:
        if any(not math.isfinite(value) or value <= 0 for value in (length_scale, prior_std, noise_std)):
            raise ValueError("核尺度与标准差必须为正有限数")
        self.length_scale, self.prior_std, self.noise_std = length_scale, prior_std, noise_std
        self.samples: list[tuple[tuple[float, ...], float]] = []

    def _kernel(self, first: tuple[float, ...], second: tuple[float, ...]) -> float:
        return self.prior_std**2 * math.exp(
            -sum((a - b) ** 2 for a, b in zip(first, second)) / (2 * self.length_scale**2)
        )

    def fit(self, samples: Sequence[tuple[tuple[float, ...], float]]) -> None:
        if not samples or len(samples) > 200:
            raise ValueError("回归训练必须含 1 到 200 个样本")
        dimensions = len(samples[0][0])
        if dimensions == 0 or any(
            len(features) != dimensions
            or not all(math.isfinite(v) for v in features)
            or not math.isfinite(value)
            or value < 0
            for features, value in samples
        ):
            raise ValueError("训练特征必须同维且有限，步行分钟必须非负有限")
        self.samples = list(samples)
        self.mean = sum(value for _, value in samples) / len(samples)
        self.lower = [[0.0] * len(samples) for _ in samples]
        for row, (features, _) in enumerate(samples):
            for column in range(row + 1):
                value = self._kernel(features, samples[column][0])
                if row == column:
                    value += self.noise_std**2
                value -= sum(self.lower[row][k] * self.lower[column][k] for k in range(column))
                self.lower[row][column] = (
                    math.sqrt(max(value, 1e-12)) if row == column else value / self.lower[column][column]
                )
        residuals = [value - self.mean for _, value in samples]
        solved = _forward(self.lower, residuals)
        self.alpha = [0.0] * len(samples)
        for row in reversed(range(len(samples))):
            self.alpha[row] = (
                solved[row] - sum(self.lower[k][row] * self.alpha[k] for k in range(row + 1, len(samples)))
            ) / self.lower[row][row]

    def predict(self, features: tuple[float, ...]) -> Prediction:
        if not self.samples:
            raise ValueError("回归器尚未训练")
        if len(features) != len(self.samples[0][0]) or not all(math.isfinite(v) for v in features):
            raise ValueError("预测特征维度不匹配或含无效数值")
        kernel = [self._kernel(features, sample) for sample, _ in self.samples]
        mean = max(0.0, self.mean + sum(k * a for k, a in zip(kernel, self.alpha)))
        projected = _forward(self.lower, kernel)
        variance = max(0.0, self.prior_std**2 - sum(value**2 for value in projected)) + self.noise_std**2
        return Prediction(mean, math.sqrt(variance))


def _forward(lower: list[list[float]], values: list[float]) -> list[float]:
    result: list[float] = []
    for row, value in enumerate(values):
        result.append((value - sum(lower[row][k] * result[k] for k in range(row))) / lower[row][row])
    return result


def select_active_samples(
    points: Sequence[SamplingPoint], regressor: TravelTimeRegressor, *, threshold_minutes: float, limit: int
) -> list[str]:
    if not math.isfinite(threshold_minutes) or threshold_minutes <= 0 or limit < 0:
        raise ValueError("阈值必须为正有限数，采样数量不得为负")
    ranked: list[tuple[tuple, str]] = []
    for point in points:
        prediction = regressor.predict(point.features)
        _validate_prediction(prediction)
        distance = abs(prediction.mean_minutes - threshold_minutes)
        crosses = distance <= 1.96 * prediction.std_minutes
        ranked.append(
            ((not point.high_risk, not crosses, -(prediction.std_minutes / (1 + distance)), point.id), point.id)
        )
    return [point_id for _, point_id in sorted(ranked)[:limit]]


def _validate_prediction(prediction: Prediction) -> None:
    if any(not math.isfinite(value) or value < 0 for value in (prediction.mean_minutes, prediction.std_minutes)):
        raise ValueError("回归器返回无效预测")


def _label_source_rejection(source: str | None, underlying_source: str | None) -> str | None:
    if source not in ("real_api", "cache", "local_snapshot"):
        return "unsupported_route_source"
    if underlying_source in ("interpolation", "degraded_estimate"):
        return "estimated_underlying_source"
    if source == "cache" and underlying_source not in ("real_api", "local_snapshot"):
        return "unverified_cache_origin"
    if underlying_source is not None and underlying_source not in ("real_api", "local_snapshot"):
        return "unverified_underlying_source"
    return None


def _route_label_rejection(route: WalkingResult) -> str | None:
    if route.success is not True:
        return "failed_route"
    source_rejection = _label_source_rejection(route.source, route.underlying_source)
    if source_rejection:
        return source_rejection
    if not all(
        isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
        for value in (route.distance_m, route.duration_s)
    ):
        return "invalid_route_measurement"
    if not all(
        len(coordinate) == 2
        and all(
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            for value in coordinate
        )
        for coordinate in (route.origin, route.destination)
    ):
        return "invalid_route_coordinates"
    if (route.distance_m > 0 and route.duration_s > 0) or (
        route.origin == route.destination and route.distance_m == route.duration_s == 0
    ):
        return None
    return "unproven_zero_route"


async def run_sampling_experiment(
    points: Sequence[SamplingPoint],
    measure: Callable[[SamplingPoint], Awaitable[WalkingResult]],
    *,
    threshold_minutes: float = 15,
    route_pair_budget: int = 20,
    validation_ids: Sequence[str] = (),
    regressor: TravelTimeRegressor | None = None,
    strategy: str = "active",
) -> dict:
    """预算包含训练与独立留出验证路线对；验证点永不进入训练，失败点保留未知。

    调用方负责地图授权和坐标到特征的映射。该函数不会自行创建真实地图客户端。
    """
    by_id = {point.id: point for point in points}
    if strategy not in {"active", "uniform", "radial", "rule_densification", "idw"}:
        raise ValueError("采样策略不支持")
    if not 2 <= len(points) <= 256 or len(by_id) != len(points):
        raise ValueError("实验需要 2 到 256 个不重复采样点")
    if (
        isinstance(route_pair_budget, bool)
        or not isinstance(route_pair_budget, int)
        or not 2 <= route_pair_budget <= 200
    ):
        raise ValueError("实验路线对预算必须为 2 到 200")
    if not math.isfinite(threshold_minutes) or threshold_minutes <= 0:
        raise ValueError("步行阈值必须为正有限数")
    dimensions = len(points[0].features)
    if dimensions == 0 or any(
        len(p.features) != dimensions or not all(math.isfinite(v) for v in p.features) for p in points
    ):
        raise ValueError("采样特征维度必须一致且为有限数")
    heldout = list(validation_ids) if validation_ids else [sorted(by_id)[-1]]
    if len(set(heldout)) != len(heldout) or any(point_id not in by_id for point_id in heldout):
        raise ValueError("留出验证点必须存在且不重复")
    if len(heldout) >= min(route_pair_budget, len(points)):
        raise ValueError("留出验证点必须给训练保留至少一个路线对预算")
    remaining = {key: point for key, point in by_id.items() if key not in heldout}
    train_budget = min(route_pair_budget - len(heldout), len(remaining))
    model = regressor or GaussianKernelRegressor()
    samples: list[tuple[tuple[float, ...], float]] = []
    observations: list[dict] = []
    training_ids: list[str] = []

    async def observe(point: SamplingPoint, phase: str) -> float | None:
        try:
            route = await measure(point)
        except MapProviderError as exc:
            observations.append(
                {
                    "point_id": point.id,
                    "phase": phase,
                    "minutes": None,
                    "source": None,
                    "underlying_source": None,
                    "method": None,
                    "status": "unknown",
                    "error_code": exc.code,
                }
            )
            return None
        rejection = _route_label_rejection(route)
        minutes = route.duration_s / 60 if rejection is None else None
        observations.append(
            {
                "point_id": point.id,
                "phase": phase,
                "minutes": minutes,
                "duration_s": route.duration_s if rejection is None else None,
                "distance_m": route.distance_m if rejection is None else None,
                "origin": list(route.origin),
                "destination": list(route.destination),
                "source": route.source,
                "underlying_source": route.underlying_source,
                "method": route.method,
                "status": "measured" if minutes is not None else "unknown",
                "exclusion_reason": rejection,
            }
        )
        return minutes

    for _ in range(train_budget):
        point_id = (
            select_active_samples(list(remaining.values()), model, threshold_minutes=threshold_minutes, limit=1)[0]
            if samples and strategy == "active"
            else _select_baseline_point(remaining, training_ids, by_id, observations, strategy, threshold_minutes)
        )
        point = remaining.pop(point_id)
        minutes = await observe(point, "training")
        training_ids.append(point_id)
        if minutes is not None:
            samples.append((point.features, minutes))
            model.fit(samples)
    predictions: list[dict] = []
    for point in sorted(points, key=lambda p: p.id):
        prediction = (
            _idw_prediction(point.features, samples)
            if samples and strategy == "idw"
            else model.predict(point.features)
            if samples
            else None
        )
        if prediction is not None:
            _validate_prediction(prediction)
        unresolved = (
            prediction is None or abs(prediction.mean_minutes - threshold_minutes) <= 1.96 * prediction.std_minutes
        )
        predictions.append(
            {
                "point_id": point.id,
                "mean_minutes": prediction.mean_minutes if prediction else None,
                "std_minutes": prediction.std_minutes if prediction else None,
                "status": "unresolved" if unresolved else "prediction_only",
                "requires_measurement": True,
                "source": "interpolation",
                "affects_official_score": False,
            }
        )
    prediction_by_id = {item["point_id"]: item for item in predictions}
    evaluation = {
        "evaluated_count": 0,
        "unknown_measurements": 0,
        "false_reachable_count": 0,
        "false_unreachable_count": 0,
        "unresolved_count": 0,
        "mae_minutes": None,
    }
    baseline = {
        "method": "inverse_distance_weighting",
        "mae_minutes": None,
        "false_reachable_count": 0,
        "false_unreachable_count": 0,
    }
    errors: list[float] = []
    baseline_errors: list[float] = []
    for point_id in heldout:
        truth = await observe(by_id[point_id], "validation")
        prediction = prediction_by_id[point_id]
        evaluation["unresolved_count"] += prediction["status"] == "unresolved"
        if truth is None or prediction["mean_minutes"] is None:
            evaluation["unknown_measurements"] += 1
            continue
        estimated = prediction["mean_minutes"]
        evaluation["evaluated_count"] += 1
        errors.append(abs(estimated - truth))
        evaluation["false_reachable_count"] += estimated <= threshold_minutes < truth
        evaluation["false_unreachable_count"] += truth <= threshold_minutes < estimated
        weights = [
            1 / max(1e-6, sum((a - b) ** 2 for a, b in zip(by_id[point_id].features, features)))
            for features, _ in samples
        ]
        baseline_value = sum(weight * value for weight, (_, value) in zip(weights, samples)) / sum(weights)
        baseline_errors.append(abs(baseline_value - truth))
        baseline["false_reachable_count"] += baseline_value <= threshold_minutes < truth
        baseline["false_unreachable_count"] += truth <= threshold_minutes < baseline_value
    evaluation["mae_minutes"] = sum(errors) / len(errors) if errors else None
    baseline["mae_minutes"] = sum(baseline_errors) / len(baseline_errors) if baseline_errors else None
    return {
        "status": "experimental",
        "strategy": strategy,
        "enabled_for_official_analysis": False,
        "threshold_minutes": threshold_minutes,
        "training_ids": training_ids,
        "validation_ids": heldout,
        "route_pair_budget": route_pair_budget,
        "route_pairs_used": len(observations),
        "route_pairs_remaining": route_pair_budget - len(observations),
        "observations": observations,
        "predictions": predictions,
        "evaluation": evaluation,
        "baseline": baseline,
        "validation_scope": "explicit_point_ids_without_spatial_independence_guarantee",
        "baseline_scope": "same_training_samples_interpolation_comparison_only",
        "disclosure": "留出集未参与训练；不确定性未经现场校准。预测不得作为可达性、盲区或评分事实；未证明优于基线或节省配额。",
    }


def _idw_prediction(features, samples):
    exact = [value for position, value in samples if position == features]
    if exact:
        return Prediction(exact[0], 0)
    weights = [1 / max(1e-6, sum((a - b) ** 2 for a, b in zip(features, position))) for position, _ in samples]
    mean = sum(weight * value for weight, (_, value) in zip(weights, samples)) / sum(weights)
    variance = sum(weight * (value - mean) ** 2 for weight, (_, value) in zip(weights, samples)) / sum(weights)
    return Prediction(mean, math.sqrt(variance))


def _select_baseline_point(remaining, selected, by_id, observations, strategy, threshold):
    if not selected:
        return min(remaining, key=lambda key: (not remaining[key].high_risk if strategy == "active" else False, key))
    if strategy == "radial":
        # 独立径向策略优先补齐16个扇区；与主动样本选择无关。
        def sector(point):
            return int((math.atan2(point.features[1], point.features[0]) + math.pi) / (2 * math.pi) * 16) % 16

        counts = {value: sum(sector(by_id[key]) == value for key in selected) for value in range(16)}
        return min(
            remaining,
            key=lambda key: (counts[sector(remaining[key])], -sum(v * v for v in remaining[key].features[:2]), key),
        )
    if strategy == "rule_densification":
        near = [
            item["point_id"]
            for item in observations
            if item.get("minutes") is not None and abs(item["minutes"] - threshold) <= 3
        ]
        if near:
            return min(
                remaining,
                key=lambda key: (
                    min(
                        sum((a - b) ** 2 for a, b in zip(remaining[key].features, by_id[observed].features))
                        for observed in near
                    ),
                    key,
                ),
            )
    # 均匀空间覆盖：最远点迭代；IDW采用同样独立均匀样本。
    return min(
        remaining,
        key=lambda key: (
            -min(
                sum((a - b) ** 2 for a, b in zip(remaining[key].features, by_id[observed].features))
                for observed in selected
            ),
            key,
        ),
    )


async def evaluate_report_sampling(report: dict[str, Any], *, route_pair_budget: int = 20) -> dict:
    """只复用报告内路线做离线留出实验，不访问地图，不训练跨城市模型。"""
    center = report["analysis_center"]
    origin = (float(center["lng"]), float(center["lat"]))
    facilities = report.get("facilities") or report.get("pois") or []
    points: list[SamplingPoint] = []
    routes: dict[str, WalkingResult] = {}
    aliases: dict[str, list[str]] = {}
    sample_sources: dict[str, list[dict[str, Any]]] = {}
    spatial_blocks: dict[tuple[int, int], list[str]] = {}
    destination_groups: dict[tuple[float, float], list[tuple[dict[str, Any], WalkingResult]]] = {}
    exclusions: list[dict[str, Any]] = []
    conflicting_groups: list[dict[str, Any]] = []
    usable_records = 0
    for facility in facilities:
        minutes = facility.get("walk_minutes")
        # 源设施没有路线时不凭空造训练标签；快照样本也保留其来源。
        source = facility.get("source") or facility.get("walking_source")
        point_id = str(facility.get("id", ""))
        source_rejection = _label_source_rejection(source, facility.get("underlying_source"))
        if source_rejection:
            exclusions.append({"facility_id": point_id, "reason": source_rejection})
            continue
        if (
            isinstance(minutes, bool)
            or not isinstance(minutes, (int, float))
            or not math.isfinite(minutes)
            or minutes < 0
        ):
            exclusions.append({"facility_id": point_id, "reason": "invalid_report_minutes"})
            continue
        try:
            destination = (float(facility["lng"]), float(facility["lat"]))
        except (KeyError, TypeError, ValueError):
            exclusions.append({"facility_id": point_id, "reason": "invalid_route_coordinates"})
            continue
        route = WalkingResult(
            origin,
            destination,
            True,
            facility.get("walk_distance_m"),
            float(minutes) * 60,
            source,
            facility.get("calculation_method") or "report_recorded_route",
            underlying_source=facility.get("underlying_source"),
        )
        rejection = _route_label_rejection(route)
        if rejection:
            exclusions.append({"facility_id": point_id, "reason": rejection})
            continue
        usable_records += 1
        destination_key = (round(destination[0], 7), round(destination[1], 7))
        destination_groups.setdefault(destination_key, []).append((facility, route))
    deduplicated_records = 0
    conflicting_records = 0
    for destination_key, records in destination_groups.items():
        labels = sorted({float(facility["walk_minutes"]) for facility, _ in records})
        if len(labels) > 1:
            conflicting_records += len(records)
            ids = [str(facility["id"]) for facility, _ in records]
            conflicting_groups.append(
                {
                    "destination": {"lng": destination_key[0], "lat": destination_key[1]},
                    "facility_ids": ids,
                    "labels_minutes": labels,
                    "reason": "conflicting_report_minutes_same_destination",
                }
            )
            exclusions.extend(
                {"facility_id": point_id, "reason": "conflicting_report_minutes_same_destination"} for point_id in ids
            )
            continue
        facility, route = records[0]
        point_id = str(facility["id"])
        aliases[point_id] = [str(record["id"]) for record, _ in records]
        sample_sources[point_id] = [
            {"facility_id": str(record["id"]), "source": item.source, "underlying_source": item.underlying_source}
            for record, item in records
        ]
        deduplicated_records += len(records) - 1
        features = (
            (route.destination[0] - origin[0]) * 111_320 * math.cos(math.radians(origin[1])),
            (route.destination[1] - origin[1]) * 111_320,
        )
        points.append(SamplingPoint(point_id, features))
        spatial_blocks.setdefault((math.floor(features[0] / 500), math.floor(features[1] / 500)), []).append(point_id)
        routes[point_id] = route
    scope = {
        "sample_count": len(points),
        "usable_record_count": usable_records,
        "deduplicated_record_count": deduplicated_records,
        "conflicting_record_count": conflicting_records,
        "conflicting_sample_groups": conflicting_groups,
        "excluded_record_count": len(exclusions),
        "sample_exclusions": exclusions,
        "sample_aliases": aliases,
        "sample_sources": sample_sources,
        "source_modes": sorted({item["source"] for items in sample_sources.values() for item in items}),
        "label_precision_minutes": 0.1,
        "label_origin": "report_rounded_walk_minutes",
        "raw_duration_seconds_available": False,
        "spatial_block_size_m": 500,
        "spatial_block_count": len(spatial_blocks),
        "external_route_pairs_used": 0,
        "enabled_for_official_analysis": False,
    }
    label_disclosure = (
        "复用报告已舍入至0.1分钟的路线标签，无法恢复原始秒级测量；同坐标分钟标签冲突整组排除，"
        "缓存仅接纳可核验为地图接口或快照的基础来源，快照不代表当前实测。"
    )
    if len(points) < 3 or len(spatial_blocks) < 2:
        return {
            "status": "insufficient_recorded_samples",
            "report_id": report["report_id"],
            **scope,
            "disclosure": "去重后的路线样本不足三个，或仅分布在一个空间块，无法进行空间留出实验；未调用地图或生成预测。"
            + label_disclosure,
        }
    eligible_blocks = [(key, ids) for key, ids in spatial_blocks.items() if len(ids) < route_pair_budget]
    if not eligible_blocks or len(points) > 256:
        return {
            "status": "insufficient_evaluation_budget",
            "report_id": report["report_id"],
            **scope,
            "disclosure": "当前预算无法把同一空间块全部留出并保留训练样本，或超过256点实验规模；未调用地图或生成预测。"
            + label_disclosure,
        }
    heldout_block, heldout_ids = max(eligible_blocks, key=lambda item: (sum(value**2 for value in item[0]), item[0]))

    async def measure(point: SamplingPoint) -> WalkingResult:
        return routes[point.id]

    result = await run_sampling_experiment(
        points,
        measure,
        threshold_minutes=float(report["request"]["minutes"]),
        route_pair_budget=route_pair_budget,
        validation_ids=heldout_ids,
    )
    result.update(
        {
            "report_id": report["report_id"],
            **scope,
            "validation_scope": "entire_500m_spatial_block_excluded_from_training",
            "heldout_spatial_block": list(heldout_block),
            "evaluation_strength": "exploratory_single_spatial_block",
            "data_scope": "recorded_report_center_to_facility_routes",
            "disclosure": result["disclosure"]
            + " 仅对已有设施路线样本评估，不能外推等时圈边界或路网障碍效果。"
            + label_disclosure,
        }
    )
    return result
