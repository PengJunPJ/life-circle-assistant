"""应用运行时资源装配。

这个模块只负责把数据库、仓储和地图提供方放进 FastAPI 的 ``app.state``。
路由处理函数不需要知道这些对象如何创建，只通过依赖注入读取它们。
这样可以在测试中传入临时数据库和 mock 地图提供方，也方便以后替换为
PostgreSQL、Redis 或其他实现。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from .maps import MapProvider, create_map_provider
from .maps.walking import WalkingSettings
from .storage import Database, ReportRepository, TaskRepository, WalkingCacheRepository


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

    app.state.map_provider = resolved_provider
    app.state.database = database
    app.state.task_repository = TaskRepository(database)
    app.state.report_repository = ReportRepository(database)
    app.state.walking_cache_repository = WalkingCacheRepository(database)
    app.state.walking_settings = WalkingSettings.from_env()
    # 服务重启后，之前未完成的任务不可能继续执行，统一标记为中断。
    app.state.recovered_task_count = app.state.task_repository.recover_interrupted()
    return resolved_provider
