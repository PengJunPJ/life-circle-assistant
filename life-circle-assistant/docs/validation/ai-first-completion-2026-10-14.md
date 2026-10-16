# AI 融合方案全量补齐与验收

日期：2026-10-14。对照[实施前缺口核查](../research/ai-first-implementation-gap-audit-2026-10-13.md)的 A1–A11、B1–B6，共17项。用户授权核查后全部实现；本轮覆盖业务算法、公共 API、持久化、前端入口与回归，原核查和10月13日的部分实施记录保留为历史。

17项软件能力链已补齐，下面分别列出用户行为和验收证据。真实账号权限、部署模型效果、现场精度与账单仍需真实数据验收，不能用离线测试替代。嵌入、OCR、原生等时圈默认关闭，配置完整后使用真实适配器；关闭或失败时显示降级和未知。GNN、强化学习、DBSCAN等原方案的条件可选方法不列为必须使用的算法。

## 逐项验收矩阵

表中“测试”验证实现行为与输入输出契约，不能自动证明真实模型或地图效果。

| 编号 | 补齐的业务行为 | 源码与用户入口 | 测试证据 |
| --- | --- | --- | --- |
| A1 实际嵌入 | 启动装配兼容 embeddings 服务或已有本地 Sentence Transformers 模型；中文类别锚点匹配与空间门禁内实体候选召回，异常降级 | [embeddings.py](../../backend/app/governance/embeddings.py)、[semantic_review.py](../../backend/app/analysis/semantic_review.py)；AI核验 → 设施审核 | [test_governance.py](../../backend/tests/test_governance.py)、[test_semantic_review.py](../../backend/tests/test_semantic_review.py) |
| A2 设施治理闭环 | 保留规则归并前及辅助来源；接纳、驳回、修正类别和实体关系；事务保存目录版本与审计；按新目录正式测路重算并生成新报告 | [catalog.py](../../backend/app/governance/catalog.py)、[storage/governance.py](../../backend/app/storage/governance.py)、[governance_routes.py](../../backend/app/governance_routes.py)；AI核验 → 设施审核 | [test_governance.py](../../backend/tests/test_governance.py)、[公共治理流程](../../backend/tests/test_public_completion_workflows.py)；真实HTTP重算后旧报告逐字段不变 |
| A3 原生等时圈 | `foot_fastest/foot_shortest` 状态、显式权限探测、正式分析适配与失败回退；Polygon/MultiPolygon及孔洞校验 | [isochrone.py](../../backend/app/maps/isochrone.py)、[geo_routes.py](../../backend/app/geo_routes.py)；AI核验 → 空间补测 | [test_native_isochrone.py](../../backend/tests/test_native_isochrone.py)；真实HTTP禁用状态不发探测请求 |
| A4 预算主动补测 | 实际调用路线服务新增观测，按风险、阈值与不确定性迭代选点；读取可信障碍，留出测量包含在总预算内 | [active_measurement.py](../../backend/app/analysis/active_measurement.py)；AI核验 → 空间补测，或“主动采样实验” | [test_active_measurement.py](../../backend/tests/test_active_measurement.py)、[test_physical_route_budget.py](../../backend/tests/test_physical_route_budget.py)、[test_geo_routes.py](../../backend/tests/test_geo_routes.py) |
| A5 观测/预测/未决 | 输出观测点、观测中心所在网格外沿、预测可达格、未决带与时间场；独立地图图层可切换 | [active_measurement.py](../../backend/app/analysis/active_measurement.py)、[completionLayers.ts](../../frontend/src/utils/completionLayers.ts)、[useMapRenderer.ts](../../frontend/src/composables/useMapRenderer.ts) | [test_active_measurement.py](../../backend/tests/test_active_measurement.py)、[completionLayers.test.ts](../../frontend/src/utils/completionLayers.test.ts)、真实HTTP时间场展示 |
| A6 三类缺口与障碍 | 稀缺、步行超时、双条件重点缺口分别成片；可信障碍限制连接；候选消费分组，保留孤立格、多片几何和未知洞 | [gap_groups.py](../../backend/app/analysis/gap_groups.py)、[recommendations.py](../../backend/app/analysis/recommendations.py)、[spatial_evidence.py](../../backend/app/storage/spatial_evidence.py)；空间缺口核验与地图 | [test_gap_groups.py](../../backend/tests/test_gap_groups.py)、[test_spatial_evidence.py](../../backend/tests/test_spatial_evidence.py)、[test_geospatial_report.py](../../backend/tests/test_geospatial_report.py) |
| A7 约束编译 | 编译预算、限定/必选/禁选候选、整体和分类数量、最低容量、核验人口与可建设条件；歧义拒绝或多轮澄清 | [planning_portfolio.py](../../backend/app/planning_portfolio.py)、[conversation_tools.py](../../backend/app/conversation_tools.py)；对话及AI核验 → 组合选址 | [test_completion_portfolio.py](../../backend/tests/test_completion_portfolio.py)、[test_workspaces.py](../../backend/tests/test_workspaces.py)、[公共澄清流程](../../backend/tests/test_public_completion_workflows.py) |
| A8 可信候选与需求 | 登记带来源、核验状态及成本/容量/用地的候选；限定考虑地块；独立核验网格人口台账，缺字段保持未知 | [planning_portfolio.py](../../backend/app/planning_portfolio.py)；AI核验 → 组合选址候选/人口输入 | [test_completion_portfolio.py](../../backend/tests/test_completion_portfolio.py)、[AiCompletionWorkbench.test.ts](../../frontend/src/components/AiCompletionWorkbench.test.ts)、真实HTTP登记与必选约束 |
| A9 组合复算与帕累托 | 小规模精确枚举，组合整体测路、服务区及 `before/after/delta`；覆盖/成本/数量/完整人口收益非支配前沿；方案落图和逐个复算 | [planning_portfolio.py](../../backend/app/planning_portfolio.py)、[simulations.py](../../backend/app/analysis/simulations.py)；AI核验 → 组合选址 | [test_completion_portfolio.py](../../backend/tests/test_completion_portfolio.py)、[test_simulations.py](../../backend/tests/test_simulations.py)、真实HTTP原分68而证据不足的after/delta为null |
| A10 居民反馈 | 文字或图片、可配置OCR、原图保存查看；疑似关闭/入口变化/漏设施/围挡待审核；人工核验后事务更新目录或障碍 | [ocr.py](../../backend/app/governance/ocr.py)、[governance_routes.py](../../backend/app/governance_routes.py)；AI核验 → 居民观察，文字也可直接对话提交 | [test_governance.py](../../backend/tests/test_governance.py)、[AiCompletionWorkbench.test.ts](../../frontend/src/components/AiCompletionWorkbench.test.ts)、真实HTTP待核验及驳回 |
| A11 独立与消融评估 | 语义独立社区标签、五种空间策略同预算/空间块留出/同误差比较、五组完整消融；重复标签、训练泄漏和不可比预算拒绝 | [evaluate_semantics.py](../../backend/scripts/evaluate_semantics.py)、[evaluate_spatial_sampling.py](../../backend/scripts/evaluate_spatial_sampling.py)、[evaluate_ablations.py](../../backend/scripts/evaluate_ablations.py) | [test_spatial_sampling_evaluation.py](../../backend/tests/test_spatial_sampling_evaluation.py)、[test_ablations.py](../../backend/tests/test_ablations.py)、已保存空间与消融合成产物 |
| B1 多轮操作 | 对话选择地址/历史序号、取消、进度、失败恢复与重试、东南角等网格指代；分析运行时仍能输入取消 | [workspace_routes.py](../../backend/app/workspace_routes.py)、[ConversationWorkspace.vue](../../frontend/src/components/ConversationWorkspace.vue)、[useConversation.ts](../../frontend/src/composables/useConversation.ts) | [test_workspaces.py](../../backend/tests/test_workspaces.py)、[test_public_completion_workflows.py](../../backend/tests/test_public_completion_workflows.py)、[useConversation.test.ts](../../frontend/src/composables/useConversation.test.ts) |
| B2 工具与多步计划 | 统一声明式白名单、schema与预算目录；最多六步持久计划、继续执行、逐步确认和澄清；分类模型读取近期六轮及状态 | [conversation_tools.py](../../backend/app/conversation_tools.py)、[workspace_schemas.py](../../backend/app/workspace_schemas.py)、[workspace_routes.py](../../backend/app/workspace_routes.py) | [test_public_completion_workflows.py](../../backend/tests/test_public_completion_workflows.py)、[test_workspaces.py](../../backend/tests/test_workspaces.py)；跨create_app重启计划继续及确认 |
| B3 共享独立图层 | 独立稀缺、步行超时、重点盲区、缺口片区及预测图层；聊天、地图控件和持久工作区同步 | [MapLayerControls.vue](../../frontend/src/components/MapLayerControls.vue)、[useMapRenderer.ts](../../frontend/src/composables/useMapRenderer.ts)、[App.vue](../../frontend/src/App.vue) | [conversationWorkspace.test.ts](../../frontend/src/conversationWorkspace.test.ts)、[completionLayers.test.ts](../../frontend/src/utils/completionLayers.test.ts)、真实HTTP聊天与地图同步 |
| B4 规范与角色报告 | 项目规则/配置外部规范文段检索，版本、来源、范围、散列引用；居民/社区/规划师报告分观察、假设、措施与核验条件 | [reports.py](../../backend/app/governance/reports.py)；AI核验 → 角色报告，或“查看居民报告” | [test_governance.py](../../backend/tests/test_governance.py)、[test_packaged_project_rules.py](../../backend/tests/test_packaged_project_rules.py)、真实HTTP两类受众及容器随包规范 |
| B5 统一预算账本 | 公共入口与后台任务独立执行账本，计入实际HTTP/物理路线对/token与模型地图规则工具版本；互斥计价，人工整次执行结算及追加更正 | [execution_ledger.py](../../backend/app/execution_ledger.py)、[execution_budget.py](../../backend/app/execution_budget.py)；报告说明 → 预算与版本账本 | [test_execution_resume.py](../../backend/tests/test_execution_resume.py)、[test_execution_settlements.py](../../backend/tests/test_execution_settlements.py)、[executionApi.test.ts](../../frontend/src/services/executionApi.test.ts)、真实HTTP合成结算版本1/2 |
| B6 跨进程续算 | 成功提供方调用检查点持久复用；中断未决调用先核对和显式授权；终态/取消门禁、原预算不重置、继续同任务 | [execution_ledger.py](../../backend/app/execution_ledger.py)、[main.py](../../backend/app/main.py)、[ExecutionCheckpointReview.vue](../../frontend/src/components/ExecutionCheckpointReview.vue) | [test_analysis_checkpoint_recovery.py](../../backend/tests/test_analysis_checkpoint_recovery.py)、[test_execution_resume.py](../../backend/tests/test_execution_resume.py)、[ExecutionCheckpointReview.test.ts](../../frontend/src/components/ExecutionCheckpointReview.test.ts) |

B2使用统一声明式目录约束现有确定性分支及规划工具，不宣称已替换为动态handler插件框架。A6使用四邻接而非强行增加DBSCAN，符合原方案当前网格尺度的取舍。A9的最优性仅针对给定候选、覆盖数据和有限枚举模型；覆盖面积指标为各类别面积之和，不能称跨类别地理并集。

## 本轮额外补齐

1. 人工账单结算：终态门禁、金额校验、预期版本/用量指纹、并发冲突、只追加历史、更正版本和续算过时保护；未核验账单时 `settled_total=null`。操作者字段是审计信息，不是身份认证。
2. 容器项目规则：移除依赖深层仓库路径的启动假设，随包提供三份ADR逐字副本；浅目录启动与Docker构建后真实角色报告有引用。Compose透传嵌入、OCR、原生、规范与计价配置；容器冒烟隔离项目和测试数据。
3. 标准空间出口：新增 `/exports/geojson-wgs84` 和前端/对话入口。Point/Polygon/MultiPolygon坐标、中心及候选属性一致转换，保留孔洞、规范环方向，删除过时的 `crs/bbox`；原BD-09出口兼容，原参数逐值保留并标记源坐标系。非有限坐标、退化环或逆转换不收敛明确拒绝，HTTP返回422。

标准WGS84使用本地BD-09→GCJ-02→WGS84近似逆解，不是官方或测绘级转换。独立北京锚点及公式容差只验证数值回归，真实精度为未知；导出不改变内部BD-09地图、路径测量、缓存和评分。

## 正确性与结果披露

- 正式评分保持固定规则和同一报告事实；所有生成式事实出口绑定报告槽位，不能由模型补造分数、坐标、人口或覆盖收益。
- 预测、未核验居民观察、无来源候选和未复核辅助POI不会进入正式事实。观测网格中心可达不等于认证整个格子可达。
- 目录接纳仅产生新版本，正式重算产生新报告；数据库不可变触发器与完整用户流程检查旧报告不变。
- 未知测量、计价、token、人口、土地与容量不替换为零或默认满足。人口收益按成功测路可达网格并集去重，不能相加候选人口。
- 检查点恢复不自动重放计费未决请求，不重置原预算；人工授权重试留下依据。旧结算遇新增用量标记过时。

## 最终验证

后端最终全量回归511项全部通过，耗时562.74秒（9分22秒）；仅有Starlette测试客户端使用AnyIO旧别名的弃用提示，无测试失败。最终Ruff检查与格式检查通过（132个文件）。

前端最终全量38个文件、193项测试通过；类型检查、lint和生产构建通过。Vite保留图表chunk体积提示，不影响构建结果。

标准导出26项新增测试及4项原导出测试通过；公共对话实际下载7项流程通过。测试使用注入提供方和受控协议传输，未调用收费服务。

[真实HTTP浏览器验收](ai-first-http-smoke-2026-10-14.md)：实际uvicorn、Vite和Chrome，不拦截业务API；浏览器31个、脚本直接22个API响应，页面错误、失败请求和外部服务请求为0。实际标准导出菜单下载与接口内容一致，17个要素完成转换。所有用户流程结束后原报告不变，临时进程、端口及数据库已清理。

另有10条隔离浏览器夹具流程，用于前端确定性状态验收；夹具不代替上述真实HTTP链路。最终Docker隔离构建/扩展冒烟退出0：前端、同源API、健康、PDF、标准WGS84出口及随包项目规则的规划师报告均通过，原报告不变。Compose项目 `life-circle-ai-completion-20261014` 的容器、网络与测试数据卷已清理，可重新执行。

可复现命令：

```sh
# 后端目录
.venv/bin/python -m pytest -q
ruff check app tests scripts
ruff format --check app tests scripts

# 前端目录，使用Vite支持的Node版本
npm run test
npm run typecheck
npm run lint
npm run build

# 应用根目录，强制关闭外部服务并使用临时数据库/隔离Compose项目
node scripts/validate_completion_http.mjs
CONTAINER_SMOKE_PROJECT_NAME=life-circle-ai-completion-20261014 ./scripts/container-smoke.sh
```

## 真实效果验收条件

实现验收与效果验收分开。当前未取得真实部署账号的原生等时圈权限/报价、真实嵌入/LLM/OCR效果、独立现场标签、后验不确定性校准、候选地块适用性或真实账单；本轮没有调用这些收费服务。

现有评估可接收授权实测数据：[语义与五组评估说明](../governance/ai-first-governance-and-evaluation.md)、[空间评估说明](spatial-completion-2026-10-14.md)。空间合成契约共30组，未证明主动策略节省配额；五组消融的类别/回归差异来自脚本模型和解析路线，不能写成真实AI成绩。模型预测继续不参与正式评分，独立效果证据达标后再决定默认策略。

本轮未提交或推送Git，未修改用户已有的演示视频。
