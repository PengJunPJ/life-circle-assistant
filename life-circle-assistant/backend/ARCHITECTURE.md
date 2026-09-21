# 后端结构说明

## 当前分层

```text
app/main.py                 HTTP 路由、请求校验和错误映射
app/bootstrap.py            运行时装配（数据库、仓储、地图适配器）
app/analysis/               生活圈分析领域逻辑
app/maps/                   地图提供方接口及百度/快照适配器
app/storage/                SQLite 连接、迁移和仓储
app/contracts/              报告输出的稳定结构
app/exports/                JSON/CSV/GeoJSON/PDF 导出适配器
app/validation/             基准数据校验
tests/                      以公开接口为主的单元测试
```

## 为什么这样拆分

- `analysis` 不直接访问 SQLite，也不依赖百度 HTTP 细节；它只依赖 `MapProvider`
  和步行服务接口，因此可以用 mock provider 测试。
- `maps` 是外部系统适配器。以后增加高德或离线数据源时，实现同一接口即可，调用方无需改变。
- `storage` 隐藏 SQL 和连接生命周期。路由只通过仓储读取任务和报告，不拼接 SQL。
- `bootstrap` 只做装配，不放业务规则；`main.py` 仍保留路由，便于初学者按 URL 查找代码。

## 后续演进建议

当路由继续增长时，再按用例拆成 `app/api/map_routes.py`、`analysis_routes.py`、
`report_routes.py` 和 `export_routes.py`，每个文件只创建一个 `APIRouter`。当前先不强行拆分，
避免为了目录好看而增加跨文件跳转；路由拆分应以文件超过约 200 行或多人并行修改为触发条件。

## 一次分析的依赖方向

```text
HTTP 路由 -> AnalysisApplicationService -> MapProvider / WalkingService
    |                         |                    |
    +-> Repository             +-> contracts        +-> 百度/快照 Adapter
```

箭头表示“调用或依赖”。业务逻辑不应反向依赖 FastAPI、SQLite 或具体百度客户端。
