# 赛事完成度对标评估（2026-10-04）

## 结论摘要

当前分支已经覆盖赛题的主体功能和工程基础：真实百度模式下的地理编码/逆地理编码、POI 检索、步行路线与等时圈，设施覆盖和盲区分类，批量/缓存/限流/重试/降级，报告导出，Docker，自动化测试，以及带证据约束的 AI 解读均已存在。

当前最影响参赛验收的不是继续堆功能，而是把已有能力变成可提交、可复核的证据：

1. 64 个类别网格的人工真值仍未完成，基准仍为 `draft`，因此不能声称准确率、精确率、召回率、F1 或混淆矩阵。
2. `v2.1.1` 发布后的真实报告尚未重新归档；现有真实报告创建于 2026-09-21，早于 `v2.1.1`（2026-09-28）。
3. Gitee Go PR 门禁和 `master` 保护分支尚未开通、实跑、失败阻断和修复恢复验证。
4. 截图集、3~5 分钟录屏、密钥扫描记录和赛事平台材料仍为空/待人工完成。
5. 本机的 Docker daemon 不可用，因此本次只能验证 Compose 配置，不能把容器构建与冒烟标记为已复验。

## 比赛基线

比赛原始 PDF 的交付要求包括：开源源码和许可证、一键构建/部署与示例数据、地图 API 调用/等时圈/POI 清洗/盲区算法文档、特定社区真实对比报告；评分维度为功能正确性与覆盖率 40%、API 深度调用与工程优化 30%、产品交互与用户体验 15%、开源工程规范 15%。来源：仓库根目录 `【开源AI工具赛道】基于地图开发能力的“15分钟生活圈”智能体检与规划助手.pdf`，第 3、4 节。

## 必须补齐

### P0：真实社区全网格基准

- 当前 `life-circle-assistant/docs/validation/benchmarks/hongshan-haiyundonglu-20260921.json` 的 `status` 为 `draft`，64 条 `expected_kind` 仍为空。
- 指南要求完成所有类别、所有网格的独立人工核查，并保留来源、日期、核查人和道路障碍说明；只有全部完成后才能改为 `verified`。
- 指南还要求正式对外公布指标前至少建设 3~5 个社区基准。最低可接受收口是先完成首个 64 格 `verified` 基准，并把对外表述严格限定为“单社区结果”；更完整的比赛材料应继续补到 3~5 个社区。
- 证据：`life-circle-assistant/docs/validation/v2.1-benchmark-evaluation.md:24-34,58-69`；`life-circle-assistant/docs/contest/evidence-index.md:17`。

### P0：更新 `v2.1.1` 后真实报告

- 当前归档 `life-circle-assistant/docs/validation/reports/hongshan-haiyundonglu-20260921.json` 的创建时间为 2026-09-21，而 `v2.1.1` 发布说明日期为 2026-09-28。
- 需要在当前代码和同一中心点/参数下重新执行一次受控真实分析，归档报告、执行指标、数据来源和质量事件，并更新 E-05 的状态。
- 不能用旧报告证明当前版本的批量算路、缓存种子、雷达图和最新 AI/交互行为。
- 证据：`life-circle-assistant/docs/contest/evidence-index.md:11,34`；`life-circle-assistant/docs/releases/v2.1.1.md:42-46`。

### P0：Gitee CI/CD 门禁和保护分支

- 当前只有 GitHub Actions 和本地 `make quality`；README 明确说明主远端是 Gitee，GitHub Actions 不会因 Gitee 提交自动执行。
- 需要完成 Gitee Go PR 流水线的成功运行、故意失败 PR 的合并阻断、修复后的恢复三步，并在 `master` 保护分支中绑定实际检查项。
- Gitee Go 的 Node/Python 托管版本和 Docker Compose 能力存在不确定性。应先验证运行时；不能仅提交 YAML 就宣称门禁已生效，也不应未经验证把 Node 22/Python 3.12 降级到旧托管插件。
- 证据：`life-circle-assistant/README.md:171-189`；`life-circle-assistant/docs/research/gitee-go-quality-gate.md:117-130,170-199`；`life-circle-assistant/docs/contest/evidence-index.md:24`。

### P1：最终参赛证据包

- 采集截图清单中的 12 类截图（离线/真实、深色/浅色、盲区证据、评分、雷达、AI、模拟、导出、执行指标、数据质量）。当前目录只有 README，没有图片。
- 录制 3~5 分钟演示，至少覆盖离线闭环和真实模式关键能力；两种模式必须清晰区分，不能把合成快照分数当真实社区结论。
- 生成并归档一次不泄露值的密钥扫描结果，更新 E-17。
- 在赛事平台完成报名表、作品描述和视频上传；这些需要账号权限，不能由仓库代码替代。
- 证据：`life-circle-assistant/docs/contest/screenshots/README.md:3-26`；`life-circle-assistant/docs/contest/evidence-index.md:20-28`。

### P1：容器交付复验

- `docker compose config --quiet` 已通过，但本机 Docker daemon 不可用，`scripts/container-smoke.sh` 无法完成。
- 在有 Docker daemon 的干净环境执行 `make container-check` 或 `scripts/container-smoke.sh`，保存构建、健康检查和快速分析的日志/结果。
- 证据：`life-circle-assistant/Makefile:3-16`；`life-circle-assistant/scripts/container-smoke.sh:1-22`；`life-circle-assistant/docs/contest/evidence-index.md:8,22`。

## 可以优化

### 可信度与赛题口径

- 赛题盲区文字明确点名菜市场、药店、小学；项目把医疗服务也纳入核心四类网格。应在参赛说明中明确“前三类承载赛题硬指标，医疗为增强分析”，避免评委误认为口径偏离。
- 离线快照存在历史上的红山/萝岗地址与设施语义错配记录。继续保持“合成样例/非实时”披露，并在最终演示中避免用快照名称代表现实社区。
- 对真实结果中缓存、插值和降级估算混合的情况，建议在截图、录屏和口头脚本中直接展示 `data_quality` 与 `execution`，减少评委误读。
- 证据：`CONTEXT.md`；`life-circle-assistant/docs/contest/limitations.md:7-28`；`life-circle-assistant/docs/validation/v2-real-community-comparison.md`。

### 文档与版本一致性

- 证据索引仍写“后端 107+、前端 38”，发布说明写“后端 106、前端 38”，但当前实测为后端 112、前端 44。应统一测试数字并注明执行日期、运行时和命令。
- 发布说明的“CI 补充格式化/静态检查”已在当前 HEAD 落地（Ruff/ESLint），应更新为已完成或移除旧待办。
- 当前 `HEAD` 比 `v2.1.1` 多 3 个提交，包含 AI provider 和交互修复；参赛入口仍写 `2.1.1/tag v2.1.1`。若以当前 HEAD 提交参赛，应打新版本/tag并同步 README、发布说明、证据包索引；若坚持提交 `v2.1.1`，则必须明确后续提交不在参赛版本中。
- 前端同时保留 `package-lock.json` 和 `pnpm-lock.yaml`，建议明确赛事唯一安装入口（当前 CI 使用 `npm ci`），减少评审复现歧义。

### 测试与运行环境

- 当前测试通过，但 pytest 输出 `requests/urllib3` 版本警告和 `pytest-asyncio` 的 loop-scope 弃用警告。建议固定/清理依赖并显式设置 `asyncio_default_fixture_loop_scope`，避免质量记录出现可疑噪声。
- 后端没有 Python lockfile，只有版本 pin 的 requirements；如比赛环境差异较大，建议补充可复现的 Python 依赖锁定方案或记录完整运行时。
- 增加一个“证据包自检”命令，自动检查截图、真实报告版本、基准状态、密钥扫描、README 链接和测试计数，避免索引与实际材料再次漂移。

### 产品表现与评审体验

- 真实模式应优先演示真实底图、路线折线和报告质量区；mock 模式只用于无凭证闭环，不应让评委误以为等时圈来自真实路网。
- 在演示路径中固定展示一次：逐词 POI 检索/归一化、批量步行矩阵、缓存命中与降级事件。这些是 30% API 深度与工程优化分值的核心证据。
- 对“准确率未验证”的限制应放在报告、AI 面板和现场脚本的同一位置，形成一致口径；完成基准后再替换为单社区指标，并单独标注样本范围。

## 已满足或基本满足

| 赛题项 | 当前证据 |
| --- | --- |
| 源码与 Apache-2.0 许可证 | 根 `LICENSE`、`life-circle-assistant/LICENSE` |
| 一键部署与示例数据 | `life-circle-assistant/README.md:7-34`、`docker-compose.yml`、快照/缓存种子 |
| 地理编码/逆地理编码/POI/步行 API | `backend/app/main.py:141-242`、百度 provider |
| 等时圈与空间分析 | `backend/app/analysis/service.py`、`backend/app/maps/walking.py` |
| 盲区/稀疏区分类 | `backend/app/analysis/service_areas.py` |
| POI 归一化与同址归并 | `backend/app/analysis/facility_normalization.py` |
| 批量、缓存、QPS、重试、超时、降级 | `backend/app/maps/walking.py`、报告 `execution/data_quality` |
| 图层、评分、雷达、规划建议、模拟、历史、导出 | `frontend/src/components/`、`backend/app/exports/`、报告契约 |
| AI 解读与规则降级 | `backend/app/ai_assistant.py`、`backend/app/llm.py`、`frontend/src/components/AiPlanningAssistant.vue` |
| 自动化质量基线 | `.github/workflows/quality.yml`、`Makefile` |

## 本次验证记录

- 后端：`python3 -m pytest backend/tests`，112 项通过。
- 前端：`npm test`，15 个测试文件、44 项通过。
- 后端：`ruff check .`、`ruff format --check .` 通过。
- 前端：`npm run lint`、`npm run typecheck`、`npm run build` 通过。
- Compose：`docker compose config --quiet` 通过。
- 未完成：容器构建/健康检查/冒烟，因为本机 Docker daemon 不可用；真实百度分析、Gitee Go 和赛事平台材料未在本次本地环境执行。
- 安全扫描：`.env` 被 `.gitignore` 忽略且未被 Git 跟踪；本地文件中存在非空百度 AK。此次只检查存在性和长度，没有把凭证值写入报告。提交/共享前应确认未泄露并按需轮换。

