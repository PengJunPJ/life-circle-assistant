from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal


AI_MODE = Literal["rule_template"]
PROMPT_VERSION = "rule-template-v1"


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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        Evidence("report", str(report.get("report_id") or report.get("id")), "体检报告", f"综合指数 {summary.get('score') if summary.get('score') is not None else '暂不可用'}"),
    ]


def _score_evidence(report: dict[str, Any], category: str) -> Evidence | None:
    for item in report.get("category_scores", []):
        if item.get("category") == category:
            label = item.get("label") or category
            score = item.get("score")
            return Evidence("category_score", category, f"{label}评分", f"评分 {score if score is not None else '暂不可用'}")
    return None


def _area_evidence(area: dict[str, Any]) -> Evidence:
    props = area.get("properties") or {}
    return Evidence(
        "service_area",
        str(props.get("grid_id")),
        f"{props.get('category_label', props.get('category', '设施'))}{props.get('label', '服务区域')}",
        str(props.get("basis") or "当前网格分类依据已记录在报告中。"),
    )


def _areas(report: dict[str, Any], *, kind: str | None = None, grid_id: str | None = None) -> list[dict[str, Any]]:
    features = (report.get("service_areas") or report.get("zones") or {}).get("features", [])
    result = []
    for feature in features:
        props = feature.get("properties") or {}
        if kind and props.get("kind") != kind:
            continue
        if grid_id and props.get("grid_id") != grid_id:
            continue
        result.append(feature)
    return result


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
        issues.append((f"{category}存在重点服务盲区", str(props.get("basis") or "最近同类设施步行时间或周边设施数量未满足要求。"), evidence))
    for score in sorted(report.get("category_scores", []), key=lambda item: item.get("score") if item.get("score") is not None else 101)[:2]:
        if score.get("score") is None:
            continue
        category = str(score.get("label") or score.get("category"))
        evidence = [_score_evidence(report, str(score.get("category")))]
        issues.append((f"{category}服务水平需要关注", str(score.get("status_explanation") or f"当前类别评分为 {score.get('score')}。"), [item for item in evidence if item]))
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
        result.append({
            "title": item.get("title") or "关注重点服务区域",
            "text": item.get("rationale") or item.get("description") or "结合报告中的服务区域和类别评分进行优先研判。",
            "priority": item.get("priority") or "medium",
            "evidence_refs": [ref.as_dict() for ref in evidence],
        })
    if not result:
        result.append({
            "title": "保持现有服务覆盖并持续复核",
            "text": "当前报告没有形成可直接引用的重点规划建议，建议结合人口、容量和现场通行条件继续核验。",
            "priority": "low",
            "evidence_refs": [ref.as_dict() for ref in _report_evidence(report)],
        })
    return result


def _base_result(report: dict[str, Any], *, intent: str, summary: str, recommendations: list[dict[str, Any]], evidence: list[Evidence]) -> dict[str, Any]:
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


def build_ai_interpretation(report: dict[str, Any], *, intent: str = "summary", grid_id: str | None = None, question: str | None = None) -> dict[str, Any]:
    labels = _category_labels(report)
    if intent == "area_explanation":
        area = next(iter(_areas(report, grid_id=grid_id)), None) if grid_id else None
        if area is None:
            raise ValueError("当前报告中不存在该服务区域")
        props = area["properties"]
        evidence = [_area_evidence(area)]
        score = _score_evidence(report, str(props.get("category")))
        if score:
            evidence.append(score)
        return _base_result(
            report,
            intent=intent,
            summary=f"{props.get('category_label', labels.get(str(props.get('category')), '该类别'))}的{props.get('label', '服务区域')}：{props.get('basis') or '报告未提供更细的分类依据。'}",
            recommendations=[{"title": "结合现场条件复核", "text": "重点核对社区出入口、围墙、道路过街和设施实际开放情况，再决定是否需要规划干预。", "priority": "medium", "evidence_refs": [item.as_dict() for item in evidence]}],
            evidence=evidence,
        )

    if intent == "ask":
        normalized = (question or "").strip()
        if any(word in normalized for word in ("为什么", "盲区", "网格")):
            critical = _areas(report, kind="critical")
            if critical:
                return build_ai_interpretation(report, intent="area_explanation", grid_id=critical[0]["properties"].get("grid_id"))
        if any(word in normalized for word in ("模拟", "新增", "改善")):
            simulations = report.get("simulations") or []
            if not simulations:
                return _base_result(report, intent=intent, summary="当前报告还没有已完成的新增设施模拟，因此不能承诺具体改善数值。请先在规划建议或地图中选择类别和候选位置运行模拟。", recommendations=[], evidence=_report_evidence(report))
        if any(word in normalized for word in ("补什么", "优先", "设施")):
            issues = _top_issues(report)
            evidence = [ref for _, _, refs in issues for ref in refs]
            return _base_result(report, intent=intent, summary="优先关注当前报告中重点盲区数量较多或类别评分较低的设施，先核对对应网格的步行证据，再进入候选设施模拟。", recommendations=_recommendations(report), evidence=evidence[:8])
        return _base_result(report, intent=intent, summary="我目前只能基于本次报告回答摘要、盲区原因、设施优先级和已完成模拟的问题。请从示例问题中选择一个方向。", recommendations=[], evidence=_report_evidence(report))

    issues = _top_issues(report)
    summary_score = (report.get("summary") or {}).get("score")
    summary = f"本次生活圈体检综合指数为 {summary_score if summary_score is not None else '暂不可用'}，识别到 {(report.get('summary') or {}).get('critical_zone_count', 0)} 个重点服务盲区和 {(report.get('summary') or {}).get('sparse_zone_count', 0)} 个设施稀疏区。"
    evidence = _report_evidence(report)
    for _, _, refs in issues:
        evidence.extend(refs)
    return _base_result(report, intent="summary", summary=summary, recommendations=_recommendations(report), evidence=evidence[:10])
