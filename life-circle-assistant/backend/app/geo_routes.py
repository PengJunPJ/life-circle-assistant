"""用户主动补测、原生能力核验与经审核邻接的空间入口。"""

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .analysis.active_measurement import run_active_measurement
from .maps.provider import MapProviderError


class ActiveSamplingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    route_pair_budget: int = Field(default=20, ge=2, le=200)
    grid_size: int = Field(default=9, ge=3, le=15)
    high_risk_grid_ids: list[str] = Field(default_factory=list, max_length=225)
    strategy: Literal["active", "uniform", "radial", "rule_densification", "idw"] = "active"


class IsochroneProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    lng: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    minutes: int = Field(default=15, ge=1, le=60)
    strategy: Literal["foot_fastest", "foot_shortest"] = "foot_fastest"


def isochrone_capability(provider):
    capability = getattr(provider, "isochrone_capability", None)
    if callable(capability):
        return capability()
    return {
        "provider": provider.descriptor.id,
        "configured": False,
        "available": False,
        "account_verified": False,
        "pricing_verified": False,
        "disclosure": "当前地图提供方未配置原生等时圈能力；继续使用明确披露的径向路线采样。",
    }


def geo_router():
    router = APIRouter(tags=["spatial-measurement"])

    @router.get("/api/map/isochrone-capability")
    async def capability(request: Request):
        return isochrone_capability(request.app.state.map_provider)

    @router.post("/api/map/isochrone-probe")
    async def probe(payload: IsochroneProbeRequest, request: Request):
        provider = request.app.state.map_provider
        capability = isochrone_capability(provider)
        if not capability.get("configured"):
            return {**capability, "status": "disabled", "request_sent": False}
        try:
            result = await provider.native_isochrone((payload.lng, payload.lat), payload.minutes * 60, payload.strategy)
            return {
                **isochrone_capability(provider),
                "status": "available",
                "request_sent": True,
                "geometry": result.geometry,
                "source": result.source,
                "method": result.method,
            }
        except MapProviderError as exc:
            return {
                **isochrone_capability(provider),
                "status": "unavailable",
                "request_sent": True,
                "error_code": exc.code,
                "message": str(exc),
            }

    @router.post("/api/reports/{report_id}/experiments/active-sampling")
    async def sampling(report_id: str, payload: ActiveSamplingRequest, request: Request):
        report = request.app.state.report_repository.get(report_id)
        if not report or report.get("status") != "completed":
            raise HTTPException(404, "来源报告不存在或未完成")
        repository = getattr(request.app.state, "spatial_evidence_repository", None)
        center = report["analysis_center"]
        edges = repository.get_verified_edges((center["lng"], center["lat"])) if repository else []
        try:
            async with asyncio.timeout(120):
                return await run_active_measurement(
                    request.app.state.walking_service, report, adjacency_evidence=edges, **payload.model_dump()
                )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(504, "主动补测超时，原报告保持不变") from exc

    return router
