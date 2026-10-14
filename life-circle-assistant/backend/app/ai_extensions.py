"""可审核 AI 增量：所有输入取自来源报告，不接受客户端编造的路线标签。"""

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .analysis.coverage_optimizer import optimize_report_coverage
from .analysis.sampling import evaluate_report_sampling
from .analysis.semantic_review import review_facility_semantics
from .execution_budget import BudgetLLMProvider, BudgetMapProvider
from .governance_routes import governance_repository, persist_semantic_review
from .mock_data import CATEGORIES


class CoverageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    candidate_ids: list[str] = Field(min_length=1, max_length=32)
    max_facilities: int = Field(ge=1, le=32)
    budget: float | None = Field(default=None, ge=0)
    costs: dict[str, float] | None = None
    method: Literal["auto", "exact", "greedy"] = "auto"


class SemanticRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    use_model: bool = False


class SamplingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    route_pair_budget: int = Field(default=20, ge=2, le=200)


async def semantic_review(app, report: dict, *, use_model: bool = False, provider=None):
    llm = provider if use_model else None
    if llm is None and use_model and app.state.llm_provider:
        llm = BudgetLLMProvider(app.state.llm_provider, 1)
    before = llm.used if llm else 0
    catalog = governance_repository(app).ensure_catalog(report)
    records = catalog["source_records"]
    result = await review_facility_semantics(
        records,
        provider=llm,
        embedder=getattr(app.state, "semantic_embedder", None),
        categories=list(CATEGORIES),
        coordinate_system="BD09",
    )
    return persist_semantic_review(
        app,
        report,
        {
            "report_id": report["report_id"],
            **result,
            "model_calls": llm.used - before if llm else 0,
            "affects_original_report": False,
        },
    )


def extension_router():
    router = APIRouter(prefix="/api/reports", tags=["ai-extensions"])

    def source(request, report_id):
        report = request.app.state.report_repository.get(report_id)
        if not report or report.get("status") != "completed":
            raise HTTPException(404, "来源报告不存在或尚未完成")
        return report

    @router.post("/{report_id}/ai/semantic-review")
    async def review(report_id: str, payload: SemanticRequest, request: Request):
        try:
            async with asyncio.timeout(60):
                return await semantic_review(request.app, source(request, report_id), use_model=payload.use_model)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(504, "语义审核超时，原报告未修改") from exc

    @router.post("/{report_id}/experiments/sampling")
    async def sampling(report_id: str, payload: SamplingRequest, request: Request):
        try:
            return await evaluate_report_sampling(
                source(request, report_id), route_pair_budget=payload.route_pair_budget
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/{report_id}/planning/coverage")
    async def optimize(report_id: str, payload: CoverageRequest, request: Request):
        try:
            async with asyncio.timeout(90):
                bounded = BudgetMapProvider(request.app.state.map_provider, 512)
                result = await optimize_report_coverage(bounded, source(request, report_id), **payload.model_dump())
                result["execution_budget"] = {
                    "max_route_pairs": bounded.limit,
                    "route_pairs_requested": bounded.used,
                    "physical_route_pairs_used": bounded.physical_route_pairs_used,
                }
                return result
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(504, "覆盖优化超时，原报告未修改") from exc

    return router
