"""Public governance workflow: proposals -> reviewed catalog -> new analysis."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .analysis.service import AnalysisApplicationService
from .execution_budget import BudgetMapProvider
from .execution_ledger import record_version
from .governance.catalog import (
    CatalogMapProvider,
    apply_observation_decision,
    apply_semantic_decision,
    infer_observation_kind,
)
from .governance.ocr import validate_image
from .governance.reports import NormRegistry, build_audience_report
from .schemas import AnalyzeRequest, CoreCategory
from .storage.governance import GovernanceConflict, GovernanceRepository


class DecisionBase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    decision: Literal["accept", "reject", "correct"]
    reviewer: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def nonblank(self):
        if not self.reviewer.strip() or not self.reason.strip():
            raise ValueError("审核人和理由不能为空")
        return self


class SemanticDecision(DecisionBase):
    review_id: str = Field(min_length=1, max_length=120)
    kind: Literal["category", "entity"]
    record_id: str | None = None
    left_id: str | None = None
    right_id: str | None = None
    category: CoreCategory | None = None
    relation: Literal["same_entity", "different_entity", "department", "entrance"] | None = None


class ObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    text: str = Field(default="", max_length=5000)
    image_base64: str | None = Field(default=None, max_length=5_592_416)
    mime_type: Literal["image/png", "image/jpeg", "image/webp"] | None = None
    lng: float | None = Field(default=None, ge=-180, le=180)
    lat: float | None = Field(default=None, ge=-90, le=90)

    @model_validator(mode="after")
    def content_required(self):
        if not self.text.strip() and not self.image_base64:
            raise ValueError("请输入观察内容或提供图片")
        if (self.lng is None) != (self.lat is None):
            raise ValueError("经纬度必须同时提供")
        return self


class ObservationDecision(DecisionBase):
    kind: Literal["closure", "entrance_change", "barrier", "facility_missing", "other"] | None = None
    facility_id: str | None = None
    category: CoreCategory | None = None
    name: str | None = Field(default=None, min_length=1, max_length=512)
    lng: float | None = Field(default=None, ge=-180, le=180)
    lat: float | None = Field(default=None, ge=-90, le=90)
    first_grid_id: str | None = None
    second_grid_id: str | None = None


class AudienceReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audience: Literal["resident", "community", "planner"]
    query: str = Field(default="", max_length=1000)


def governance_repository(app) -> GovernanceRepository:
    repository = getattr(app.state, "governance_repository", None)
    if repository is None:
        repository = GovernanceRepository(app.state.database)
        app.state.governance_repository = repository
    return repository


def governance_source(app, report_id: str):
    report = app.state.report_repository.get(report_id)
    if not report or report.get("status") != "completed":
        raise HTTPException(404, "来源报告不存在或尚未完成")
    return report


def persist_semantic_review(app, report: dict, result: dict):
    record_version("semantic_review_contract", result["contract_version"])
    return governance_repository(app).save_review(report, result)


async def submit_observation(app, report: dict, payload: ObservationRequest):
    ocr_text = ""
    status = "not_requested"
    if payload.image_base64:
        if not payload.mime_type:
            raise ValueError("图片需要明确MIME类型")
        validate_image(payload.image_base64, payload.mime_type)
        ocr = getattr(app.state, "observation_ocr_provider", None)
        if ocr:
            try:
                async with asyncio.timeout(20):
                    ocr_text = await ocr.extract(payload.image_base64, payload.mime_type)
                status = "extracted_unverified"
            except Exception:
                status = "failed_pending_manual_review"
        else:
            status = "not_configured_pending_manual_review"
    observation = {
        "text": payload.text,
        "ocr_text": ocr_text,
        "ocr_status": status,
        "kind": infer_observation_kind(payload.text + " " + ocr_text),
        "lng": payload.lng,
        "lat": payload.lat,
        "location": {"lng": payload.lng, "lat": payload.lat, "coordinate_system": "BD09"},
        "mime_type": payload.mime_type,
        "source": "resident_unverified",
        "disclosure": "留言和OCR仅形成待核验观察，不修改设施、路网、盲区或评分。",
    }
    return governance_repository(app).save_observation(report, observation, payload.image_base64)


def review_semantic(app, report: dict, payload: SemanticDecision):
    repository = governance_repository(app)
    repository.ensure_catalog(report)
    data = payload.model_dump()
    return repository.decide(
        report["report_id"],
        payload.expected_version,
        target_type="review",
        target_id=payload.review_id,
        mutate=lambda catalog, review: apply_semantic_decision(catalog, review, data),
        event={"action": "semantic_decision", **data},
    )


def review_observation(app, report: dict, observation_id: str, payload: ObservationDecision):
    repository = governance_repository(app)
    repository.ensure_catalog(report)
    data = payload.model_dump()

    def apply_spatial(connection, catalog, target):
        if payload.decision == "reject" or target["kind"] != "barrier":
            return
        spatial = getattr(app.state, "spatial_evidence_repository", None)
        if spatial is None:
            raise ValueError("围挡审核需要空间证据仓储")
        center = report["analysis_center"]
        spatial.record_edge(
            center=(center["lng"], center["lat"]),
            first_grid_id=payload.first_grid_id,
            second_grid_id=payload.second_grid_id,
            blocked=True,
            source="resident_reviewed",
            reviewer=payload.reviewer,
            evidence_ref=observation_id,
            connection=connection,
        )

    result = repository.decide(
        report["report_id"],
        payload.expected_version,
        target_type="observation",
        target_id=observation_id,
        mutate=lambda catalog, observation: apply_observation_decision(catalog, observation, data),
        event={"action": "observation_decision", **data},
        after_mutate=apply_spatial,
    )
    return result


async def recompute_reviewed_catalog(app, report: dict):
    catalog = governance_repository(app).ensure_catalog(report)
    record_version("catalog", {"report_id": report["report_id"], "version": catalog["version"]})
    parameters = deepcopy(report["request"])
    parameters["categories"] = list(
        dict.fromkeys(parameters["categories"] + [record["category"] for record in catalog["records"]])
    )
    task = app.state.task_repository.create(parameters, rerun_of_report_id=report["report_id"])
    task_id = task["id"]
    app.state.task_repository.mark_running(task_id)
    bounded = BudgetMapProvider(app.state.map_provider, 4096)
    provider = CatalogMapProvider(bounded, catalog)
    try:
        service = AnalysisApplicationService(
            provider, adjacency_repository=getattr(app.state, "spatial_evidence_repository", None)
        )
        async with asyncio.timeout(120):
            result = await service.run(task_id, AnalyzeRequest.model_validate(parameters))
        result["catalog_lineage"] = {
            "source_report_id": report["report_id"],
            "catalog_version": catalog["version"],
            "immutable_source": True,
        }
        result["raw_facility_records"] = deepcopy(catalog["source_records"])
        result["catalog_reviewed_records"] = deepcopy(catalog["records"])
        result["execution"]["governance_budget"] = {
            "route_pairs_requested": bounded.used,
            "max_route_pairs": bounded.limit,
        }
        # A successful rewrite of an existing report is impossible at the database layer.
        if not app.state.report_repository.save_for_task(task_id, result):
            raise ValueError("目录重算任务已取消")
        return {
            "report_id": result["report_id"],
            "source_report_id": report["report_id"],
            "catalog_version": catalog["version"],
            "report": result,
            "affects_original_report": False,
        }
    except Exception:
        app.state.task_repository.fail(task_id, "已审核目录重算失败；来源报告保持不变")
        raise


def governance_router():
    router = APIRouter(prefix="/api/reports", tags=["governance"])

    def translate(exc):
        if isinstance(exc, GovernanceConflict):
            raise HTTPException(409, str(exc)) from exc
        raise HTTPException(422, str(exc)) from exc

    @router.get("/{report_id}/governance")
    def state(report_id: str, request: Request):
        report = governance_source(request.app, report_id)
        state = governance_repository(request.app).state(report)
        return {**state, "versions": governance_repository(request.app).versions(report_id)}

    @router.post("/{report_id}/governance/decisions")
    def decide(report_id: str, payload: SemanticDecision, request: Request):
        try:
            return review_semantic(request.app, governance_source(request.app, report_id), payload)
        except ValueError as exc:
            translate(exc)

    @router.post("/{report_id}/governance/recompute")
    async def recompute(report_id: str, request: Request):
        try:
            return await recompute_reviewed_catalog(request.app, governance_source(request.app, report_id))
        except ValueError as exc:
            translate(exc)
        except TimeoutError as exc:
            raise HTTPException(504, "目录重算超时；来源报告保持不变") from exc

    @router.post("/{report_id}/observations")
    async def observation(report_id: str, payload: ObservationRequest, request: Request):
        try:
            return await submit_observation(request.app, governance_source(request.app, report_id), payload)
        except ValueError as exc:
            translate(exc)

    @router.post("/{report_id}/observations/{observation_id}/decision")
    def observation_decision(report_id: str, observation_id: str, payload: ObservationDecision, request: Request):
        try:
            return review_observation(request.app, governance_source(request.app, report_id), observation_id, payload)
        except ValueError as exc:
            translate(exc)

    @router.get("/{report_id}/observations/{observation_id}/image")
    def observation_image(report_id: str, observation_id: str, request: Request):
        governance_source(request.app, report_id)
        stored = governance_repository(request.app).observation_image(report_id, observation_id)
        if stored is None:
            raise HTTPException(404, "该观察没有原始图片")
        return Response(
            content=validate_image(stored["image_base64"], stored["mime_type"]),
            media_type=stored["mime_type"],
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @router.post("/{report_id}/audience-report")
    def audience_report(report_id: str, payload: AudienceReportRequest, request: Request):
        report = governance_source(request.app, report_id)
        registry = getattr(request.app.state, "norm_registry", None) or NormRegistry.from_env()
        document = build_audience_report(report, payload.audience, payload.query, registry=registry)
        return governance_repository(request.app).save_audience_report(report_id, document)

    return router
