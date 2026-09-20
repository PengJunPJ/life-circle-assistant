from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from .analysis import AnalysisApplicationService
from .maps import MapProvider, MapProviderError, create_map_provider
from .mock_data import CATEGORIES, CENTER
from .schemas import AnalyzeRequest
from .storage import Database, ReportRepository, TaskRepository


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

    service = AnalysisApplicationService(app.state.map_provider, update_stage)
    try:
        report = await service.run(task_id, analysis_request)
        report_repository.save_for_task(task_id, report)
    except Exception as exc:
        task_repository.fail(task_id, str(exc))


def create_app(provider: MapProvider | None = None, database_path: str | Path | None = None) -> FastAPI:
    app = FastAPI(title="15分钟生活圈智能体检与规划助手", version="0.3.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.map_provider = provider or create_map_provider()
    app.state.database = Database(database_path)
    app.state.database.migrate()
    app.state.task_repository = TaskRepository(app.state.database)
    app.state.report_repository = ReportRepository(app.state.database)
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
        first = candidates[0]
        return {
            "source": map_provider.descriptor.source,
            "result": {"location": {"lng": first.lng, "lat": first.lat}, "formatted_address": first.address},
            "candidates": [asdict(candidate) for candidate in candidates],
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
    def create_analysis(
        analysis_request: AnalyzeRequest,
        background_tasks: BackgroundTasks,
        request: Request,
        task_repository: TaskRepository = Depends(get_task_repository),
    ):
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

    return app


app = create_app()
