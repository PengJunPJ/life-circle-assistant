from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from .analysis import AnalysisApplicationService, compare_reports
from .analysis.simulations import ReportSimulationService, SimulationValidationError
from .maps import MapProvider, MapProviderError, create_map_provider
from .maps.support import is_in_supported_huangpu_area, require_supported_huangpu_area
from .maps.walking import WalkingService, WalkingSettings
from .mock_data import CATEGORIES, CENTER
from .schemas import AnalyzeRequest, ReportComparisonRequest, SimulationRequest
from .storage import Database, ReportRepository, TaskRepository, WalkingCacheRepository


load_dotenv()


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
        report_repository.save_for_task(task_id, report)
    except Exception as exc:
        task_repository.fail(task_id, str(exc))


def create_app(provider: MapProvider | None = None, database_path: str | Path | None = None) -> FastAPI:
    resolved_provider = provider or create_map_provider()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            client = getattr(resolved_provider, "client", None)
            close = getattr(client, "aclose", None)
            if close is not None:
                await close()

    app = FastAPI(title="15分钟生活圈智能体检与规划助手", version="0.3.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.map_provider = resolved_provider
    app.state.database = Database(database_path)
    app.state.database.migrate()
    app.state.task_repository = TaskRepository(app.state.database)
    app.state.report_repository = ReportRepository(app.state.database)
    app.state.walking_cache_repository = WalkingCacheRepository(app.state.database)
    app.state.walking_settings = WalkingSettings.from_env()
    app.state.recovered_task_count = app.state.task_repository.recover_interrupted()

    @app.get("/api/health")
    def health(map_provider: MapProvider = Depends(get_map_provider)):
        descriptor = map_provider.descriptor
        return {
            "status": "ok",
            "mode": "real" if descriptor.mode == "real" else "mock",
            "provider_mode": descriptor.mode,
            "real_api_available": descriptor.source == "real_api",
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
        try:
            resolved_center = await map_provider.reverse_geocode(analysis_request.lng, analysis_request.lat)
        except MapProviderError as exc:
            status_code = 422 if map_provider.descriptor.mode == "snapshot" else 502
            raise HTTPException(status_code=status_code, detail=f"分析中心点不可用：{exc}") from exc
        analysis_request = analysis_request.model_copy(
            update={"center_address": analysis_request.center_address.strip() or resolved_center.address}
        )
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
        report_repository: ReportRepository = Depends(get_report_repository),
    ):
        return report_repository.list_history(limit=limit, offset=offset)

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

    return app


app = create_app()
