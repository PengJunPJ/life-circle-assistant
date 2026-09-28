from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

AI_MODE = Literal["rule_template"]
PROMPT_VERSION = "rule-template-v2"
SUPPORTED_INTENTS = frozenset({"summary", "area_explanation", "ask", "priority", "simulation", "brief"})


@dataclass(frozen=True)
class Evidence:
    ref_type: str
    ref_id: str
    label: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "type": self.ref_type,
            "id": self.ref_id,
            "label": self.label,
            "detail": self.detail,
        }


def _build_report_index(report: dict[str, Any]) -> dict[str, set[str]]:
    """构建报告实体索引，用于校验证据引用是否指向报告中真实存在的实体。"""
    index: dict[str, set[str]] = {
        "report": set(),
        "category_score": set(),
        "service_area": set(),
        "simulation": set(),
        "facility": set(),
        "data_quality_event": set(),
    }

    # 报告 ID
    report_id = str(report.get("report_id") or report.get("id") or "")
    if report_id:
        index["report"].add(report_id)

    # 类别评分
    for item in report.get("category_scores", []):
        category = str(item.get("category") or "")
        if category:
            index["category_score"].add(category)

    # 服务区域（网格）
    features = (report.get("service_areas") or report.get("zones") or {}).get("features", [])
    for feature in features:
        props = feature.get("properties") or {}
        grid_id = str(props.get("grid_id") or "")
        if grid_id:
            index["service_area"].add(grid_id)

    # 模拟结果
    for sim in report.get("simulations") or []:
        sim_id = str(sim.get("id") or "")
        if sim_id:
            index["simulation"].add(sim_id)

    # 设施（POI）
    for poi in report.get("pois") or report.get("facilities") or []:
        poi_id = str(poi.get("id") or "")
        if poi_id:
            index["facility"].add(poi_id)

    # 数据质量事件
    quality = report.get("data_quality") or {}
    for event in quality.get("events") or []:
        event_id = str(event.get("id") or event.get("code") or "")
        if event_id:
            index["data_quality_event"].add(event_id)

    return index


def _validate_evidence_refs(
    evidence_refs: list[dict[str, str]],
    index: dict[str, set[str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """校验证据引用，返回 (有效引用, 无效引用)。"""
    valid: list[dict[str, str]] = []
    invalid: list[dict[str, str]] = []

    for ref in evidence_refs:
        ref_type = ref.get("type", "")
        ref_id = ref.get("id", "")

        # 检查类型是否已知
        if ref_type not in index:
            invalid.append(ref)
            continue

        # 检查 ID 是否存在于索引中
        if ref_id and ref_id in index[ref_type]:
            valid.append(ref)
        else:
            invalid.append(ref)

    return valid, invalid


def _filter_hallucinated_content(
    result: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    """过滤 AI 结果中的幻觉内容：无效证据引用、虚构评分、虚构步行时间等。"""
    index = _build_report_index(report)

    # 校验顶层证据引用
    evidence_refs = result.get("evidence_refs") or []
    valid_refs, invalid_refs = _validate_evidence_refs(evidence_refs, index)

    # 校验建议中的证据引用
    filtered_recommendations = []
    for rec in result.get("recommendations") or []:
        rec_refs = rec.get("evidence_refs") or []
        valid_rec_refs, _ = _validate_evidence_refs(rec_refs, index)
        filtered_rec = {**rec, "evidence_refs": valid_rec_refs}
        filtered_recommendations.append(filtered_rec)

    # 如果所有证据都无效，标记为降级
    all_invalid = len(invalid_refs) > 0 and len(valid_refs) == 0
    if all_invalid:
        result["data_quality_notice"] = (
            "AI 解读引用的证据无法在当前报告中找到，已降级为仅基于报告摘要的解读。原始体检报告仍可正常使用。"
        )
        result["mode"] = "rule_template_degraded"

    result["evidence_refs"] = valid_refs
    result["recommendations"] = filtered_recommendations

    # 记录被过滤的无效引用数量（用于调试，不暴露给前端）
    if invalid_refs:
        result["_filtered_invalid_refs"] = len(invalid_refs)

    return result


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _category_labels(report: dict[str, Any]) -> dict[str, str]:
    return {
        str(item.get("category")): str(item.get("label") or item.get("category"))
        for item in report.get("category_scores", [])
    }


def _quality_notice(report: dict[str, Any]) -> str:
    quality = report.get("data_quality") or {}
    status = quality.get("overall_status")
    if report.get("completeness") == "partial" or status == "partial":
        return "当前报告包含部分失败结果，以下解读只覆盖已获得有效证据的类别和网格。"
    if status in {"limited", "degraded"}:
        return "当前报告包含快照、插值或降级估算，AI 解读不能替代最新地图核验。"
    return "事实依据来自当前生活圈体检报告；AI 不会修改原始评分、路线和设施数据。"


def _report_evidence(report: dict[str, Any]) -> list[Evidence]:
    summary = report.get("summary") or {}
    return [
        Evidence(
            "report",
            str(report.get("report_id") or report.get("id")),
            "体检报告",
            f"综合指数 {summary.get('score') if summary.get('score') is not None else '暂不可用'}",
        ),
    ]


def _score_evidence(report: dict[str, Any], category: str) -> Evidence | None:
    for item in report.get("category_scores", []):
        if item.get("category") == category:
            label = item.get("label") or category
            score = item.get("score")
            return Evidence(
                "category_score", category, f"{label}评分", f"评分 {score if score is not None else '暂不可用'}"
            )
    return None


def _area_evidence(area: dict[str, Any]) -> Evidence:
    props = area.get("properties") or {}
    return Evidence(
        "service_area",
        str(props.get("grid_id")),
        f"{props.get('category_label', props.get('category', '设施'))}{props.get('label', '服务区域')}",
        str(props.get("basis") or "当前网格分类依据已记录在报告中。"),
    )


def _areas(
    report: dict[str, Any], *, kind: str | None = None, grid_id: str | None = None, category: str | None = None
) -> list[dict[str, Any]]:
    features = (report.get("service_areas") or report.get("zones") or {}).get("features", [])
    result = []
    for feature in features:
        props = feature.get("properties") or {}
        if kind and props.get("kind") != kind:
            continue
        if grid_id and props.get("grid_id") != grid_id:
            continue
        if category and props.get("category") != category:
            continue
        result.append(feature)
    return result


def _simulation_evidence(simulation: dict[str, Any]) -> Evidence:
    label = simulation.get("category_label") or simulation.get("category") or "候选设施"
    delta = simulation.get("delta") or {}
    detail_parts: list[str] = []
    if delta.get("category_score") is not None:
        detail_parts.append(f"类别评分变化 {delta['category_score']:+d}")
    if delta.get("overall_score") is not None:
        detail_parts.append(f"综合指数变化 {delta['overall_score']:+d}")
    if delta.get("critical_zone_count") is not None:
        detail_parts.append(f"重点盲区变化 {delta['critical_zone_count']:+d}")
    detail = "；".join(detail_parts) if detail_parts else "本次模拟未产生可展示的评分变化。"
    return Evidence("simulation", str(simulation.get("id")), f"{label}模拟", detail)


def _top_issues(report: dict[str, Any]) -> list[tuple[str, str, list[Evidence]]]:
    labels = _category_labels(report)
    issues: list[tuple[str, str, list[Evidence]]] = []
    for area in _areas(report, kind="critical")[:3]:
        props = area["properties"]
        category = labels.get(str(props.get("category")), str(props.get("category")))
        evidence = [_area_evidence(area)]
        score = _score_evidence(report, str(props.get("category")))
        if score:
            evidence.append(score)
        issues.append(
            (
                f"{category}存在重点服务盲区",
                str(props.get("basis") or "最近同类设施步行时间或周边设施数量未满足要求。"),
                evidence,
            )
        )
    for score in sorted(
        report.get("category_scores", []), key=lambda item: item.get("score") if item.get("score") is not None else 101
    )[:2]:
        if score.get("score") is None:
            continue
        category = str(score.get("label") or score.get("category"))
        evidence = [_score_evidence(report, str(score.get("category")))]
        issues.append(
            (
                f"{category}服务水平需要关注",
                str(score.get("status_explanation") or f"当前类别评分为 {score.get('score')}。"),
                [item for item in evidence if item],
            )
        )
    return issues[:4]


def _recommendations(report: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for item in report.get("recommendations", [])[:4]:
        evidence = []
        for region_id in item.get("target_region_ids", [])[:3]:
            area = next(iter(_areas(report, grid_id=region_id)), None)
            if area:
                evidence.append(_area_evidence(area))
        score = _score_evidence(report, str(item.get("category")))
        if score:
            evidence.append(score)
        result.append(
            {
                "title": item.get("title") or "关注重点服务区域",
                "text": item.get("rationale")
                or item.get("description")
                or "结合报告中的服务区域和类别评分进行优先研判。",
                "priority": item.get("priority") or "medium",
                "evidence_refs": [ref.as_dict() for ref in evidence],
            }
        )
    if not result:
        result.append(
            {
                "title": "保持现有服务覆盖并持续复核",
                "text": "当前报告没有形成可直接引用的重点规划建议，建议结合人口、容量和现场通行条件继续核验。",
                "priority": "low",
                "evidence_refs": [ref.as_dict() for ref in _report_evidence(report)],
            }
        )
    return result


def _priority_ranking(report: dict[str, Any]) -> list[dict[str, Any]]:
    """按类别评分升序 + 重点盲区数降序对民生设施类别排序，只使用报告已有指标。"""
    ranking: list[dict[str, Any]] = []
    for item in report.get("category_scores", []):
        category = str(item.get("category"))
        if not category:
            continue
        critical_count = len(_areas(report, kind="critical", category=category))
        sparse_count = len(_areas(report, kind="sparse", category=category))
        ranking.append(
            {
                "category": category,
                "label": str(item.get("label") or category),
                "score": item.get("score"),
                "critical_count": critical_count,
                "sparse_count": sparse_count,
                "status_explanation": str(item.get("status_explanation") or ""),
            }
        )

    def sort_key(entry: dict[str, Any]) -> tuple[int, int, int]:
        score = entry["score"]
        # 分数越低越靠前；无分数排最后
        score_rank = 10**6 if score is None else int(score)
        return (score_rank, -int(entry["critical_count"]), -int(entry["sparse_count"]))

    ranking.sort(key=sort_key)
    return ranking


def _priority_priority_label(index: int, entry: dict[str, Any]) -> str:
    if entry["score"] is None:
        return "low"
    if index == 0 or entry["critical_count"] > 0:
        return "high"
    if entry["sparse_count"] > 0:
        return "medium"
    return "low"


def _build_priority_result(
    report: dict[str, Any],
    *,
    category: str | None = None,
) -> dict[str, Any]:
    labels = _category_labels(report)
    ranking = _priority_ranking(report)
    if category:
        if category not in labels and category not in {item["category"] for item in ranking}:
            raise ValueError("当前报告中不存在该民生设施类别")
        ranking = [item for item in ranking if item["category"] == category]

    if not ranking:
        return _base_result(
            report,
            intent="priority",
            summary="当前报告没有可用于优先级排序的类别评分，请先完成分析或核对报告完整性。",
            recommendations=[],
            evidence=_report_evidence(report),
        )

    recommendations: list[dict[str, Any]] = []
    evidence: list[Evidence] = []
    for index, entry in enumerate(ranking[:5]):
        score_ref = _score_evidence(report, entry["category"])
        entry_evidence: list[Evidence] = []
        if score_ref:
            entry_evidence.append(score_ref)
            evidence.append(score_ref)
        critical_areas = _areas(report, kind="critical", category=entry["category"])[:2]
        for area in critical_areas:
            ref = _area_evidence(area)
            entry_evidence.append(ref)
            evidence.append(ref)
        detail_bits: list[str] = []
        if entry["score"] is not None:
            detail_bits.append(f"类别评分 {entry['score']}")
        else:
            detail_bits.append("类别评分暂不可用")
        if entry["critical_count"]:
            detail_bits.append(f"重点服务盲区 {entry['critical_count']} 个")
        if entry["sparse_count"]:
            detail_bits.append(f"设施稀疏区 {entry['sparse_count']} 个")
        rationale = "；".join(detail_bits)
        if entry["status_explanation"]:
            rationale = f"{rationale}；{entry['status_explanation']}"
        recommendations.append(
            {
                "title": f"{'优先补充' if _priority_priority_label(index, entry) == 'high' else '关注'}{entry['label']}",
                "text": rationale,
                "priority": _priority_priority_label(index, entry),
                "evidence_refs": [ref.as_dict() for ref in entry_evidence],
            }
        )

    head = ranking[0]
    tail_hint = ""
    if len(ranking) > 1:
        tail = ranking[-1]
        tail_hint = f"；{tail['label']}当前评分或覆盖状况相对较好，可保持常态复核"
    summary = (
        f"按报告类别评分与重点服务盲区数量排序，优先关注{head['label']}"
        f"（评分 {head['score'] if head['score'] is not None else '暂不可用'}，"
        f"重点服务盲区 {head['critical_count']} 个）{tail_hint}。"
    )
    if category:
        summary = f"针对{labels.get(category, category)}的优先级研判：{summary}"

    deduped_evidence: list[Evidence] = []
    seen: set[tuple[str, str]] = set()
    for ref in _report_evidence(report) + evidence:
        key = (ref.ref_type, ref.ref_id)
        if key in seen:
            continue
        seen.add(key)
        deduped_evidence.append(ref)

    return _base_result(
        report,
        intent="priority",
        summary=summary,
        recommendations=recommendations,
        evidence=deduped_evidence[:12],
    )


def _pick_simulation(
    report: dict[str, Any],
    *,
    simulation_id: str | None = None,
    category: str | None = None,
) -> dict[str, Any] | None:
    simulations = report.get("simulations") or []
    if not simulations:
        return None
    if simulation_id:
        for item in simulations:
            if str(item.get("id")) == simulation_id:
                return item
        raise ValueError("当前报告中不存在该规划模拟结果")
    if category:
        matches = [item for item in simulations if item.get("category") == category]
        if not matches:
            raise ValueError("当前报告没有该类别的规划模拟结果")
        return matches[-1]
    return simulations[-1]


def _build_simulation_result(
    report: dict[str, Any],
    *,
    simulation_id: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    simulation = _pick_simulation(report, simulation_id=simulation_id, category=category)
    if simulation is None:
        return _base_result(
            report,
            intent="simulation",
            summary=(
                "当前报告还没有已完成的新增设施模拟，因此不能承诺具体改善数值。"
                "请先在规划建议或地图中选择类别和候选位置运行模拟，然后再让 AI 解读。"
            ),
            recommendations=[],
            evidence=_report_evidence(report),
        )

    delta = simulation.get("delta") or {}
    hypothetical = simulation.get("hypothetical_facility") or {}
    label = simulation.get("category_label") or simulation.get("category") or "候选设施"

    change_bits: list[str] = []
    if delta.get("category_score") is not None:
        change_bits.append(f"{label}类别评分变化 {delta['category_score']:+d}")
    if delta.get("overall_score") is not None:
        change_bits.append(f"综合指数变化 {delta['overall_score']:+d}")
    if delta.get("coverage_area_sqm") is not None:
        change_bits.append(f"覆盖面积变化 {delta['coverage_area_sqm']:+,.0f} 平方米")
    if delta.get("critical_zone_count") is not None:
        change_bits.append(f"重点服务盲区变化 {delta['critical_zone_count']:+d} 个")
    if delta.get("sparse_zone_count") is not None:
        change_bits.append(f"设施稀疏区变化 {delta['sparse_zone_count']:+d} 个")
    walk_minutes = hypothetical.get("walk_minutes")
    if walk_minutes is not None:
        change_bits.append(f"假设设施步行时间 {walk_minutes} 分钟")

    if not change_bits:
        summary = f"针对{label}的模拟已完成，但报告未提供可展示的评分或覆盖变化，建议在方案比较中直接引用模拟原始结果。"
    else:
        summary = (
            f"针对{label}的候选设施模拟显示："
            + "；".join(change_bits)
            + "。以上数值全部来自报告中已完成的模拟结果，AI 不会自行估算新的改善数值。"
        )

    sim_evidence = _simulation_evidence(simulation)
    evidence: list[Evidence] = [sim_evidence]
    score_ref = _score_evidence(report, str(simulation.get("category")))
    if score_ref:
        evidence.append(score_ref)

    disclosure = (
        (simulation.get("data_quality") or {}).get("disclosure")
    ) or "模拟结果仅用于方案比较，不修改来源设施或原始体检报告。"
    recommendations = [
        {
            "title": "结合规划建议与现场条件复核",
            "text": f"{disclosure}建议核对候选点用地可行性、步行路径真实通行条件，再决定是否纳入规划。",
            "priority": "medium",
            "evidence_refs": [sim_evidence.as_dict()],
        }
    ]

    return _base_result(
        report,
        intent="simulation",
        summary=summary,
        recommendations=recommendations,
        evidence=_report_evidence(report) + evidence,
    )


def _build_brief_result(report: dict[str, Any]) -> dict[str, Any]:
    summary_data = report.get("summary") or {}
    center = report.get("center") or {}
    params = report.get("parameters") or {}
    address = center.get("address") or params.get("center_address") or "当前分析中心"
    minutes = params.get("minutes") or 15
    score = summary_data.get("score")
    critical = summary_data.get("critical_zone_count", 0)
    sparse = summary_data.get("sparse_zone_count", 0)

    issues = _top_issues(report)
    ranking = _priority_ranking(report)
    top_label = ranking[0]["label"] if ranking else None

    opening = f"{address}{minutes}分钟生活圈体检综合指数为 {score if score is not None else '暂不可用'}"
    body = f"识别到重点服务盲区 {critical} 个、设施稀疏区 {sparse} 个"
    if top_label:
        body += f"，按报告类别评分排序优先关注{top_label}"
    if issues:
        head_issue = issues[0][0]
        body += f"；主要问题：{head_issue}"

    tail = "以上结论均来自本次体检报告，AI 不会修改原始评分、路线和设施数据。"
    summary = f"{opening}，{body}。{tail}"

    evidence: list[Evidence] = list(_report_evidence(report))
    for _, _, refs in issues[:2]:
        evidence.extend(refs)
    if ranking:
        score_ref = _score_evidence(report, ranking[0]["category"])
        if score_ref:
            evidence.append(score_ref)

    deduped: list[Evidence] = []
    seen: set[tuple[str, str]] = set()
    for ref in evidence:
        key = (ref.ref_type, ref.ref_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)

    recommendations = _recommendations(report)[:2]
    return _base_result(
        report,
        intent="brief",
        summary=summary,
        recommendations=recommendations,
        evidence=deduped[:10],
    )


def _base_result(
    report: dict[str, Any],
    *,
    intent: str,
    summary: str,
    recommendations: list[dict[str, Any]],
    evidence: list[Evidence],
) -> dict[str, Any]:
    return {
        "intent": intent,
        "summary": summary,
        "recommendations": recommendations,
        "evidence_refs": [item.as_dict() for item in evidence],
        "model": "规则模板",
        "mode": "rule_template",
        "prompt_version": PROMPT_VERSION,
        "generated_at": _now(),
        "data_quality_notice": _quality_notice(report),
        "boundary_notice": "AI 只解释当前报告，不会修改原始评分、路线和设施数据，也不会替代百度地图或服务区域分类。",
    }


def build_ai_interpretation(
    report: dict[str, Any],
    *,
    intent: str = "summary",
    grid_id: str | None = None,
    question: str | None = None,
    category: str | None = None,
    simulation_id: str | None = None,
) -> dict[str, Any]:
    if intent not in SUPPORTED_INTENTS:
        raise ValueError(f"不支持的 AI 解读类型：{intent}")

    labels = _category_labels(report)
    result: dict[str, Any]

    if intent == "area_explanation":
        area = next(iter(_areas(report, grid_id=grid_id)), None) if grid_id else None
        if area is None:
            raise ValueError("当前报告中不存在该服务区域")
        props = area["properties"]
        evidence = [_area_evidence(area)]
        score = _score_evidence(report, str(props.get("category")))
        if score:
            evidence.append(score)
        result = _base_result(
            report,
            intent=intent,
            summary=f"{props.get('category_label', labels.get(str(props.get('category')), '该类别'))}的{props.get('label', '服务区域')}：{props.get('basis') or '报告未提供更细的分类依据。'}",
            recommendations=[
                {
                    "title": "结合现场条件复核",
                    "text": "重点核对社区出入口、围墙、道路过街和设施实际开放情况，再决定是否需要规划干预。",
                    "priority": "medium",
                    "evidence_refs": [item.as_dict() for item in evidence],
                }
            ],
            evidence=evidence,
        )
    elif intent == "priority":
        result = _build_priority_result(report, category=category)
    elif intent == "simulation":
        result = _build_simulation_result(report, simulation_id=simulation_id, category=category)
    elif intent == "brief":
        result = _build_brief_result(report)
    elif intent == "ask":
        normalized = (question or "").strip()
        if any(word in normalized for word in ("为什么", "盲区", "网格")):
            critical = _areas(report, kind="critical")
            if critical:
                result = build_ai_interpretation(
                    report, intent="area_explanation", grid_id=critical[0]["properties"].get("grid_id")
                )
            else:
                result = _base_result(
                    report,
                    intent=intent,
                    summary="当前报告没有识别到重点服务盲区，无法解释盲区原因。",
                    recommendations=[],
                    evidence=_report_evidence(report),
                )
        elif any(word in normalized for word in ("模拟", "新增", "改善")):
            result = _build_simulation_result(report)
        elif any(word in normalized for word in ("汇报", "报告一下", "简报", "街道")):
            result = _build_brief_result(report)
        elif any(word in normalized for word in ("补什么", "优先", "设施", "排序")):
            result = _build_priority_result(report, category=category)
        else:
            result = _base_result(
                report,
                intent=intent,
                summary="我目前只能基于本次报告回答摘要、盲区原因、类别优先级、候选设施模拟和汇报摘要等问题。请从示例问题中选择一个方向。",
                recommendations=[],
                evidence=_report_evidence(report),
            )
    else:
        # summary intent
        issues = _top_issues(report)
        summary_score = (report.get("summary") or {}).get("score")
        summary = f"本次生活圈体检综合指数为 {summary_score if summary_score is not None else '暂不可用'}，识别到 {(report.get('summary') or {}).get('critical_zone_count', 0)} 个重点服务盲区和 {(report.get('summary') or {}).get('sparse_zone_count', 0)} 个设施稀疏区。"
        evidence = _report_evidence(report)
        for _, _, refs in issues:
            evidence.extend(refs)
        result = _base_result(
            report, intent="summary", summary=summary, recommendations=_recommendations(report), evidence=evidence[:10]
        )

    # 出口统一校验：过滤幻觉内容
    return _filter_hallucinated_content(result, report)
