from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .ai_assistant import build_ai_interpretation
from .analysis import AnalysisApplicationService, compare_reports
from .analysis.simulations import ReportSimulationService, SimulationValidationError
from .bootstrap import configure_runtime
from .exports import build_csv_export, build_geojson_export, build_json_export, build_pdf_export
from .llm import enhance_interpretation, llm_configuration
from .maps import MapProvider, MapProviderError
from .maps.support import is_in_supported_huangpu_area, require_supported_huangpu_area
from .maps.walking import WalkingService
from .mock_data import CATEGORIES, CENTER
from .schemas import AnalyzeRequest, ReportComparisonRequest, SimulationRequest
from .storage import ReportRepository, TaskRepository

load_dotenv()

APP_VERSION = "2.2.0"


def get_map_provider(request: Request) -> MapProvider:
    return request.app.state.map_provider


def get_task_repository(request: Request) -> TaskRepository:
    return request.app.state.task_repository


def get_report_repository(request: Request) -> ReportRepository:
    return request.app.state.report_repository


async def execute_analysis_task(app: FastAPI, task_id: str, analysis_request: AnalyzeRequest) -> None:
    task_repository: TaskRepository = app.state.task_repository
    report_repository: ReportRepository = app.state.report_repository
    task_repository.mark_running(task_id)

    def update_stage(code: str, label: str, progress: int) -> None:
        task_repository.update_stage(task_id, code, label, progress)

    walking_service = WalkingService(
        app.state.map_provider,
        app.state.walking_cache_repository,
        app.state.walking_settings,
    )
    service = AnalysisApplicationService(app.state.map_provider, update_stage, walking_service)
    try:
        report = await service.run(task_id, analysis_request)
        task_repository.update_request(task_id, report["request"])
        report_repository.save_for_task(task_id, report)
    except Exception as exc:
        task = task_repository.get(task_id) or {}
        active_stage_label = task.get("stage_label") or "分析"
        task_repository.fail(task_id, str(exc), stage_label=f"{active_stage_label}失败")


def create_app(provider: MapProvider | None = None, database_path: str | Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            client = getattr(resolved_provider, "client", None)
            close = getattr(client, "aclose", None)
            if close is not None:
                await close()
            llm_provider = getattr(_app.state, "llm_provider", None)
            if llm_provider is not None:
                await llm_provider.close()

    app = FastAPI(title="15分钟生活圈智能体检与规划助手", version=APP_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Report-Id", "X-Coordinate-System"],
    )
    # 将基础设施装配集中到 bootstrap，避免 create_app 同时承担太多职责。
    resolved_provider = configure_runtime(app, provider=provider, database_path=database_path)

    @app.get("/api/health")
    def health(request: Request, map_provider: MapProvider = Depends(get_map_provider)):
        descriptor = map_provider.descriptor
        return {
            "status": "ok",
            "version": APP_VERSION,
            "mode": "real" if descriptor.mode == "real" else "mock",
            "provider_mode": descriptor.mode,
            "real_api_available": descriptor.source == "real_api",
            "seeded_walking_cache": getattr(request.app.state, "seeded_walking_cache_count", 0),
            "llm": {
                **llm_configuration(),
                **(
                    request.app.state.llm_provider.health()
                    if request.app.state.llm_provider is not None and hasattr(request.app.state.llm_provider, "health")
                    else {}
                ),
            },
        }

    @app.get("/api/map/status")
    def map_status(map_provider: MapProvider = Depends(get_map_provider)):
        descriptor = map_provider.descriptor
        return {
            "mode": "real" if descriptor.mode == "real" else "mock",
            "provider_mode": descriptor.mode,
            "provider": descriptor.id,
            "source": descriptor.source,
            "real_api_available": descriptor.source == "real_api",
            "mock_available": True,
            "snapshot_available": descriptor.mode == "snapshot",
            "message": (
                "已启用百度地图 Web 服务实时测算"
                if descriptor.source == "real_api"
                else "当前使用本地百度数据快照，不代表最新真实地图测算"
            ),
        }

    @app.get("/api/map/config")
    def map_config(map_provider: MapProvider = Depends(get_map_provider)):
        # 浏览器端 AK 与服务器端 Web 服务 AK 分离，避免把后端凭据下发到浏览器。
        browser_ak = os.getenv("VITE_BAIDU_MAP_AK", "").strip()
        return {
            "mode": "real" if map_provider.descriptor.mode == "real" else "mock",
            "provider_mode": map_provider.descriptor.mode,
            "browser_ak": browser_ak if browser_ak else "",
        }

    @app.get("/api/geocode")
    async def geocode(address: str, city: str = "广州", map_provider: MapProvider = Depends(get_map_provider)):
        try:
            candidates = await map_provider.geocode(address, city)
        except MapProviderError as exc:
            status_code = 422 if map_provider.descriptor.mode == "snapshot" else 502
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        if not candidates:
            raise HTTPException(status_code=404, detail="地址没有匹配候选")
        supported_candidates = [
            candidate for candidate in candidates if is_in_supported_huangpu_area(candidate.lng, candidate.lat)
        ]
        if not supported_candidates:
            raise HTTPException(status_code=422, detail="地址候选超出当前支持范围；V2 仅支持广州市黄埔区样例")
        first = supported_candidates[0]
        return {
            "source": map_provider.descriptor.source,
            "provider": map_provider.descriptor.id,
            "result": {"location": {"lng": first.lng, "lat": first.lat}, "formatted_address": first.address},
            "candidates": [asdict(candidate) for candidate in supported_candidates],
        }

    @app.get("/api/locations/reverse")
    async def reverse_geocode(
        lng: float,
        lat: float,
        map_provider: MapProvider = Depends(get_map_provider),
    ):
        if not -180 <= lng <= 180 or not -90 <= lat <= 90:
            raise HTTPException(status_code=422, detail="请输入合法的 BD-09 经纬度")
        try:
            require_supported_huangpu_area(lng, lat)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            result = await map_provider.reverse_geocode(lng, lat)
        except MapProviderError as exc:
            status_code = 422 if map_provider.descriptor.mode == "snapshot" else 502
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        return {
            "source": map_provider.descriptor.source,
            "provider": map_provider.descriptor.id,
            "result": asdict(result),
        }

    @app.get("/api/pois")
    async def pois(
        query: str,
        lng: float = CENTER["lng"],
        lat: float = CENTER["lat"],
        radius: int = 1_000,
        map_provider: MapProvider = Depends(get_map_provider),
    ):
        try:
            results = await map_provider.search_places(query, (lng, lat), radius)
        except MapProviderError as exc:
            raise HTTPException(status_code=502, detail=f"地图地点检索失败：{exc}") from exc
        return {"source": map_provider.descriptor.source, "results": [asdict(item) for item in results]}

    @app.get("/api/route/walking")
    async def get_walking_route(
        origin_lng: float,
        origin_lat: float,
        destination_lng: float,
        destination_lat: float,
        request: Request,
        map_provider: MapProvider = Depends(get_map_provider),
    ):
        """按需返回起点到终点的步行折线：优先读步行缓存，缺失且为真实提供方才实时请求。"""
        cache = request.app.state.walking_cache_repository
        origin = (origin_lng, origin_lat)
        destination = (destination_lng, destination_lat)
        lookup = cache.get(map_provider.descriptor.id, origin, destination)
        result = lookup.result if lookup.status == "hit" else None
        if result is None or not result.steps:
            if map_provider.descriptor.mode != "real":
                raise HTTPException(status_code=409, detail="当前地图提供方不支持真实步行路线")
            if result is None:
                walking_service = WalkingService(map_provider, cache, request.app.state.walking_settings)
                matrix = await walking_service.walking_matrix([origin], [destination])
                result = matrix[0][0]
            else:
                # 旧缓存行只有距离/时长、没有折线：直连提供方补取并回写缓存。
                matrix = await map_provider.walking_matrix([origin], [destination])
                fresh = matrix[0][0]
                if fresh.success and fresh.steps:
                    cache.put(
                        map_provider.descriptor.id,
                        fresh,
                        ttl_seconds=request.app.state.walking_settings.cache_ttl_seconds,
                    )
                    result = fresh
            if not result.success or not result.steps:
                raise HTTPException(status_code=404, detail="两点之间没有可用步行路线")
        return {
            "origin": {"lng": origin[0], "lat": origin[1]},
            "destination": {"lng": destination[0], "lat": destination[1]},
            "distance_m": result.distance_m,
            "duration_s": result.duration_s,
            "polyline": result.steps,
            "source": result.source,
        }

    @app.get("/api/demo/default")
    def default_demo():
        return {"center": CENTER, "categories": CATEGORIES}

    @app.post("/api/analyze")
    async def create_analysis(
        analysis_request: AnalyzeRequest,
        background_tasks: BackgroundTasks,
        request: Request,
        task_repository: TaskRepository = Depends(get_task_repository),
        map_provider: MapProvider = Depends(get_map_provider),
    ):
        # 分析入口再次校验中心点，避免调用方绕过选点接口提交超出支持范围的位置。
        try:
            require_supported_huangpu_area(analysis_request.lng, analysis_request.lat)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"分析中心点不可用：{exc}") from exc
        task = task_repository.create(analysis_request.model_dump())
        background_tasks.add_task(execute_analysis_task, request.app, task["id"], analysis_request)
        return task

    @app.get("/api/analyze/{task_id}")
    def get_analysis(
        task_id: str,
        task_repository: TaskRepository = Depends(get_task_repository),
        report_repository: ReportRepository = Depends(get_report_repository),
    ):
        task = task_repository.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="体检任务不存在")
        if task["status"] == "completed" and task.get("report_id"):
            task["result"] = report_repository.get(task["report_id"])
        return task

    @app.get("/api/report/{task_id}")
    def get_report(
        task_id: str,
        task_repository: TaskRepository = Depends(get_task_repository),
        report_repository: ReportRepository = Depends(get_report_repository),
    ):
        task = task_repository.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="体检任务不存在")
        if task.get("status") == "failed":
            raise HTTPException(status_code=502, detail=task.get("error", "地图分析失败"))
        if task.get("status") != "completed":
            raise HTTPException(status_code=404, detail="体检报告尚未生成")
        report = report_repository.get_by_task_id(task_id)
        if not report:
            raise HTTPException(status_code=404, detail="体检报告不存在")
        return report

    @app.get("/api/reports/history")
    def list_report_history(
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        q: str | None = Query(default=None, max_length=64),
        report_repository: ReportRepository = Depends(get_report_repository),
    ):
        return report_repository.list_history(limit=limit, offset=offset, q=q)

    @app.post("/api/reports/compare")
    def compare_completed_reports(
        comparison_request: ReportComparisonRequest,
        report_repository: ReportRepository = Depends(get_report_repository),
    ):
        reports: list[dict] = []
        for report_id in comparison_request.report_ids:
            report = report_repository.get(report_id)
            if not report or report.get("status") != "completed":
                raise HTTPException(status_code=404, detail=f"报告 {report_id} 不存在或尚未完成")
            reports.append(report)
        return compare_reports(reports[0], reports[1])

    @app.get("/api/reports/{report_id}")
    def get_report_by_id(report_id: str, report_repository: ReportRepository = Depends(get_report_repository)):
        report = report_repository.get(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="历史报告不存在")
        return report

    @app.post("/api/reports/{report_id}/rerun")
    def rerun_report(
        report_id: str,
        background_tasks: BackgroundTasks,
        request: Request,
        task_repository: TaskRepository = Depends(get_task_repository),
        report_repository: ReportRepository = Depends(get_report_repository),
    ):
        report = report_repository.get(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="历史报告不存在")
        analysis_request = AnalyzeRequest.model_validate(report["request"])
        task = task_repository.create(analysis_request.model_dump(), rerun_of_report_id=report_id)
        background_tasks.add_task(execute_analysis_task, request.app, task["id"], analysis_request)
        return task

    @app.post("/api/reports/{report_id}/simulations")
    async def simulate_report_facility(
        report_id: str,
        simulation_request: SimulationRequest,
        map_provider: MapProvider = Depends(get_map_provider),
        report_repository: ReportRepository = Depends(get_report_repository),
    ):
        report = report_repository.get(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="来源体检报告不存在")
        try:
            require_supported_huangpu_area(simulation_request.lng, simulation_request.lat)
            return await ReportSimulationService(map_provider).run(report, simulation_request)
        except SimulationValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"假设设施位置不可用：{exc}") from exc

    @app.post("/api/reports/{report_id}/ai/interpret")
    async def interpret_report(
        request: Request,
        report_id: str,
        payload: dict[str, str] | None = None,
        report_repository: ReportRepository = Depends(get_report_repository),
    ):
        report = report_repository.get(report_id)
        if not report or report.get("status") != "completed":
            raise HTTPException(status_code=404, detail="历史报告不存在或尚未完成")
        request_payload = payload or {}
        intent = request_payload.get("intent", "summary")
        if intent not in {"summary", "area_explanation", "ask", "priority", "simulation", "brief"}:
            raise HTTPException(status_code=422, detail="不支持的 AI 解读类型")
        try:
            result = build_ai_interpretation(
                report,
                intent=intent,
                grid_id=request_payload.get("grid_id"),
                question=request_payload.get("question"),
                category=request_payload.get("category"),
                simulation_id=request_payload.get("simulation_id"),
            )
            question = request_payload.get("question")
            result = await enhance_interpretation(
                request.app.state.llm_provider,
                report,
                result,
                question=question,
            )
            saved = report_repository.save_ai_interpretation(report_id, result, question=question)
            return saved
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/reports/{report_id}/ai/interpretations")
    def list_report_interpretations(
        report_id: str,
        report_repository: ReportRepository = Depends(get_report_repository),
    ):
        if not report_repository.get(report_id):
            raise HTTPException(status_code=404, detail="历史报告不存在")
        return {"items": report_repository.list_ai_interpretations(report_id)}

    @app.get("/api/reports/{report_id}/exports/{export_format}")
    def export_completed_report(
        report_id: str,
        export_format: Literal["json", "csv", "geojson", "pdf"],
        report_repository: ReportRepository = Depends(get_report_repository),
    ):
        report = report_repository.get(report_id)
        if not report or report.get("status") != "completed":
            raise HTTPException(status_code=404, detail="历史报告不存在或尚未完成")
        # 注入已保存的 AI 解读，使 JSON/PDF 导出可以附带生成方式、证据引用和数据质量说明。
        # 仅在非空时注入，避免破坏「导出 JSON == 原始报告」的等值契约。
        interpretations = report_repository.list_ai_interpretations(report_id)
        if interpretations:
            report = {**report, "ai_interpretations": interpretations}
        builders = {
            "json": build_json_export,
            "csv": build_csv_export,
            "geojson": build_geojson_export,
            "pdf": build_pdf_export,
        }
        artifact = builders[export_format](report)
        return Response(
            content=artifact.content,
            media_type=artifact.media_type,
            headers={
                "Content-Disposition": artifact.content_disposition,
                "X-Report-Id": report_id,
                "X-Coordinate-System": "BD-09",
            },
        )

    return app


app = create_app()
