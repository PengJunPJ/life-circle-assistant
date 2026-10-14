"""应用运行时资源装配。

这个模块只负责把数据库、仓储和地图提供方放进 FastAPI 的 ``app.state``。
路由处理函数不需要知道这些对象如何创建，只通过依赖注入读取它们。
这样可以在测试中传入临时数据库和 mock 地图提供方，也方便以后替换为
PostgreSQL、Redis 或其他实现。
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from .amap import AmapPoiClient
from .baidu import BaiduMapClient
from .execution_ledger import ExecutionRepository, LedgerLLMProvider, LedgerMapProvider
from .governance.embeddings import create_embedding_provider_from_env
from .governance.ocr import create_ocr_provider_from_env
from .governance.reports import NormRegistry
from .llm import create_llm_provider
from .maps import MapProvider, create_map_provider
from .maps.walking import WalkingSettings
from .storage import Database, ReportRepository, TaskRepository, WalkingCacheRepository
from .storage.governance import GovernanceRepository
from .storage.spatial_evidence import SpatialEvidenceRepository
from .storage.walking_cache_seed import seed_from_env
from .storage.workspaces import WorkspaceRepository
from .validation.amap_facility import AmapFacilityValidator


def configure_runtime(
    app: FastAPI,
    *,
    provider: MapProvider | None = None,
    database_path: str | Path | None = None,
) -> MapProvider:
    """创建并注册应用运行期间共享的适配器。

    返回地图提供方是为了让 ``lifespan`` 能在应用关闭时释放 HTTP 客户端。
    这里不创建业务服务；业务服务应在请求或后台任务中按需创建，避免共享
    可变的分析状态。
    """

    resolved_provider = provider or create_map_provider()
    database = Database(database_path)
    database.migrate()

    app.state.execution_repository = ExecutionRepository(database)
    app.state.map_provider = LedgerMapProvider(resolved_provider)
    app.state.amap_validator = None
    if os.getenv("AMAP_VALIDATION_ENABLED", "false").strip().lower() == "true":
        baidu_client = getattr(resolved_provider, "client", None)
        if isinstance(baidu_client, BaiduMapClient):
            app.state.amap_validator = AmapFacilityValidator(AmapPoiClient(), baidu_client)
    app.state.database = database
    app.state.task_repository = TaskRepository(database)
    app.state.report_repository = ReportRepository(database)
    app.state.workspace_repository = WorkspaceRepository(database)
    app.state.governance_repository = GovernanceRepository(database)
    app.state.semantic_embedder = create_embedding_provider_from_env()
    app.state.observation_ocr_provider = create_ocr_provider_from_env()
    app.state.norm_registry = NormRegistry.from_env()
    app.state.recovered_conversation_count = app.state.workspace_repository.recover_interrupted()
    app.state.active_analysis_tasks = {}
    app.state.walking_cache_repository = WalkingCacheRepository(database)
    app.state.walking_settings = WalkingSettings.from_env()
    from .maps.walking import WalkingService

    app.state.walking_service = WalkingService(
        app.state.map_provider, app.state.walking_cache_repository, app.state.walking_settings
    )
    app.state.spatial_evidence_repository = SpatialEvidenceRepository(database)
    app.state.llm_provider = create_llm_provider()
    if app.state.llm_provider:
        app.state.llm_provider = LedgerLLMProvider(app.state.llm_provider)
    # 干净环境首跑不必现场消耗百度配额：缓存为空时导入默认中心种子并重盖 TTL。
    app.state.seeded_walking_cache_count = seed_from_env(
        app.state.walking_cache_repository,
        app.state.walking_settings.cache_ttl_seconds,
    )
    app.state.resumable_tasks = app.state.task_repository.prepare_resume()
    app.state.recovered_task_count = len(app.state.resumable_tasks)
    return resolved_provider
