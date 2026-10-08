# 15分钟生活圈智能体检与规划助手

面向广州市黄埔区社区规划场景的开源空间分析工具。系统基于真实步行可达性，生成 15 分钟等时圈，统计菜市场、药店、小学、医疗服务、养老、公园绿地与便利超市七类民生设施的覆盖情况，并识别重点服务盲区与设施稀疏区。其中菜市场、药店、小学与医疗服务四类核心设施参与 16 格服务盲区网格测算（对应赛题盲区口径），养老、公园绿地、便利超市三类扩展设施只计算覆盖度与最近可达，以控制步行 API 调用成本。

当前赛事交付版本为 `2.2.0`，定位为“可信、可解释的生活圈分析”功能型 Beta。版本范围、验证记录和已知限制见 [V2.2.0 发布说明](docs/releases/v2.2.0.md)，版本变化见 [更新日志](CHANGELOG.md)。离线样例适合演示和复现，不应被解读为正式规划审批结论。

## 快速运行

```bash
cp .env.example .env
docker compose up --build
```

日常开发建议保持 `.env` 的 `BAIDU_MAP_MODE=mock`，系统会优先读取 `backend/data/baidu_snapshot.json`，不会请求百度 Web 服务，也不会加载百度 JavaScript 地图，从而减少 API 额度消耗。需要联调真实数据时再切换为 `real`。

打开 <http://localhost:5173>。Docker 前端使用 Nginx 提供生产构建并将 `/api` 同源转发到后端；本地快照模式下使用离线数据，真实模式需要同时配置服务器端 `BAIDU_MAP_AK` 和浏览器端 `VITE_BAIDU_MAP_AK`。

当百度 Web 服务恢复可用后，可执行以下命令抓取一次真实体检报告并更新本地快照；抓取失败不会覆盖旧文件：

```bash
BAIDU_MAP_MODE=real PYTHONPATH=backend backend/.venv/bin/python backend/scripts/cache_baidu_snapshot.py
```

干净环境首跑加速：镜像随附默认演示中心的步行缓存种子 `backend/data/walking_cache_seed.json`（2026-09-28 真实测算快照）。启动时若步行缓存为空会自动导入并按启动时刻重盖 TTL，使评审首跑接近暖缓存耗时（实测约 19 秒、仅 18 次设施检索调用）；报告仍通过缓存命中指标和 `walking_cache_used` 质量事件披露缓存来源。设置 `LIFE_CIRCLE_SEED_WALKING_CACHE=0` 可关闭导入、强制现场真实测算。

不要直接双击 `frontend/index.html`。该文件是 Vite 源码入口，使用 `file://` 打开时浏览器会拦截 `/src/main.ts` 等 ES module 请求，页面会显示空白。请使用上面的开发服务器，或先构建再通过 HTTP 静态服务器访问：

```bash
cd frontend
npm run build
npm run serve
```

然后打开 <http://localhost:4173>。

## 本地开发

后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

如果 `.env` 位于项目根目录，后端会自动读取其中的百度地图配置；也可以在启动前通过 shell 环境变量导出 `BAIDU_MAP_AK`。

## 模式

- `mock`：读取本地百度数据快照，适合开发、测试和离线演示，不消耗百度地图 API 额度。
- `real`：调用百度地图地理编码、POI、步行路线 Web 服务，并加载百度地图 JavaScript 底图。

真实模式需要同时满足：百度 Web 服务 AK 已开通地理编码、地点检索和步行路线权限；浏览器端 AK 已将 `localhost` 或实际访问域名加入域名白名单。`BAIDU_MAP_SECRET` 只在后端使用，不会返回给浏览器。

### 脱敏环境变量

`.env.example` 只包含空值占位符，不要把真实 AK、Secret 或导出报告提交到版本库。

| 变量 | 用途 | 建议值 |
| --- | --- | --- |
| `BAIDU_MAP_MODE` | 后端提供方 | `mock` 用于离线，`real` 用于真实 API |
| `BAIDU_MAP_AK` / `BAIDU_MAP_SECRET` | 服务器端地图凭证 | 仅放在本地 `.env` 或密钥管理器 |
| `BAIDU_MAP_QPS` | 所有百度 Web 服务共享的请求节流 | 低配额开发 AK 建议 `1.5` |
| `CORS_ALLOW_ORIGINS` | 允许直接访问后端 API 的浏览器来源，逗号分隔 | 默认仅 `localhost:5173` 与 `127.0.0.1:5173`；禁止 `*` |
| `VITE_BAIDU_MAP_AK` | 浏览器底图 AK | 限制域名白名单，不与 Secret 混用 |
| `VITE_API_BASE_URL` | 前端 API 地址 | Docker 留空走 Nginx 同源 `/api`；本地 Vite 开发默认访问 `http://localhost:8000` |
| `LIFE_CIRCLE_DATABASE_PATH` | SQLite 数据库路径 | 开发可指向 `/tmp` 独立文件 |
| `WALKING_*` | 步行缓存、并发、QPS、超时与重试 | 真实 API 按配额调整，离线模式保持默认值 |
| `LLM_ENABLED` | 是否启用大模型解读 | 默认 `false`；未配置完整凭证时自动使用规则模板 |
| `LLM_PROVIDER` | 模型适配器 | 当前支持 `openai_compatible` |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI-compatible Chat Completions 配置 | 只放在本地 `.env` 或密钥管理器 |
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_TOKENS` | 模型请求超时与输出上限 | 默认 `30` 秒 / `1200` tokens |

离线快照标记为合成样例，不代表当前真实 POI。如需更新快照，只能在不输出凭证的本地环境执行抓取脚本。

### 大模型解读

大模型只负责把报告事实转换成自然语言，不负责评分、路线、盲区分类或模拟计算。后端先生成确定性的规则解读，再把去除地图几何的报告上下文发送给模型；模型返回结构化 JSON 后，服务端会校验证据引用，并在模型超时、调用失败或输出不合格时自动降级到规则模板。

启用方式示例：

```bash
LLM_ENABLED=true \
LLM_PROVIDER=openai_compatible \
LLM_BASE_URL=https://api.openai.com/v1 \
LLM_API_KEY=your-key \
LLM_MODEL=your-model \
uvicorn app.main:app --reload --port 8000
```

兼容 OpenAI Chat Completions 协议的模型服务也可以直接使用 `LLM_BASE_URL` 切换。API Key 不会返回浏览器，也不会写入报告。

## V2 报告契约兼容说明

公开分析流程仍保持 `POST /api/analyze`、`GET /api/analyze/{task_id}` 和 `GET /api/report/{task_id}`，原有 `source`、`quality`、`pois`、`zones`、`categories` 等字段继续保留。V2 报告新增以下稳定字段：

- `schema_version`、`report_id`、`task_id` 和 `completeness`；
- `calculation_mode`，记录分析档位、地图提供方模式、坐标系和步行计算方法；
- `execution`，记录具名任务阶段和执行指标；
- `data_quality`，结构化记录真实 API、缓存、本地快照、插值、降级估算和部分失败；
- `facilities`、`service_areas`、`category_scores`、`simulations` 和 `exports` 等后续功能章节。

地图能力通过统一提供方边界接入。默认离线演示使用本地快照提供方；测试可通过 `create_app(provider=...)` 注入确定性提供方，测试套件不会访问真实百度地图服务。本地快照或降级估算会明确显示“非实时数据”，不会被描述为最新真实地图测算。

## 任务与历史报告持久化

分析任务、请求参数、错误信息和完成报告保存在 SQLite。默认开发数据库位于 `backend/data/runtime/life-circle.db`，也可通过 `LIFE_CIRCLE_DATABASE_PATH` 指定；Docker Compose 使用 `analysis-data` 命名卷，因此 API 容器重建后历史报告仍可恢复。

数据库启动时会按 `backend/app/storage/migrations/` 中的版本文件顺序执行迁移。每次仓储操作使用独立连接并开启外键、WAL 和忙等待；已完成报告由数据库触发器保持不可变。服务启动时遗留的排队中或运行中任务会转换为“已失败”，并显示可重新运行的中断说明。

历史接口：

- `GET /api/reports/history`：分页获取按完成时间倒序排列的报告摘要，不加载报告正文；
- `GET /api/reports/{report_id}`：按稳定报告标识打开完整报告；
- `POST /api/reports/{report_id}/rerun`：复制原请求参数创建新的任务和报告；
- 原有 `GET /api/report/{task_id}` 保持兼容。

## 步行计算缓存与可靠调用

步行坐标对结果保存在同一 SQLite 数据库的 `walking_cache` 表中，缓存键包含提供方、有方向的起终点、步行方式和规范化坐标。只有成功结果会写入缓存，并保存原始数据来源、创建时间和过期时间；过期记录不会作为有效结果复用。

真实地图模式优先使用提供方的批量步行矩阵能力；提供方不支持批量时，系统按 `WALKING_MAX_CONCURRENCY` 和 `WALKING_QPS` 执行受控并发。超时、最大重试次数、指数退避基数和缓存有效期分别由 `WALKING_TIMEOUT_SECONDS`、`WALKING_MAX_RETRIES`、`WALKING_RETRY_BASE_SECONDS` 和 `WALKING_CACHE_TTL_SECONDS` 配置。部分坐标对失败不会使整份报告失败，但报告会标记为部分结果，受影响类别不会纳入综合评分。

`GET /api/health` 和 `GET /api/map/status` 只报告真实模式是否完成配置，不主动调用百度接口，也不把“配置完成”误报为“接口已连接”。需要验证时，在界面点击“验证 Web API”或显式调用 `POST /api/map/probe`；该操作会执行一次地理编码探测并消耗真实 API 配额。探活成功只证明地理编码端点可用，POI、步行接口和浏览器底图权限仍需分别验证。

V2 报告的 `execution.metrics` 记录步行提供方调用量、真实 API 调用量、批量调用量、缓存命中/未命中/过期量、重试、限流、超时、格式错误、最终失败、降级结果和步行计算耗时；`data_quality` 同时披露缓存、限流、超时和格式错误事件。

## 技术规则与导出

- 地图 API 分为设施发现、直线距离预筛、步行路线和报告组装四个阶段。多关键词按词分别请求，以百度 `uid` 优先、再按规范化名称+坐标去重，避免一次组合查询导致召回为零。
- 设施进入分析前统一执行语义归一化：识别稳定子类，并合并同址的医疗机构主体与下属门诊，同时保留别名和原始标识供审计。详见 [V2.1 设施语义归一化](docs/architecture/v2.1-facility-normalization.md)。
- 等时圈使用径向采样；`demo` 使用较少方向，`analysis` 增加方向和边界细化。任一采样失败都会写入数据质量事件。
- 服务区域按民生设施类别独立分类：步行超时且周边 1 公里无同类设施才是重点盲区；只满足一个条件则为稀疏区。评分包含数量、最近步行时间、空间分布三个子分，无有效数据的类别不纳入综合分。
- 规划建议引用具体类别和网格，模拟新增设施仅修改场景报告，不修改来源 POI。

### 导出指南

完成分析后，在报告面板选择 JSON、CSV、GeoJSON 或 PDF；也可直接调用：

```bash
curl -OJ http://localhost:8000/api/reports/<report_id>/exports/json
curl -OJ http://localhost:8000/api/reports/<report_id>/exports/csv
curl -OJ http://localhost:8000/api/reports/<report_id>/exports/geojson
curl -OJ http://localhost:8000/api/reports/<report_id>/exports/pdf
```

JSON 是完整报告，CSV 适合设施和评分表格，GeoJSON 使用 BD-09 坐标，PDF 适合评审与汇报。每种格式都带报告标识、参数和数据质量说明。

## 性能基线

完成报告会展示总耗时、主要阶段耗时、步行 API 调用量和缓存命中情况。可复现的本地快照与真实 API 测量命令、环境记录要求、优化结果和已知瓶颈见 [V2 性能基线文档](docs/performance/v2-baseline.md)。后端运行后可直接执行：

```bash
python3 scripts/performance_baseline.py --runs 2
```

## V2.1 全网格基准评估

项目提供从体检报告生成人工标注模板的命令行工具。完成逐格核查后，可自动输出混淆矩阵、准确率、精确率、召回率、F1 和有效预测覆盖率。命令与指标口径见 [V2.1 全网格基准评估指南](docs/validation/v2.1-benchmark-evaluation.md)。

```bash
python3 backend/scripts/evaluate_benchmark.py --help
```

## 测试

完成后端与前端依赖安装后，在应用目录执行统一质量检查：

```bash
make quality
```

该命令固定使用本地快照模式，不需要百度地图凭证，并依次执行：

- 后端接口测试；
- 前端 TypeScript/Vue 类型检查；
- 前端单元测试；
- 前端生产构建；
- 前后端容器构建、健康检查和快速分析体检报告冒烟验证。

也可以分别执行 `make backend-check`、`make frontend-check` 或 `make container-check`。

仓库保留 `.github/workflows/quality.yml`，供 GitHub 镜像仓库在推送和 Pull Request 中运行同一组检查；当前主远端位于 Gitee，因此该 GitHub Actions 配置不会因 Gitee 提交自动执行。Gitee Go 的运行时版本、Docker Compose 支持和保护分支关联方案见 [Gitee Go 质量门禁落地调研](docs/research/gitee-go-quality-gate.md)。在 Gitee Go 完成开通、实跑和保护分支绑定前，`make quality` 仍是发布前的权威验收命令。

项目文档、领域术语和架构决策位于上级 `docs/` 目录。
