# AI 融合方案实施缺口核查

日期：2026-10-13。核查对象为当前工作区源码（包括本轮未提交的实现），对照原始《AI大模型融合方案与专家评审》的 P0/P1/P2 与具体能力链。本文记录事实与建议，不实施新功能。

后续状态：用户授权全部补齐后，2026-10-14已实施本核查的17项软件能力链，见[全量补齐与验收](../validation/ai-first-completion-2026-10-14.md)。本文的“部分/未实现”指核查当日状态，保留用于对照；真实模型和现场效果仍需独立实测。

## 结论与核查口径

用户所说“只实现了部分功能”成立。目前已经落地可信对话的基础链路、地图契约修正和若干 AI/规划实验，但尚未完成方案描述的“语义治理 → 主动测量 → 缺口分组 → 约束组合规划 → 反馈复核”完整闭环。尤其不能将“可注入嵌入接口”“复用报告路线的离线 GPR 实验”“有限候选覆盖并集求解”分别等同于已部署语义模型、已上线主动等时圈或已完成组合情景复算。

原方案的“当前基线”章节是实施前盘点；本文以现在的实际调用链判断状态。原方案新增的[实施状态说明](../../../docs/AI大模型融合方案与专家评审.md#2026-10-13-实施进展)已披露部分边界，但完整需求验收仍需要逐项核查。

状态定义：

- **已实现**：存在实际业务调用链和可供用户使用的输出；相关测试只能证明所覆盖契约，不自动证明真实效果。
- **部分实现**：已有接口、算法或展示，但缺少数据、适配器、治理操作或主流程接线，尚不能完成原方案定义的端到端行为。
- **未实现**：当前生产路由、持久化模型和界面中未找到相应能力链。
- **待实测**：实现或评估工具已经存在，真实账号、独立标签或现场效果尚不能由当前证据确认。
- **可选方法**：原方案条件允许时的备选技术，不因为没有使用指定算法就判为主线欠交付。

核查方法为读取原方案、生产源码、路由/持久化/UI调用链与已有测试。此轮没有调用收费地图/模型服务，没有重复运行全量测试，没有改变业务代码。

## 已经存在的 AI、地理与规划基础

以下能力不应列为“完全未实现”：

- 语义审核已有类别建议、实体候选、受约束 LLM 裁决、空间与父子实体保护、低置信度保留及失败降级；正式报告保持不变。
- GPR、阈值/风险优先选点、预算包含留出集、失败来源排除、样本去重、500 米空间块整体留出与 IDW 对照已经存在。
- 设施稀缺与步行可达已经分别统计；已确认步行超时网格可以按四邻接分组，保留孤立格与原网格几何。
- 最大覆盖已有数量与已知成本预算硬约束、小规模精确枚举、确定性贪心、重叠覆盖去重、真实路线覆盖核验及未知覆盖下界披露。
- 既有单设施情景支持 `before/after/delta` 和地图标记；既有 2–3 个方案比较是独立单设施比较。
- 人工网格基准工具、多源 POI 人工对齐评估工具已有，不能概括为“没有任何评估”。

## AI、空间计算与规划的主线缺口

| 编号 | 原方案要求 | 当前状态 | 已有能力与未完成部分 | 关键源码依据 |
|---|---|---|---|---|
| A1 | 实际嵌入模型辅助类别匹配、实体候选召回 | 部分实现 | 有 `EmbeddingProvider` 注入协议，但应用启动未创建/赋值实际嵌入提供方。类别候选仍是关键词规则，向量接口仅用于实体候选；配置 LLM 后可提出分类建议，但不能称已上线 Sentence-BERT/text2vec 或完成嵌入辅助类别匹配。 | [semantic_review.py](../../backend/app/analysis/semantic_review.py#L32)、[ai_extensions.py](../../backend/app/ai_extensions.py#L42)、[bootstrap.py](../../backend/app/bootstrap.py#L40) |
| A2 | 人工接纳/驳回/修正 → 版本化设施目录 → 后续正式计算 | 部分实现 | 能生成待审核建议；无审核决策操作、版本化设施目录及接纳后重算链。输入是已生成报告中的正式设施，不是保留全部原始多源记录的治理流水线。 | [ai_extensions.py](../../backend/app/ai_extensions.py#L34)、[semantic_review.py](../../backend/app/analysis/semantic_review.py#L343)、[ConversationExtensionResults.vue](../../frontend/src/components/ConversationExtensionResults.vue#L2) |
| A3 | 百度原生 `foot_fastest`/`foot_shortest` 探测与等时圈适配 | 未实现 | `MapProvider` 没有原生等时圈方法；`/api/map/probe` 仅测地理编码；正式等时圈仍用径向采样。权限、计费、几何契约及账号可用性未核验。 | [provider.py](../../backend/app/maps/provider.py#L80)、[main.py](../../backend/app/main.py#L198)、[service.py](../../backend/app/analysis/service.py#L475) |
| A4 | 模型按信息量分配真实 API 测量预算，迭代补测边界/障碍/候选点 | 部分实现 | 低层采样算法接受测量回调；应用入口只复用报告的中心到设施路线，没有真实新增补测。正式分析未接入 GPR 或主动策略；特征只有米制 x/y，应用没有传入障碍/入口高风险信息。 | [sampling.py](../../backend/app/analysis/sampling.py#L319)、[sampling.py](../../backend/app/analysis/sampling.py#L403)、[workspace_routes.py](../../backend/app/workspace_routes.py#L384)、[service.py](../../backend/app/analysis/service.py#L215) |
| A5 | API 观测边界、估计边界、未决带与独立预测图层 | 未实现 | 采样结果只展示误差与计数；没有时间场图层、观测/预测边界和未决带。正式径向算法只生成既有等时圈多边形。 | [ConversationExtensionResults.vue](../../frontend/src/components/ConversationExtensionResults.vue#L10)、[useMapRenderer.ts](../../frontend/src/composables/useMapRenderer.ts#L32)、[service.py](../../backend/app/analysis/service.py#L475) |
| A6 | 稀缺/超时/双条件缺口分别成片，限制跨障碍连接，再进入候选生成 | 部分实现 | 已有独立统计和步行超时四邻接组。仅稀缺但仍可达的网格不进入当前分组；生产不传 `blocked_edges`；候选模块另用旧四邻接，没有复用新分组；地图没有缺口片区图层。 | [gap_groups.py](../../backend/app/analysis/gap_groups.py#L11)、[service.py](../../backend/app/analysis/service.py#L375)、[recommendations.py](../../backend/app/analysis/recommendations.py#L65)、[ReportPanel.vue](../../frontend/src/components/ReportPanel.vue#L60) |
| A7 | 自然语言编译预算、指定地块、类别数量、人口/容量/土地等规划约束 | 部分实现 | 对话仅支持设施类别与一个整体数量上限；预算、用地、容量、必须/只能及分别数量明确拒绝。结构化 REST 已支持报告候选 ID、数量、已知成本与预算，但无人口/容量/土地约束模型。 | [workspace_routes.py](../../backend/app/workspace_routes.py#L99)、[ai_extensions.py](../../backend/app/ai_extensions.py#L15)、[coverage_optimizer.py](../../backend/app/analysis/coverage_optimizer.py#L14) |
| A8 | 用户限定候选地块，可信候选范围与可建设条件 | 部分实现 | 对话从报告候选按 ID 取前 16 个，无法指定“只考虑三个地块”。报告候选是重点盲区的代表网格中心，尚未核验地块、入口和建设可行性。 | [workspace_routes.py](../../backend/app/workspace_routes.py#L392)、[recommendations.py](../../backend/app/analysis/recommendations.py#L177)、[coverage_optimizer.py](../../backend/app/analysis/coverage_optimizer.py#L214) |
| A9 | 所选设施组合整体复算、帕累托权衡与地图方案联动 | 部分实现 | 已能求已确认重点盲区网格中心的覆盖并集；没有组合完整 `before/after/delta`、综合评分/服务区域复算，也没有多目标非支配前沿。旧比较只排名一个目标的独立单设施情景；组合结果界面仅显示 ID/数字，未落图。 | [coverage_optimizer.py](../../backend/app/analysis/coverage_optimizer.py#L201)、[simulations.py](../../backend/app/analysis/simulations.py#L20)、[planning_comparison.py](../../backend/app/planning_comparison.py#L14)、[ConversationExtensionResults.vue](../../frontend/src/components/ConversationExtensionResults.vue#L17) |
| A10 | 居民留言/图片 → 疑似关闭、入口变更、围挡观察 → 待复核事件闭环 | 未实现 | 未找到居民观察、图片上传/OCR、待复核事件、接纳/驳回路由或对应持久化与 UI；名称为 `feedback` 的导出提示不属于居民反馈。 | 当前 [迁移目录](../../backend/app/storage/migrations)、[workspace_routes.py](../../backend/app/workspace_routes.py)、[ConversationWorkspace.vue](../../frontend/src/components/ConversationWorkspace.vue)；见下文检索范围 |
| A11 | 独立验证、主动策略同预算/同误差对照、五组消融 | 部分实现 / 待实测 | 有基准工具与离线局部指标；缺多社区隔离、现场校准、径向/等预算均匀/规则加密策略比较、边界误差、真实路线对数节省和时延对照；未找到五组消融 runner/config/results。真实嵌入/LLM 的类别及错误合并收益未验证。 | [sampling.py](../../backend/app/analysis/sampling.py#L314)、[sampling.py](../../backend/app/analysis/sampling.py#L464)、[evaluate_benchmark.py](../../backend/scripts/evaluate_benchmark.py#L40)、[v2.1-benchmark-evaluation.md](../validation/v2.1-benchmark-evaluation.md#L71) |

### A1–A2：语义建议存在，设施治理闭环仍未完成

`semantic_review.py` 的类别建议由名称与 `provider_category` 关键词规则生成；如果注入 `embedder` 才计算向量实体候选。当前启动函数初始化地图、数据库、会话仓库、步行缓存和 LLM，没有嵌入适配器创建逻辑。生产检索 `semantic_embedder|EmbeddingProvider|embedder=` 只命中协议、参数和状态读取；嵌入测试使用 `FakeEmbedder`，不是实际模型精度证据。

LLM 可以裁决类别和实体关系，但所有输出保留 `pending_human_review` 与 `apply_policy=human_review_only`。前端展示建议清单，没有接纳、驳回、修正或复核记录入口。数据库迁移仅涉及任务/报告、路线缓存、解释和对话工作区，未包含审核决定与版本化设施目录。正式分析仍调用确定性 `normalize_facilities`；高德核验也是独立旁路。因此当前语义建议无法改善后续正式统计，不能宣称“AI 清洗已提高覆盖率准确性”。

对应测试已经检查类别与身份分开、同品牌异店/科室/入口保护、非法模型批次整批拒绝、低置信不修改记录及超时降级。这些是必要的正确性基础，不能替代有独立人工标签的真实模型评估。参见 [test_semantic_review.py](../../backend/tests/test_semantic_review.py#L37)。

### A3–A5、A11：离线 GPR 实验不是主动等时圈上线

`run_sampling_experiment` 已支持风险、阈值跨越、不确定性与预算控制；实际业务包装 `evaluate_report_sampling` 明确不访问地图。其输入是报告舍入到 0.1 分钟的中心到设施路线，实验包装未读取原始秒级标签，按同坐标去重并排除冲突，以一个 500 米空间块作留出。返回 `external_route_pairs_used=0`、`enabled_for_official_analysis=False`、`evaluation_strength=exploratory_single_spatial_block`。

当前唯一 IDW 基线与 GPR 使用相同的主动选定训练点，所以只能比较插值器，不足以比较“主动采样 vs 均匀/径向/规则加密”的整体策略。样本只分布于既有设施位置，不能据此证明等时圈边界更准、障碍两侧更可靠或地图配额减少。模型标准差也尚未获得独立现场误差校准。

正式等时圈继续采用 16/24 方向、最高 1,250 米和二分细化后拼接一个多边形的路径；并未输出学习时间场、预测边界或未决带。原生接口的权限探测、adapter 与返回几何契约也没有接入。仅 `/api/map/probe` 成功无法推导原生等时圈可用，因为此路由只调用 `geocode`。

对应测试已覆盖预算和留出不泄漏、失败来源排除、缓存基础来源验证、合法同点零值、冲突去重与标签精度披露，参见 [test_sampling.py](../../backend/tests/test_sampling.py#L34)。下一步应验证真实采样链与独立基线，而不是把更多模型名称当作完成标准。

### A6：缺口分组还有主流程断点

当前 `build_gap_groups` 只接纳成功分类且确认步行超时、无失败路线、非预测来源的网格。四邻接组保留原网格 `MultiPolygon`，未知洞和孤立缺口不会被凸包填平，但这仍不是河流/铁路/围墙限制下的连通片区。

`blocked_edges` 参数及单元测试已经存在，正式调用却是 `build_gap_groups(zones)`，没有障碍或已核验步行邻接数据。候选生成继续调用自己的 `_connected_clusters`，未消费新缺口组；候选点是组内代表格中心。还缺三种缺口分别成组、最不利时间/缺失比例等完整元数据、受障碍限制的候选范围及地图片区展示。参见 [test_gap_groups.py](../../backend/tests/test_gap_groups.py#L24) 与 [recommendations.py](../../backend/app/analysis/recommendations.py#L149)。

### A7–A9：最大覆盖基础成立，但不等于完整规划优化

当前求解器在给定候选和已确认覆盖集合内支持数量/预算约束，精确枚举不超过十万组合时返回 `OPTIMAL`，否则使用确定性贪心返回 `FEASIBLE`。覆盖取并集，避免同一网格被重复计入。已有随机小实例与独立穷举 oracle 的测试，参见 [test_coverage_optimizer.py](../../backend/tests/test_coverage_optimizer.py#L39)。

剩余缺口主要是使用链和领域约束：对话无法将真实预算、限定地块和分别数量编译成结构化约束；人口、容量和土地可行性没有字段与数据接入；候选范围只是报告网格中心，路线核验对象也只限原有 `critical` 网格中心。未知路线只形成确认覆盖下界。

组合求解返回选点集合与覆盖数量，没有调用单设施复算服务产生组合整体评分、服务区域及改善量。既有单设施模拟有 `before/after/delta`，既有 2–3 方案比较明确为独立新增一处设施，不能相加为组合收益。当前优化目标为覆盖优先、已知成本次优、数量/ID 打破平局，不是帕累托前沿。前端组合卡片未提供所选设施地图定位、整体情景按钮或多目标方案比较。

## 现有评估与仍缺的证据

已有网格基准模型能生成不携带系统预测的人工标注模板，提供混淆矩阵、精确率/召回率/F1 与未知统计；CLI 能对比报告与基准。多源 POI 脚本已有人工标签、许可、样本量和复核时间门禁。这些工具可以复用，但尚不是新嵌入/LLM、主动测量和完整系统消融的验收结果。

现有海韵东路基准仍为 `draft`；沙涌长盛花园有 64 条百度地图同源人工复核。项目文档已经明确：100% 同源一致仅证明相同数据源/规则下的结果一致，不是跨来源准确率或现场泛化成绩。参见 [基准进度](../validation/v2.1-benchmark-evaluation.md#L67) 和 [多源评估工具](../../backend/scripts/evaluate_multisource_poi.py#L34)。

上轮实施说明记录的后端 366 个、前端 136 个测试通过以及类型/静态检查/构建通过，是已有实现路径的回归结果。固定拦截数据的浏览器检查不代表真实端到端验证，也不证明融合方案已全部验收。参见 [上轮验证说明](../validation/ai-first-implementation-2026-10-13.md#L68)。本次核查没有重新执行这些测试或任何收费调用。

仍需专项证据：真实语义分类准确率、错误/漏合并率和复核工作量；跨社区与障碍两侧采样误判/未决/边界误差；同预算或同错误水平的路线对数/时延比较；组合复算一致性和硬约束违规数；“无模型、仅对话、语义审核、主动采样、完整系统”消融。

## 可选方法与条件能力

以下项目没有实现，但不应作为近期主线全部未完成的证据：

- **GNN、强化学习**：原方案明确需完整有许可步行路网或稳定训练环境，当前不列近期主线。
- **随机森林/XGBoost/MLP、克里金**：是数据充足或对照需求明确后的候选；先证明当前轻量回归有收益。
- **DBSCAN/KMeans**：原方案允许 4×4 网格优先用四邻接；缺 DBSCAN 本身不是缺口，缺三种分组口径与障碍接线才是。
- **CP-SAT/MIP、遗传算法/模拟退火**：小规模精确枚举已符合当前最大覆盖基础需求；更复杂约束或规模出现后再选求解方法。
- **人口/容量/土地数据**：能力还未实现，但缺实际授权与可信输入时只能披露空间覆盖。不要为了补功能虚构数据或受益人数。

## 建议补齐顺序（本次不实施）

1. 先补用户可见的主流程断点：独立稀缺/超时/重点缺口图层和分组落图、对话覆盖范围、统一恢复与账本口径（具体证据见下节 B1–B6）。
2. 完成一个真正的 AI 治理闭环：实际嵌入提供方、全量原始候选保留、人工决策、版本化设施目录及接纳后重算，同时收集独立标签。
3. 探测/集成原生等时圈，接通真实 API 主动补测；分别展示观测、估计和未决区域，完成多社区与同预算基线评估后再决定默认启用。
4. 接通自然语言结构化候选/成本/数量约束、组合整体复算、地图方案展示及帕累托；人口/容量/土地只在有合格数据时扩展。
5. 增加居民反馈待复核闭环与五组消融，统一形成可审计的功能验收和效果报告。

## 负向检索边界

“未实现”结论来自当前工作区的生产能力核查，不是仅凭文件名推断。已检索 `backend/app`、`backend/scripts`、`frontend/src` 中 `foot_fastest|foot_shortest`、`semantic_embedder|EmbeddingProvider|embedder=`、`feedback|upload|resident|ablation|OCR|observation|accept|reject`，并读取路由、迁移、算法调用和相关 UI。采样中的 `observations` 是路线测量记录；导出菜单中的 `feedback` 是下载提示，均不构成居民观察事件能力。

## 对话、事实出口、恢复和账本的补充核查

事实槽位门禁、报告范围校验、持久会话、修订冲突、幂等、执行确认、后台进度、按钮取消和显式重试已经存在。百度矩阵 50 路线对分块、非同点零值未知、POI 分页/截断、来源与导航入口聚合也已实现，不能继续沿用原方案实施前的描述将这些判为缺失。依据：[workspace_routes.py](../../backend/app/workspace_routes.py#L50)、[llm.py](../../backend/app/llm.py#L192)、[实施记录](../validation/ai-first-implementation-2026-10-13.md#L19)。

| 编号 | 能力 | 当前状态 | 具体缺口与依据 |
|---|---|---|---|
| B1 | 大部分操作可直接通过多轮对话完成 | 部分实现 | 地址可解析后填表，但候选选择仍靠位置界面；历史列表可对话查询，打开记录仍靠按钮；取消/重试有按钮及 API，却没有对应对话命令。分析期间输入框禁用，无法直接说“取消体检”。空间定位需要明确网格 ID，未实现“东南角”等空间指代。见 [Command](../../backend/app/workspace_routes.py#L28)、[历史与网格处理](../../backend/app/workspace_routes.py#L336)、[前端按钮和输入限制](../../frontend/src/components/ConversationWorkspace.vue#L18)、[地址候选处理](../../frontend/src/App.vue#L556)。 |
| B2 | 统一工具注册与多步骤编排 | 部分实现 | 当前工作台使用正则/有限命令分类及条件分支，复用既有规划工具；未把定位、设施查询、路线测量、等时圈、网格检查、模拟和比较全部收敛为方案中的统一工具注册体系。分类模型输入只有本条消息与是否有报告，规划分支可复用上一轮规划结果，但这不是完整历史对话的统一任务编排与约束澄清。见 [命令分类](../../backend/app/workspace_routes.py#L120)、[规划上一轮上下文](../../backend/app/workspace_routes.py#L417)。 |
| B3 | 独立稀缺/步行超时/重点盲区图层及共享图层状态 | 部分实现 | 后端已拆分统计，前端显示统计；地图仍按既有 `normal/sparse/critical/unknown` 综合分类过滤，未按 `nearby_scarcity` 与 `walking_reachable` 独立绘制。对话仅切换设施类别，不能独立切换上述状态或新缺口片区；工作区也未保存这些状态开关。见 [MapLayerControls.vue](../../frontend/src/components/MapLayerControls.vue#L29)、[地图过滤](../../frontend/src/composables/useMapRenderer.ts#L275)、[共享状态](../../frontend/src/App.vue#L405)、[声明式动作](../../frontend/src/types/workspace.ts#L28)。 |
| B4 | 规范检索、角色化报告与分层解释 | 部分实现 | 有经过事实槽位验证的解读及已有报告导出，但模型上下文只有既有事实、建议与有限不确定性选项；未接规范文档检索、居民/社区工作人员/规划师受众参数及相应报告流程。不能把现有解读称为完成该项。见 [解读上下文](../../backend/app/llm.py#L192)、[解读入口](../../backend/app/main.py#L544)。 |
| B5 | 全入口统一质量、成本与版本账本 | 部分实现 | 已有数据质量事件、逻辑/实际路线对数及模型 HTTP 尝试上限；已有模型名和提示词版本存储。尚无实际 token 用量、货币估价及结算记录、全入口统一预算，以及模型/地图/规则/工具 schema 版本的完整追踪。旧独立解读/规划 API、地点和设施检索仍未纳入新增共享总预算。见 [预算边界](../validation/ai-first-implementation-2026-10-13.md#L52)、[模型响应与计数](../../backend/app/llm.py#L103)、[旧规划入口](../../backend/app/main.py#L520)、[提示词版本存储](../../backend/app/storage/repositories.py#L288)。 |
| B6 | 中断任务恢复与续算 | 部分实现 | 浏览器能恢复保存状态并继续跟踪正在运行的任务；服务重启后将中断任务/轮次标为失败，显式重试创建新任务。没有检查点恢复或跨进程断点续算；这不等于“没有恢复”，但也不能称已支持断点续跑。见 [bootstrap.py](../../backend/app/bootstrap.py#L54)、[workspaces.py](../../backend/app/storage/workspaces.py#L148)、[前端恢复](../../frontend/src/App.vue#L429)、[重试说明](../validation/ai-first-implementation-2026-10-13.md#L10)。 |

### 本次离线命令解析复现

在后端虚拟环境直接执行 `select_command(message, state, None)`，设置 `state={"report_id":"audit-report","visible_categories":[]}`。此验证只执行规则分类，没有创建工作区、执行地图动作、修改报告或调用地图/模型服务。

| 输入 | 实际解析结果 | 表明的缺口 |
|---|---|---|
| 取消体检 | `interpret` | 没有取消对话命令；按钮取消能力仍存在。 |
| 重试刚才失败的任务 | `interpret` | 没有失败任务重试对话命令。 |
| 打开刚才第二份报告 | `interpret` | 没有历史序号指代及打开报告命令。 |
| 定位到东南角 | `focus`，没有 `grid_id` | 方向指代未解析；正式执行还会要求提供网格标识或点击地图。 |
| 只看1公里设施稀缺图层 | `layers`，`categories=[]` | 被当成设施类别图层命令，没有识别独立稀缺图层。 |
| 覆盖优化，预算10万元，最多3家药店 | 抛出明确的“不支持此约束”错误 | 不会忽略预算执行，但自然语言预算规划尚未接通。 |

此表复现的是规则模式；配置模型后可以改善意图分类，但仍受同一有限命令结构与执行分支限制，不能因此获得尚未实现的取消、重试、报告选择或独立状态图层能力。来源：[select_command](../../backend/app/workspace_routes.py#L120)、[_coverage_command](../../backend/app/workspace_routes.py#L99)。

### 分阶段验收结论

- **P0 部分完成**：事实门禁、地图契约和持久会话已落地；统一工具入口、对话操作覆盖和独立稀缺图层尚未完成。
- **P1 部分完成**：有语义审核与采样实验、步行缺口分组；实际嵌入及治理闭环、真实主动测量、完整空间评估和统一成本账本尚未完成。
- **P2 部分完成**：有有限候选最大覆盖求解；复杂约束编译、组合整体复算、帕累托及居民反馈复核尚未完成。

人口/容量/土地、障碍、现场入口及账号权限同时受可信数据和授权条件制约；这些既需要接入实现，也需要外部核验。模型预测默认未进入正式评分符合原方案的正确性门禁，不能通过直接把实验结果接入评分来消除上述缺口。是否启用主动策略应由独立评估决定，评分口径变化还需遵循现有 ADR。
