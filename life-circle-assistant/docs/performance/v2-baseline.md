# V2 性能基线与复测方法

本文档用于复现 V2 分析耗时、步行 API 调用和缓存收益。性能数据是运行环境下的观测值，不作为真实百度接口的固定 SLA；默认 CI 继续使用确定性本地快照与测试提供方，避免网络波动造成误报。

> **口径说明（2.1.0）**：本文既有基线数据采集于"四类设施、全类别跑 16 格盲区网格"的配置。2.1.0 起默认分析七类设施，且扩展三类（养老、公园绿地、便利超市）不参与网格测算，调用量与耗时结构已发生变化。在完成七类口径复测之前，本文数字仅反映 4 类别历史配置，不应被引用为当前版本的性能结论。

## 报告内置指标

完成报告的 `execution` 章节和前端“执行指标”区域统一展示：

- `total_duration_ms`：后端一次分析的总耗时；
- `stage_durations_ms`：请求校验、设施发现、步行计算、区域分类、评分和报告组装耗时；
- `api_calls`：设施检索与步行计算的真实地图 API 调用总数；
- `cache.hits`、`cache.misses`、`cache.hit_rate`：坐标对缓存命中、未命中与命中率；
- `metrics`：重试、超时、限流、失败、并发回退等底层计数。

阶段耗时使用单调时钟测量；API 和缓存指标由同一个 `WalkingService` 采集，避免算法模块各自统计产生口径差异。

## 测量环境记录

每次保存结果时同时记录：

- Git 提交 SHA；
- 操作系统、CPU、内存和 Python/Node 版本；
- `provider_mode`（`snapshot` 或 `real`）；
- 分析分钟数、模式与设施类别；
- 步行配置：`WALKING_MAX_CONCURRENCY`、`WALKING_QPS`、超时、重试次数和缓存 TTL；
- 数据库是否为空，以及是否执行过预热。

推荐命令：

```bash
git rev-parse HEAD
uname -a
python3 --version
node --version
```

## 本地快照模式

1. 使用独立数据库启动后端，保证冷缓存可复现：

```bash
cd life-circle-assistant
BAIDU_MAP_MODE=mock LIFE_CIRCLE_DATABASE_PATH=/tmp/life-circle-performance-snapshot.db \
  uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

2. 在另一个终端执行两次相同分析：

```bash
cd life-circle-assistant
python3 scripts/performance_baseline.py \
  --runs 2 \
  --mode demo \
  --minutes 15 \
  --output docs/performance/latest-snapshot.json
```

第一次是冷缓存，第二次是暖缓存。结果中的 `warm_run_api_reduction`、`warm_run_duration_reduction_ms` 和第二次 `cache.hits` 用于验证缓存收益。快照模式 API 调用预期为 0，但提供方调用量和分析耗时仍应下降或保持同一数量级。

## 真实 API 模式

真实模式需要有效凭证，只在人工性能复测环境运行：

```bash
cd life-circle-assistant
BAIDU_MAP_MODE=real BAIDU_MAP_AK='<服务器端 AK>' \
LIFE_CIRCLE_DATABASE_PATH=/tmp/life-circle-performance-real.db \
WALKING_MAX_CONCURRENCY=6 WALKING_QPS=8 \
  uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

python3 scripts/performance_baseline.py \
  --runs 2 \
  --mode analysis \
  --minutes 15 \
  --timeout 300 \
  --output docs/performance/latest-real.json
```

真实 API 基线重点观察：

- 第二次相同分析的 `api_calls` 应显著下降；当前设施检索仍会请求真实 API，因此不要求降为 0；
- 第二次 `cache.hits` 应增加；
- `walking_rate_limits`、`walking_timeouts` 和 `walking_failures` 不应持续增长；
- 批量或并发计算仍受 `WALKING_MAX_CONCURRENCY` 与 `WALKING_QPS` 约束。

不要把真实 API 绝对耗时设置为默认 CI 的硬门槛。网络、地图配额和提供方负载会造成合理波动。

## V2 优化结果

本轮已完成以下结构性优化：

- 报告增加统一阶段耗时、API 调用和缓存摘要，前端可直接查看；
- 报告工作台与报告比较面板改为异步组件，地图与分析参数优先进入可交互状态；
- ECharts 改为报告出现后动态加载；
- Element Plus 不再全量注册，只注册首屏实际使用的 `ElSegmented` 和 `ElSwitch`；
- Vite 将 Vue、Element Plus、ECharts 分成独立资源块，避免业务代码、图表和 UI 库混成单一初始包；
- 性能基线脚本以相同请求连续运行，直接输出冷/暖缓存差异。
- 本地快照和测试提供方默认不再套用真实 API 的 QPS 节流；显式设置 `WALKING_QPS` 时仍尊重配置。

2026-09-20 在 Apple Silicon（arm64）、Python 3.11.1、Node 22.17.0 上，以单类别、15 分钟演示模式运行一次参考采样：冷缓存后端报告耗时约 100 ms，暖缓存约 52 ms；暖缓存命中 82 个坐标对、提供方调用由 50 次降至 0。该数值用于证明测量链路与缓存收益可见，不作为其他机器的硬门槛。

构建后可用以下命令检查资源拆分：

```bash
cd life-circle-assistant/frontend
npm run build
find dist/assets -type f -maxdepth 1 -print
```

## 已知瓶颈

- 分析模式等时圈需要更多步行采样，真实 API 下仍是主要耗时来源；
- 百度轻量步行接口不支持真正矩阵批量请求，系统通过受控并发逐坐标对调用；
- 首次打开报告仍需要下载图表资源，但已不再阻塞地图首屏；
- Element Plus 样式目前仍使用统一 CSS，后续若包体证据表明样式占比突出，可再引入自动按需样式插件；
- 移动网络、真实地图脚本加载和浏览器缓存会影响“首次可交互”观测，建议使用浏览器 Performance 面板分别记录冷启动和二次访问。

## 回归判定

性能优化不得改变报告业务结果。提交前至少运行：

```bash
cd life-circle-assistant
BAIDU_MAP_MODE=mock python3 -m pytest backend/tests
cd frontend && npm run typecheck && npm test && npm run build
docker compose config
```

默认自动化只要求确定性测试通过和资源成功拆分；性能脚本的结果用于保存趋势和人工判断数量级回退。
