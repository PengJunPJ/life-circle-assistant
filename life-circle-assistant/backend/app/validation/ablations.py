"""Five explicit arms against isolated community labels and measured workloads.

The fixture runner executes application components, but its analytic route oracle
and scripted model are synthetic. It makes no claim about live model accuracy.
"""

from __future__ import annotations

import math
import time

from ..analysis.sampling import SamplingPoint, run_sampling_experiment
from ..analysis.semantic_review import review_facility_semantics
from ..analysis_intent import parse_analysis_intent
from ..maps.provider import WalkingResult
from ..mock_data import CATEGORIES
from ..planning_portfolio import PortfolioConstraints, compile_constraints, feasible_portfolios
from ..schemas import AnalysisIntentRequest

ARMS = {
    "no_model": {"conversation": False, "semantic": False, "active": False},
    "conversation_only": {"conversation": True, "semantic": False, "active": False},
    "semantic_review": {"conversation": True, "semantic": True, "active": False},
    "active_sampling": {"conversation": True, "semantic": False, "active": True},
    "full_system": {"conversation": True, "semantic": True, "active": True},
}


def _finite(value, label):
    if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
        raise ValueError(f"{label}必须为非负有限数")
    return value


def _count(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"{label}必须为非负整数")
    return value


def _identifier(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}必须为非空标识")
    return value


def _ids(value, label, *, unique=True):
    if not isinstance(value, list):
        raise ValueError(f"{label}必须为标识列表")
    for item in value:
        _identifier(item, label)
    if unique and len(set(value)) != len(value):
        raise ValueError(f"{label}重复")
    return value


def _entity_pairs(value, record_ids, *, labels=False):
    if not isinstance(value, list):
        raise ValueError("实体标注与产物必须为列表")
    result = {}
    for pair in value:
        if not isinstance(pair, dict):
            raise ValueError("实体标注或产物结构无效")
        key = frozenset(
            (_identifier(pair.get("left_id"), "实体左标识"), _identifier(pair.get("right_id"), "实体右标识"))
        )
        if len(key) != 2 or not key <= record_ids or key in result:
            raise ValueError("实体标注或产物引用无效或重复")
        prediction = pair.get("same_entity") if labels else pair.get("relation")
        if labels and type(prediction) is not bool:
            raise ValueError("实体人工标签必须为布尔值")
        if not labels and prediction not in {"same_entity", "different_entity", "entrance", "department", "uncertain"}:
            raise ValueError("实体预测关系无效")
        result[key] = prediction
    return result


def compare_ablation_artifacts(dataset: dict):
    if not isinstance(dataset, dict):
        raise ValueError("消融评估数据必须为对象")
    communities = dataset.get("communities")
    if (
        not isinstance(dataset.get("label_source"), str)
        or not dataset["label_source"].strip()
        or not isinstance(communities, list)
        or not 1 <= len(communities) <= 100
    ):
        raise ValueError("消融评估需要独立标注来源和社区清单")
    community_ids = [_identifier(item.get("community_id"), "社区标识") for item in communities]
    if len(set(community_ids)) != len(communities):
        raise ValueError("消融社区标识重复")
    rows = []
    for community in communities:
        truth, arms = community["truth"], community["arms"]
        if set(arms) != set(ARMS):
            raise ValueError("每个社区必须包含固定的五组消融产物")
        category_labels = truth["category_labels"]
        if (
            not isinstance(category_labels, dict)
            or not category_labels
            or not set(category_labels.values()) <= set(CATEGORIES)
        ):
            raise ValueError("分类独立标签必须引用支持的设施类别")
        for identifier in category_labels:
            _identifier(identifier, "分类标注标识")
        record_ids = set(category_labels)
        entity_labels = _entity_pairs(truth["entity_labels"], record_ids, labels=True)
        threshold = _finite(truth["threshold_minutes"], "可达阈值")
        if threshold == 0:
            raise ValueError("可达阈值必须大于零")
        route_truth = truth["route_minutes"]
        if not isinstance(route_truth, dict) or not route_truth:
            raise ValueError("独立路线标签缺失")
        for key, value in route_truth.items():
            _identifier(key, "路线标签标识")
            _finite(value, "独立路线标签")
        candidates = {}
        for candidate in community["candidates"]:
            key = _identifier(candidate.get("id"), "候选标识")
            if key in candidates or candidate.get("category") not in CATEGORIES:
                raise ValueError("候选标识重复或类别无效")
            for field in ("cost", "capacity"):
                if candidate.get(field) is not None:
                    _finite(candidate[field], f"候选{field}")
            if candidate.get("land_allowed") is not None and type(candidate["land_allowed"]) is not bool:
                raise ValueError("候选用地状态必须为布尔值或未知")
            candidates[key] = candidate
        constraints = PortfolioConstraints.model_validate(truth["constraints"], strict=True)
        referenced = set(constraints.candidate_ids + constraints.required_ids + constraints.forbidden_ids)
        if not referenced <= set(candidates):
            raise ValueError("独立硬约束引用未知候选")
        validation_sets = []
        budgets = []
        for name, artifact in arms.items():
            predictions = artifact["category_predictions"]
            if not isinstance(predictions, dict) or not record_ids <= set(predictions):
                raise ValueError("分类产物缺少独立标注对象")
            if any(value is not None and value not in CATEGORIES for value in predictions.values()):
                raise ValueError("分类预测包含未知类别")
            correct = sum(predictions[key] == label for key, label in category_labels.items())
            pair_predictions = _entity_pairs(artifact["entity_predictions"], record_ids)
            false_merges = missed_merges = 0
            for pair, label in entity_labels.items():
                prediction = pair_predictions.get(pair) == "same_entity"
                false_merges += prediction and not label
                missed_merges += not prediction and label
            sampling = artifact["sampling"]
            if type(sampling["route_pair_budget"]) is not int or not 2 <= sampling["route_pair_budget"] <= 200:
                raise ValueError("消融采样预算超出范围")
            validation_ids = _ids(sampling["validation_ids"], "留出验证标识")
            training_ids = _ids(sampling["training_ids"], "训练标识")
            if set(validation_ids) & set(training_ids):
                raise ValueError("消融产物训练与验证样本重叠")
            if not validation_ids:
                raise ValueError("留出验证标识缺失或重复")
            if not set(training_ids) <= set(route_truth):
                raise ValueError("训练样本引用未知路线标签")
            if sampling.get("threshold_minutes", threshold) != threshold:
                raise ValueError("各组采样阈值必须与独立阈值一致")
            validation_sets.append(frozenset(validation_ids))
            budgets.append(sampling["route_pair_budget"])
            route_predictions = {}
            for item in sampling["predictions"]:
                key = _identifier(item.get("point_id"), "路线预测标识")
                if key in route_predictions or key not in route_truth:
                    raise ValueError("路线预测标识重复或缺少独立标签")
                if item["mean_minutes"] is not None:
                    _finite(item["mean_minutes"], "预测时间")
                route_predictions[key] = item["mean_minutes"]
            if not set(validation_ids) <= set(route_truth) or not set(validation_ids) <= set(route_predictions):
                raise ValueError("采样产物缺少独立路线标签或预测")
            errors = [
                abs(route_predictions[key] - route_truth[key])
                for key in validation_ids
                if route_predictions[key] is not None
            ]
            false_reachable = sum(
                route_predictions[key] is not None and route_predictions[key] <= threshold < route_truth[key]
                for key in validation_ids
            )
            selected_ids = _ids(artifact["selected_ids"], "选址产物标识", unique=False)
            unknown = set(selected_ids) - set(candidates)
            violations = len(unknown) + (len(selected_ids) != len(set(selected_ids)))
            violations += len(selected_ids) > constraints.max_facilities
            violations += bool(set(constraints.required_ids) - set(selected_ids))
            violations += bool(set(constraints.forbidden_ids) & set(selected_ids))
            violations += bool(constraints.candidate_ids and set(selected_ids) - set(constraints.candidate_ids))
            known_selected = [candidates[key] for key in selected_ids if key in candidates]
            for field, limit in (("cost", constraints.budget), ("capacity", constraints.minimum_capacity)):
                if limit is not None:
                    unknown_value = any(item.get(field) is None for item in known_selected)
                    total = sum(item.get(field) or 0 for item in known_selected)
                    violations += unknown_value or (total > limit if field == "cost" else total < limit)
            violations += constraints.allowed_land_only and any(
                item.get("land_allowed") is not True for item in known_selected
            )
            if constraints.minimum_population is not None:
                # 独立路线覆盖标签的网格并集；候选人口不能直接求和。
                coverage = truth.get("candidate_coverage")
                population = truth.get("population_by_grid")
                if (
                    not isinstance(coverage, dict)
                    or not isinstance(population, dict)
                    or not set(selected_ids) <= set(coverage)
                ):
                    violations += 1
                else:
                    grids = set()
                    for key in selected_ids:
                        grids.update(_ids(coverage[key], "独立候选覆盖网格"))
                    if not grids <= set(population):
                        violations += 1
                    else:
                        benefit = sum(_finite(population[key], "独立网格人口") for key in grids)
                        violations += benefit < constraints.minimum_population
            for category, bound in constraints.category_limits.items():
                count = sum(item["category"] == category for item in known_selected)
                violations += not bound.min <= count <= bound.max
            violations += artifact.get("predictions_used_for_official_score") is not False
            violations += any(item.get("affects_official_score") is True for item in sampling["predictions"])
            violations += sampling.get("enabled_for_official_analysis") is True
            intent_labels = truth.get("intent", {})
            intent_correct = (
                all(artifact.get("intent", {}).get(key) == value for key, value in intent_labels.items())
                if intent_labels
                else None
            )
            usage = artifact["usage"]
            _count(usage["route_pairs"], "路线对用量")
            _count(usage["model_calls"], "模型调用用量")
            for field in ("total_tokens", "physical_http_requests"):
                if usage.get(field) is not None:
                    _count(usage[field], f"{field}用量")
            violations += usage["route_pairs"] > sampling["route_pair_budget"]
            violations += usage["route_pairs"] < len(training_ids) + len(validation_ids)
            violations += not ARMS[name]["conversation"] and usage["model_calls"] > 0
            latency = _finite(artifact["latency_ms"], "端到端延迟")
            _count(artifact["review_workload"], "审核工作量")
            _count(artifact["user_steps"], "用户动作数量")
            rows.append(
                {
                    "community_id": community["community_id"],
                    "arm": name,
                    "category_accuracy": round(correct / len(category_labels), 4),
                    "category_count": len(category_labels),
                    "category_correct": correct,
                    "false_merges": int(false_merges),
                    "missed_merges": int(missed_merges),
                    "heldout_mae_minutes": sum(errors) / len(errors) if errors else None,
                    "false_reachable_count": int(false_reachable),
                    "unknown_prediction_count": len(validation_ids) - len(errors),
                    "constraint_violations": int(violations),
                    "intent_correct": intent_correct,
                    "usage": usage,
                    "latency_ms": latency,
                    "review_workload": artifact["review_workload"],
                    "user_steps": artifact["user_steps"],
                    "selected_ids": selected_ids,
                }
            )
        if len(set(validation_sets)) != 1 or len(set(budgets)) != 1:
            raise ValueError("五组消融必须使用相同留出集和路线对预算")
    aggregates = []
    for name in ARMS:
        selected = [row for row in rows if row["arm"] == name]

        def mean(key):
            values = [row[key] for row in selected if row[key] is not None]
            return sum(values) / len(values) if values else None

        aggregates.append(
            {
                "arm": name,
                "components": ARMS[name],
                "community_count": len(selected),
                "category_accuracy": round(
                    sum(row["category_correct"] for row in selected) / sum(row["category_count"] for row in selected), 4
                ),
                "false_merges": sum(row["false_merges"] for row in selected),
                "missed_merges": sum(row["missed_merges"] for row in selected),
                "heldout_mae_minutes": mean("heldout_mae_minutes"),
                "latency_ms": mean("latency_ms"),
                "constraint_violations": sum(row["constraint_violations"] for row in selected),
                "route_pairs": sum(row["usage"]["route_pairs"] for row in selected),
                "model_calls": sum(row["usage"]["model_calls"] for row in selected),
                "tokens": sum(row["usage"]["total_tokens"] for row in selected)
                if all(type(row["usage"].get("total_tokens")) is int for row in selected)
                else None,
                "review_workload": sum(row["review_workload"] for row in selected),
                "user_steps": sum(row["user_steps"] for row in selected),
            }
        )
    return {
        "contract_version": "five-arm-ablation-v1",
        "dataset_kind": dataset.get("dataset_kind", "unspecified"),
        "label_source": dataset["label_source"],
        "community_count": len(communities),
        "same_budget": True,
        "community_isolation": True,
        "arms": aggregates,
        "rows": rows,
        "effect_strength": "fixture_contract_validation_only"
        if dataset.get("dataset_kind") == "synthetic"
        else "supplied_independent_labels_not_automatically_field_verified",
        "cost_cny": None,
        "disclosure": "合成路径和脚本模型结果只能检验管线，不能证明现场精度、模型收益、真实节省配额或人工效率；token缺失与价格未知保持未知。",
    }


class FixtureModel:
    model = "scripted-fixture-no-external-service"

    def __init__(self):
        self.calls = 0

    async def generate(self, *, system, user):
        import json

        self.calls += 1
        if "category_proposals" in system:
            payload = json.loads(user)
            return {
                "category_proposals": [
                    {"record_id": record["id"], "category": "pharmacy", "confidence": 0.95, "evidence_fields": ["name"]}
                    for record in payload["records"]
                    if record["name"] == "健康驿站"
                ],
                "entity_proposals": [
                    {
                        "left_id": "a",
                        "right_id": "b",
                        "relation": "same_entity",
                        "confidence": 0.95,
                        "evidence_fields": ["name"],
                    }
                ],
            }
        return {"use_current_center": True, "minutes": 15, "categories": ["pharmacy"], "mode": "demo"}


async def run_fixture_ablations():
    """Two disjoint analytic communities; fixed labels never enter the algorithms."""
    communities = []
    for index in range(2):
        records = [
            {
                "id": "a",
                "name": "仁和药房",
                "category": "pharmacy",
                "address": "合成1号",
                "lng": 113.4 + index * 0.03,
                "lat": 23.1,
            },
            {
                "id": "b",
                "name": "仁和药房",
                "category": "pharmacy",
                "address": "合成1号",
                "lng": 113.4001 + index * 0.03,
                "lat": 23.1,
            },
            {
                "id": "c",
                "name": "健康驿站",
                "category": "market",
                "address": "合成2号",
                "lng": 113.405 + index * 0.03,
                "lat": 23.1,
            },
        ]
        points = [
            SamplingPoint(f"p{x}-{y}", (x * 200.0, y * 200.0), high_risk=x >= 3) for x in range(1, 7) for y in range(6)
        ]
        heldout = [point.id for point in points if point.features[0] == 1200]

        def oracle(point):
            x, y = point.features
            return 2 + math.hypot(x, y) / 90 + (4 + index if x > 500 and y < 500 else 0)

        async def measure(point):
            return WalkingResult(
                (113.4, 23.1),
                (113.4 + point.features[0] / 111320, 23.1 + point.features[1] / 111320),
                True,
                math.hypot(*point.features),
                oracle(point) * 60,
                "local_snapshot",
                "analytic-fixture",
            )

        candidates = [
            {"id": "plot-a", "category": "pharmacy", "cost": 40000},
            {"id": "plot-b", "category": "pharmacy", "cost": 60000},
            {"id": "plot-c", "category": "pharmacy", "cost": 80000},
        ]
        structured = {
            "max_facilities": 2,
            "budget": 100000.0,
            "category_limits": {"pharmacy": {"min": 0, "max": 2}},
            "required_ids": [],
            "forbidden_ids": [],
        }
        artifacts = {}
        for name, config in ARMS.items():
            started = time.perf_counter()
            model = FixtureModel()
            if config["conversation"]:
                interactions = ["send_analysis_message"]
                intent = (
                    await parse_analysis_intent(AnalysisIntentRequest(message="帮我体检当前选点15分钟的药店"), model)
                ).draft.model_dump()
                constraints = compile_constraints("预算10万元，最多2家药店")
            else:
                interactions = ["set_center", "set_minutes", "set_categories"]
                intent = {"use_current_center": True, "minutes": 15, "categories": ["pharmacy"]}
                constraints = PortfolioConstraints.model_validate(structured)
            review = await review_facility_semantics(
                records, model if config["semantic"] else None, coordinate_system="BD09"
            )
            category_predictions = {record["id"]: record["category"] for record in records}
            for proposal in review["category_proposals"]:
                if proposal.get("proposed_category"):
                    category_predictions[proposal["record_id"]] = proposal["proposed_category"]
            sampled = await run_sampling_experiment(
                points,
                measure,
                route_pair_budget=16,
                validation_ids=heldout,
                strategy="active" if config["active"] else "uniform",
            )
            frontier, _ = feasible_portfolios(
                candidates, {"plot-a": {"g1"}, "plot-b": {"g2"}, "plot-c": {"g1", "g2"}}, constraints
            )
            artifacts[name] = {
                "intent": intent,
                "category_predictions": category_predictions,
                "entity_predictions": [
                    {key: item[key] for key in ("left_id", "right_id", "relation")}
                    for item in review["entity_proposals"]
                ],
                "sampling": sampled,
                "selected_ids": frontier[0]["candidate_ids"],
                "predictions_used_for_official_score": False,
                "usage": {
                    "route_pairs": sampled["route_pairs_used"],
                    "model_calls": model.calls,
                    "total_tokens": None,
                    "physical_http_requests": 0,
                },
                "latency_ms": (time.perf_counter() - started) * 1000,
                "review_workload": len(review["entity_proposals"])
                + sum(bool(item.get("proposed_category")) for item in review["category_proposals"]),
                "user_steps": len(interactions),
                "interaction_trace": interactions,
            }
        communities.append(
            {
                "community_id": f"synthetic-community-{index + 1}",
                "candidates": candidates,
                "truth": {
                    "category_labels": {"a": "pharmacy", "b": "pharmacy", "c": "pharmacy"},
                    "entity_labels": [{"left_id": "a", "right_id": "b", "same_entity": True}],
                    "route_minutes": {point.id: oracle(point) for point in points},
                    "threshold_minutes": 15,
                    "intent": {"use_current_center": True, "minutes": 15, "categories": ["pharmacy"]},
                    "constraints": structured,
                },
                "arms": artifacts,
            }
        )
    dataset = {
        "dataset_kind": "synthetic",
        "label_source": "固定合成标签与解析路线oracle，非现场验证",
        "communities": communities,
    }
    return {**compare_ablation_artifacts(dataset), "artifacts": dataset}
