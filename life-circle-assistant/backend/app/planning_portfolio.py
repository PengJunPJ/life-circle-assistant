"""可信候选硬约束、有限组合帕累托和整体情景复算。"""

from __future__ import annotations

import copy
import itertools
import math
import re
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .analysis.coverage_optimizer import optimize_report_coverage
from .analysis.scoring import aggregate_overall_score, score_category
from .analysis.service_areas import build_category_service_areas
from .analysis.simulations import ReportSimulationService, _polygon_area_sqm
from .execution_budget import BudgetMapProvider
from .maps.support import require_supported_huangpu_area
from .schemas import CoreCategory
from .storage.repositories import _dump, now


class CandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(min_length=1, max_length=120)
    category: CoreCategory
    lng: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    cost: float | None = Field(default=None, ge=0)
    capacity: float | None = Field(default=None, ge=0)
    population: float | None = Field(default=None, ge=0)
    land_allowed: bool | None = None
    source: str = Field(min_length=1, max_length=500)
    verified: bool

    @model_validator(mode="after")
    def validate_evidence(self):
        require_supported_huangpu_area(self.lng, self.lat)
        if not self.verified:
            raise ValueError("候选输入必须经人工核验，未经核验的候选不能进入硬约束计算")
        return self


class CategoryLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min: int = Field(default=0, ge=0, le=32)
    max: int = Field(default=32, ge=0, le=32)

    @model_validator(mode="after")
    def ordered(self):
        if self.min > self.max:
            raise ValueError("类别最小数量不能超过最大数量")
        return self


class CandidateBatch(BaseModel):
    candidates: list[CandidateInput] = Field(min_length=1, max_length=32)


class PortfolioConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    candidate_ids: list[str] = Field(default_factory=list, max_length=32)
    max_facilities: int = Field(default=2, ge=0, le=32)
    budget: float | None = Field(default=None, ge=0)
    category_limits: dict[CoreCategory, CategoryLimit] = Field(default_factory=dict)
    required_ids: list[str] = Field(default_factory=list, max_length=32)
    forbidden_ids: list[str] = Field(default_factory=list, max_length=32)
    minimum_capacity: float | None = Field(default=None, ge=0)
    minimum_population: float | None = Field(default=None, ge=0)
    allowed_land_only: bool = False
    method: str = "auto"

    @model_validator(mode="after")
    def unique(self):
        for values in (self.candidate_ids, self.required_ids, self.forbidden_ids):
            if len(set(values)) != len(values):
                raise ValueError("候选标识不得重复")
        if set(self.required_ids) & set(self.forbidden_ids):
            raise ValueError("必须选择和禁止选择的候选冲突")
        if self.method not in {"auto", "exact", "greedy"}:
            raise ValueError("不支持的求解方式")
        return self


def compile_constraints(message: str, previous: dict | None = None) -> PortfolioConstraints:
    """只编译文字明确给出的硬约束，不推断不存在的成本或地块属性。"""
    from .analysis_intent import CATEGORY_WORDS

    data = copy.deepcopy(previous or {})
    number_map = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

    def number(value):
        if value.isascii():
            return int(value)
        total, pending = 0, 0
        for char in value:
            if char in {"十", "百", "千"}:
                total += (pending or 1) * {"十": 10, "百": 100, "千": 1000}[char]
                pending = 0
            else:
                pending = number_map[char]
        return total + pending

    budget = re.search(
        r"预算\s*(?:为|是|不超过|最多)?\s*(\d+(?:\.\d+)?|[零一二两三四五六七八九十百千]+)\s*(万)?\s*元?", message
    )
    if budget:
        value = float(budget[1]) if budget[1].isascii() else number(budget[1])
        data["budget"] = value * (10000 if budget[2] else 1)
    elif "预算" in message:
        raise ValueError("预算未能明确解析，请使用‘预算10万元’等金额格式")
    counts = list(
        re.finditer(
            r"(最多|至多|不超过|至少|不少于|恰好)?\s*([0-9]+|[一二两三四五六七八九十]+)\s*(?:个|家|处|座|所)\s*([^，,；;。0-9一二两三四五六七八九十]*)",
            message,
        )
    )
    limits = data.setdefault("category_limits", {})
    for match in counts:
        amount, suffix = number(match[2]), match[3]
        matches = [k for k, words in CATEGORY_WORDS.items() if any(w in suffix for w in words)]
        if len(matches) > 1:
            raise ValueError("请分别说明每类设施数量，不能把多个类别的共用上限自动拆分")
        if not matches:
            prefix = re.split(r"[，,；;。]", message[: match.start()])[-1][-8:]
            matches = [k for k, words in CATEGORY_WORDS.items() if any(w in prefix for w in words)]
            if len(matches) > 1:
                raise ValueError("请分别说明每类设施数量，不能把多个类别的共用上限自动拆分")
        category = matches[0] if len(matches) == 1 else None
        if category:
            limit = limits.setdefault(category, {"min": 0, "max": 32})
            if match[1] in {"至少", "不少于", "恰好"}:
                limit["min"] = amount
            if match[1] not in {"至少", "不少于"}:
                limit["max"] = amount
        elif match[1] in {"至少", "不少于", "恰好"}:
            raise ValueError("请明确最低数量对应的设施类别")
        else:
            data["max_facilities"] = amount
    if counts and "max_facilities" not in data:
        data["max_facilities"] = min(32, sum(v["max"] for v in limits.values()))
    for term, key in (
        (r"(?:只考虑|只能选择|限定候选|候选地块)", "candidate_ids"),
        (r"(?:必须选择|必须包含|必须选)", "required_ids"),
        (r"(?:禁止选择|禁止|避开|不得选择)", "forbidden_ids"),
    ):
        match = re.search(term + r"\s*[:：]?\s*([^；;。\n]+)", message)
        if match:
            ids = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]*", match[1])
            if not ids:
                raise ValueError("请提供当前候选清单中的地块标识")
            data[key] = ids
    capacity = re.search(r"(?:容量|服务能力)\s*(?:至少|不低于|>=)\s*(\d+(?:\.\d+)?)", message)
    if capacity:
        data["minimum_capacity"] = float(capacity[1])
    elif re.search(r"容量|服务能力", message):
        raise ValueError("容量约束未能解析，请使用‘容量至少200’等明确下限")
    population = re.search(r"(?:受益人口|覆盖人口|人口)\s*(?:至少|不少于|不低于|>=)\s*(\d+(?:\.\d+)?)", message)
    if population:
        data["minimum_population"] = float(population[1])
    elif "人口" in message:
        raise ValueError("人口约束需要明确下限与逐网格已核验人口数据")
    if re.search(r"(?:仅|只).*(?:可建设|合规用地)|必须.*(?:可建设|合规用地)", message):
        data["allowed_land_only"] = True
    if re.search(r"面积|用地性质|每人|费用|不能选在|不得选在|禁止.*周围", message):
        raise ValueError("请将人口需求、面积或用地性质提供为有来源的候选数据；当前文字没有可核验的结构化字段")
    return PortfolioConstraints.model_validate(data)


def candidate_inventory(app, report):
    inventory = {
        c["id"]: {**c, "source": "report_gap_representative", "verified": False}
        for rec in report.get("recommendations", [])
        for c in rec.get("candidate_locations", [])
    }
    with app.state.database.connect() as connection:
        import json

        for row in connection.execute(
            "SELECT data_json FROM planning_candidates WHERE report_id=? ORDER BY id", (report["report_id"],)
        ):
            candidate = json.loads(row["data_json"])
            inventory[candidate["id"]] = candidate
    return inventory


class GridDemand(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    grid_id: str = Field(min_length=1, max_length=120)
    population: float = Field(ge=0)
    source: str = Field(min_length=1, max_length=500)
    verified: bool


class DemandBatch(BaseModel):
    items: list[GridDemand] = Field(min_length=1, max_length=225)


def population_inventory(app, report):
    with app.state.database.connect() as connection:
        import json

        return {
            row["grid_id"]: json.loads(row["data_json"])
            for row in connection.execute(
                "SELECT grid_id,data_json FROM planning_demand WHERE report_id=? ORDER BY grid_id",
                (report["report_id"],),
            )
        }


def validate_population_data(app, report, constraints, categories):
    demand = population_inventory(app, report)
    target = {
        f["properties"]["grid_id"]
        for f in report["service_areas"]["features"]
        if f["properties"]["category"] in categories and f["properties"]["kind"] == "critical"
    }
    if constraints.minimum_population is not None and (not target or not target <= set(demand)):
        raise ValueError("人口约束需要所有目标重点盲区的逐网格已核验人口数据，请先录入需求台账")
    return {key: value["population"] for key, value in demand.items()}


def feasible_portfolios(
    candidates: list[dict],
    coverage: dict[str, set[str]],
    constraints: PortfolioConstraints,
    population=None,
    *,
    validate_coverage=True,
):
    by_id = {c["id"]: c for c in candidates}
    if not set(constraints.required_ids) <= set(by_id) or not set(constraints.forbidden_ids) <= set(by_id):
        raise ValueError("必须或禁止候选不存在于当前限定范围")
    if constraints.budget is not None and any(c.get("cost") is None for c in candidates):
        raise ValueError("预算约束需要所有候选的已核验成本，请先补齐候选数据")
    if constraints.minimum_capacity is not None and any(c.get("capacity") is None for c in candidates):
        raise ValueError("容量约束需要所有候选的已核验服务能力")
    if constraints.allowed_land_only and any(c.get("land_allowed") is None for c in candidates):
        raise ValueError("用地约束需要所有候选的已核验可建设状态")
    limit = min(constraints.max_facilities, len(candidates))
    combinations = sum(math.comb(len(candidates), n) for n in range(limit + 1))
    if combinations > 100000:
        raise ValueError("硬约束帕累托枚举超过十万组合，请缩小候选范围或设施数量")
    known_cost = all(c.get("cost") is not None for c in candidates)
    options = []
    for n in range(limit + 1):
        for subset in itertools.combinations(sorted(by_id), n):
            keys = set(subset)
            if not set(constraints.required_ids) <= keys or keys & set(constraints.forbidden_ids):
                continue
            selected = [by_id[key] for key in subset]
            if any(
                not bound.min <= sum(c["category"] == category for c in selected) <= bound.max
                for category, bound in constraints.category_limits.items()
            ):
                continue
            cost = sum(c["cost"] for c in selected) if known_cost else None
            if constraints.budget is not None and cost > constraints.budget:
                continue
            if (
                constraints.minimum_capacity is not None
                and sum(c["capacity"] for c in selected) < constraints.minimum_capacity
            ):
                continue
            if constraints.allowed_land_only and any(c["land_allowed"] is not True for c in selected):
                continue
            union = set().union(*(coverage[key] for key in subset))
            known_population = population is not None and union <= set(population)
            benefit = sum(population[key] for key in union) if known_population else None
            if constraints.minimum_population is not None and validate_coverage:
                if benefit is None:
                    raise ValueError("人口约束缺少逐网格核验数据，不能按零处理")
                if benefit < constraints.minimum_population:
                    continue
            options.append(
                {
                    "candidate_ids": list(subset),
                    "covered_grid_ids": sorted(union),
                    "covered_grid_count": len(union),
                    "confirmed_population_benefit": benefit,
                    "total_cost": cost,
                    "selected_count": n,
                }
            )
    if not options:
        raise ValueError("所提供硬约束没有可行组合，未放宽任何限制")
    known_population = all(item["confirmed_population_benefit"] is not None for item in options)

    def dominates(a, b):
        objectives_a = (
            [-a["covered_grid_count"], a["selected_count"]]
            + ([a["total_cost"]] if known_cost else [])
            + ([-a["confirmed_population_benefit"]] if known_population else [])
        )
        objectives_b = (
            [-b["covered_grid_count"], b["selected_count"]]
            + ([b["total_cost"]] if known_cost else [])
            + ([-b["confirmed_population_benefit"]] if known_population else [])
        )
        return all(x <= y for x, y in zip(objectives_a, objectives_b)) and any(
            x < y for x, y in zip(objectives_a, objectives_b)
        )

    # 相同目标只保留按标识排序最先的方案；先压缩，避免二次方扫描全部组合。
    representatives = {}
    for item in options:
        signature = (
            item["covered_grid_count"],
            item["total_cost"],
            item["selected_count"],
            item["confirmed_population_benefit"] if known_population else None,
        )
        representatives.setdefault(signature, item)
    compressed = list(representatives.values())
    frontier = [item for item in compressed if not any(dominates(other, item) for other in compressed)]
    frontier.sort(
        key=lambda x: (
            -x["covered_grid_count"],
            -(x["confirmed_population_benefit"] or 0) if known_population else 0,
            x["total_cost"] or 0,
            x["selected_count"],
            x["candidate_ids"],
        )
    )
    return frontier, combinations


async def recompute_combination(provider, report, selected):
    facilities = copy.deepcopy(report.get("facilities") or report.get("pois") or [])
    center_data = report["analysis_center"]
    center = (center_data["lng"], center_data["lat"])
    helper = ReportSimulationService(provider)
    hypothetical, events, failures = [], [], []
    for candidate in selected:
        facility, event, failure = await helper._build_hypothetical_facility(
            candidate["category"], candidate["lng"], candidate["lat"], center
        )
        facility["candidate_id"] = candidate["id"]
        hypothetical.append(facility)
        events.extend(event)
        failures.extend(failure)
    facilities.extend(hypothetical)
    affected = sorted({c["category"] for c in selected})
    areas, area_events, area_failures = await build_category_service_areas(
        provider, center, affected, facilities, report["request"]["minutes"]
    )
    events.extend(area_events)
    failures.extend(area_failures)
    original_areas = report.get("service_areas") or report.get("zones") or {"type": "FeatureCollection", "features": []}
    after_areas = {
        "type": "FeatureCollection",
        "features": [
            copy.deepcopy(f) for f in original_areas["features"] if f["properties"]["category"] not in affected
        ]
        + areas["features"],
    }
    original_scores = report.get("category_scores") or report.get("categories") or []
    scores = [
        score_category(
            s["category"],
            [f for f in facilities if f["category"] == s["category"]],
            center,
            facility_search_failed=s.get("status") == "data_unavailable",
            calculation_failed=s.get("status") == "calculation_incomplete"
            or any(
                f["properties"].get("classification_status") != "valid"
                for f in areas["features"]
                if f["properties"]["category"] == s["category"]
            ),
        )
        if s["category"] in affected
        else copy.deepcopy(s)
        for s in original_scores
    ]

    def snapshot(score, score_rows, geo):
        features = geo["features"]
        return {
            "overall_score": score,
            "category_scores": score_rows,
            "service_areas": geo,
            "critical_zone_count": sum(f["properties"]["kind"] == "critical" for f in features),
            "sparse_zone_count": sum(f["properties"]["kind"] == "sparse" for f in features),
            "unknown_zone_count": sum(f["properties"]["kind"] == "unknown" for f in features),
            "coverage_area_sqm": round(
                sum(
                    _polygon_area_sqm(f["geometry"]["coordinates"][0])
                    for f in features
                    if f["properties"]["kind"] in {"normal", "sparse"}
                )
            ),
        }

    before = snapshot(
        report.get("scoring", {}).get("score"), copy.deepcopy(original_scores), copy.deepcopy(original_areas)
    )
    after = snapshot(aggregate_overall_score(scores)["score"], scores, after_areas)
    delta = {
        key: after[key] - before[key] if after[key] is not None and before[key] is not None else None
        for key in (
            "overall_score",
            "critical_zone_count",
            "sparse_zone_count",
            "unknown_zone_count",
            "coverage_area_sqm",
        )
    }
    return {
        "id": str(uuid4()),
        "report_id": report["report_id"],
        "coordinate_system": "BD-09",
        "hypothetical": True,
        "hypothetical_facilities": hypothetical,
        "before": before,
        "after": after,
        "delta": delta,
        "data_quality": {
            "events": events,
            "partial_failures": failures,
            "disclosure": "组合整体重算，原报告保持不变；位置是假设规划点，不能据此证明用地许可。",
        },
        "coverage_area_disclosure": "覆盖面积按各类别网格面积相加；跨类别重叠仍分别统计，不表示地理面积并集。",
    }


async def optimize_portfolio(app, provider, report, constraints):
    inventory = candidate_inventory(app, report)
    ids = constraints.candidate_ids or sorted(inventory)[:16]
    if not ids or not set(ids) <= set(inventory):
        raise ValueError("请提供当前报告中的有效候选清单")
    candidates = [inventory[key] for key in ids]
    if any(c["category"] not in report["request"]["categories"] for c in candidates):
        raise ValueError("候选类别尚未分析")
    # 在任何地图调用之前完成属性、范围与枚举预算验证。
    population = validate_population_data(app, report, constraints, {c["category"] for c in candidates})
    feasible_portfolios(candidates, {key: set() for key in ids}, constraints, population, validate_coverage=False)
    extended_report = copy.deepcopy(report)
    extended_report["recommendations"] = [{"candidate_locations": candidates}]
    measured = await optimize_report_coverage(
        provider, extended_report, candidate_ids=ids, max_facilities=constraints.max_facilities
    )
    coverage = {item["candidate_id"]: set(item["covered_grid_ids"]) for item in measured["candidate_evidence"]}
    frontier, count = feasible_portfolios(candidates, coverage, constraints, population or None)
    chosen = frontier[0]
    selected = [inventory[key] for key in chosen["candidate_ids"]]
    combination = await recompute_combination(provider, report, selected)
    return {
        **measured,
        **chosen,
        "selected_candidate_ids": chosen["candidate_ids"],
        "selected_candidates": selected,
        "constraints": constraints.model_dump(),
        "pareto_solutions": frontier,
        "enumeration_combinations": count,
        "combination": combination,
        "constraint_violations": 0,
        "population_benefit": chosen["confirmed_population_benefit"],
        "confirmed_population": chosen["confirmed_population_benefit"],
        "population_disclosure": "按已测可达重点盲区网格并集及核验人口计数，跨设施/类别去重；缺少台账保持未知，不将候选人口相加。",
        "optimality_scope": "finite_candidate_confirmed_coverage_hard_constraints",
        "disclosure": "按覆盖、已知成本、设施数量以及完整核验人口收益计算帕累托；整体情景用实际路线重算，未知保持未知。",
    }


def portfolio_router():
    router = APIRouter(prefix="/api/reports", tags=["planning-portfolio"])

    def source(request, identifier):
        report = request.app.state.report_repository.get(identifier)
        if not report or report.get("status") != "completed":
            raise HTTPException(404, "来源报告不存在")
        return report

    @router.get("/{report_id}/planning/candidates")
    def candidates(report_id: str, request: Request):
        return {"items": list(candidate_inventory(request.app, source(request, report_id)).values())}

    @router.post("/{report_id}/planning/candidates")
    def import_candidates(report_id: str, payload: CandidateBatch, request: Request):
        report = source(request, report_id)
        if len({c.id for c in payload.candidates}) != len(payload.candidates):
            raise HTTPException(422, "候选标识不得重复")
        if any(c.category not in report["request"]["categories"] for c in payload.candidates):
            raise HTTPException(422, "候选类别必须属于当前报告")
        with request.app.state.database.connect() as connection:
            for c in payload.candidates:
                connection.execute(
                    "INSERT INTO planning_candidates VALUES(?,?,?,?) ON CONFLICT(report_id,id) DO UPDATE SET data_json=excluded.data_json,created_at=excluded.created_at",
                    (report_id, c.id, _dump(c.model_dump()), now()),
                )
            connection.commit()
        return candidates(report_id, request)

    @router.get("/{report_id}/planning/demand")
    def demand(report_id: str, request: Request):
        return {"items": list(population_inventory(request.app, source(request, report_id)).values())}

    @router.post("/{report_id}/planning/demand")
    def import_demand(report_id: str, payload: DemandBatch, request: Request):
        report = source(request, report_id)
        grids = {f["properties"]["grid_id"] for f in report["service_areas"]["features"]}
        if len({item.grid_id for item in payload.items}) != len(payload.items):
            raise HTTPException(422, "每个空间网格只能有一条人口需求，跨类别不得重复录入")
        if any(not item.verified or item.grid_id not in grids for item in payload.items):
            raise HTTPException(422, "人口需求必须属于报告网格且经人工核验")
        with request.app.state.database.connect() as connection:
            for item in payload.items:
                connection.execute(
                    "INSERT INTO planning_demand VALUES(?,?,?,?) ON CONFLICT(report_id,grid_id) DO UPDATE SET data_json=excluded.data_json,created_at=excluded.created_at",
                    (report_id, item.grid_id, _dump(item.model_dump()), now()),
                )
            connection.commit()
        return demand(report_id, request)

    @router.post("/{report_id}/planning/optimize")
    async def optimize(report_id: str, payload: PortfolioConstraints, request: Request):
        try:
            return await optimize_portfolio(
                request.app,
                BudgetMapProvider(request.app.state.map_provider, 5000),
                source(request, report_id),
                payload,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/{report_id}/planning/combination")
    async def combination(report_id: str, payload: PortfolioConstraints, request: Request):
        report = source(request, report_id)
        inventory = candidate_inventory(request.app, report)
        if not payload.candidate_ids or not set(payload.candidate_ids) <= set(inventory):
            raise HTTPException(422, "候选清单无效")
        selected = [inventory[key] for key in payload.candidate_ids]
        try:
            # 组合复算必须核验实际所选集合，而非仅证明子集有一个可行解。
            exact = payload.model_copy(update={"required_ids": payload.candidate_ids})
            population = validate_population_data(request.app, report, exact, {c["category"] for c in selected})
            feasible_portfolios(
                selected, {key: set() for key in payload.candidate_ids}, exact, population, validate_coverage=False
            )
            if exact.minimum_population is not None:
                result = await optimize_portfolio(
                    request.app, BudgetMapProvider(request.app.state.map_provider, 5000), report, exact
                )
                return result["combination"]
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return await recompute_combination(
            BudgetMapProvider(request.app.state.map_provider, 5000),
            report,
            selected,
        )

    return router
