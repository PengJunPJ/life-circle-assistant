from __future__ import annotations

from typing import Any

from ..maps.provider import ProviderDescriptor
from .sources import source_label


REPORT_SCHEMA_VERSION = "2.0"


def quality_event(
    code: str,
    severity: str,
    scope: str,
    message: str,
    source: str,
    method: str,
    *,
    category: str | None = None,
    object_ref: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "scope": scope,
        "category": category,
        "object_ref": object_ref,
        "source": source,
        "method": method,
        "message": message,
    }


def build_quality_summary(
    descriptor: ProviderDescriptor,
    events: list[dict[str, Any]],
    partial_failures: list[dict[str, Any]],
) -> dict[str, Any]:
    degraded_sources = {"local_snapshot", "interpolation", "degraded_estimate"}
    used_degraded = descriptor.source in degraded_sources or any(event["source"] in degraded_sources for event in events)
    if partial_failures:
        overall_status = "partial"
    elif used_degraded:
        overall_status = "limited"
    else:
        overall_status = "good"
    primary_source_label = descriptor.label
    disclosure = (
        "当前结果包含本地快照、插值或降级估算，不代表最新真实地图测算。"
        if used_degraded
        else f"当前结果使用{descriptor.label}。"
    )
    sources = [
        {
            "kind": descriptor.source,
            "provider": descriptor.id,
            "label": primary_source_label,
            "usage": "分析主要数据来源",
            "is_latest_real_measurement": descriptor.is_latest_real_measurement,
        }
    ]
    for event in events:
        if event["source"] not in {source["kind"] for source in sources}:
            sources.append(
                {
                    "kind": event["source"],
                    "provider": descriptor.id,
                    "label": source_label(event["source"]),
                    "usage": event["scope"],
                    "is_latest_real_measurement": event["source"] == "real_api",
                }
            )
    return {
        "overall_status": overall_status,
        "summary": disclosure,
        "sources": sources,
        "events": events,
        "partial_failures": partial_failures,
    }


def create_report_skeleton(
    *,
    report_id: str,
    task_id: str,
    created_at: str,
    completed_at: str,
    request_parameters: dict[str, Any],
    center: dict[str, Any],
    descriptor: ProviderDescriptor,
    completeness: str,
    execution: dict[str, Any],
    data_quality: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "id": report_id,
        "report_id": report_id,
        "task_id": task_id,
        "status": "completed",
        "completeness": completeness,
        "created_at": created_at,
        "completed_at": completed_at,
        "parameters": request_parameters,
        "request": request_parameters,
        "center": center,
        "analysis_center": center,
        "calculation_mode": {
            "requested_mode": request_parameters["mode"],
            "provider_mode": descriptor.mode,
            "coordinate_system": "BD-09",
            "walking_method": "provider_walking_matrix",
        },
        "execution": execution,
        "data_quality": data_quality,
        # 下列章节一次性定稳，后续任务只填充内容，不再改变顶层契约。
        "isochrone": None,
        "pois": [],
        "facilities": [],
        "zones": {"type": "FeatureCollection", "features": []},
        "service_areas": {"type": "FeatureCollection", "features": []},
        "summary": {},
        "categories": [],
        "category_scores": [],
        "scoring": {},
        "recommendation_summary": {
            "status": "no_shortage",
            "message": "所选类别未发现重点服务盲区，当前无需生成补充设施建议。",
            "recommendation_count": 0,
            "target_region_count": 0,
        },
        "recommendations": [],
        "simulations": [],
        "exports": {},
        # V1 兼容字段；新代码应优先读取 calculation_mode/data_quality。
        "source": "baidu" if descriptor.source == "real_api" else descriptor.source,
        "quality": {
            "mode": descriptor.label,
            "confidence": 0.92 if descriptor.source == "real_api" else 0.76,
            "message": data_quality["summary"],
        },
    }
