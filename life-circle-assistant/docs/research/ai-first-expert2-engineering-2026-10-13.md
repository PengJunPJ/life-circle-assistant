# 专家2：从现有代码演进为 AI 对话工作台

日期：2026-10-13

角色：高级软件开发工程师

## 0. 阅读边界与结论先行

本报告把随附赛题 PDF 当作交付与评分约束，把用户本轮要求当作产品方向：PDF 要求基于百度地图能力完成真实步行等时圈、设施覆盖/服务盲区、可视化报告、API 策略、容错与开源交付；用户要求在不牺牲地理正确性的前提下最大化使用大模型，并把对话作为主要入口。两者不是同一类指令：大模型不能替代 PDF 要求的真实地图计算，也不能把“会聊天”当成计算正确性证明。

工程结论：保留确定性空间计算作为事实内核，让 AI 负责“理解意图、选择受控工具、解释证据、提出可验证假设、引导下一步”。项目已经有自然语言填参、报告解读和规划工具链，当前最急的不是再加一个聊天框，而是把已有出口收敛到同一份任务状态和同一套可验证事实契约。否则用户从“一句话体检”、快捷解读、规划助手三个入口得到的答案可能使用不同状态、不同校验强度和不同费用路径。

## 1. 赛题映射与当前能力盘点

### 1.1 赛题硬约束

赛题明确要求稳定调用百度地图地理编码/逆地理编码、POI 检索、路径规划或距离计算，使用真实路网生成 15 分钟步行等时圈，统计民生设施并识别周边 1 公里服务盲区；同时要求 API 调用策略、等时圈算法、POI 清洗、盲区算法、真实社区对比测试、可部署源码和自动化测试。依据：随附 PDF 第 1--2 页；仓库对该 PDF 的逐项基线记录见 [`contest-official-requirements-2026.md`](contest-official-requirements-2026.md) 第 68--95、114--148 行。

AI 方案必须因此遵守三个边界：

1. 模型不能生成坐标、POI 或路线事实；地图服务和确定性算法必须产生这些事实。
2. “未检索到”“路线失败”“缓存过期”只能进入未知/部分结果，不能由模型改写成“没有设施”或“不可达”。现有分类器已经遵守这一点（[`service_areas.py`](../backend/app/analysis/service_areas.py):40-67）。
3. 任何演示快照、插值和降级估算都要显式披露，不能冒充最新真实测算；项目上下文和报告质量契约已有此要求（[`CONTEXT.md`](../../CONTEXT.md):39-67；[`reports.py`](../backend/app/contracts/reports.py):34-53）。

### 1.2 现有、部分具备、需要新增

| 能力 | 代码证据 | 判断 | 工程含义 |
|---|---|---|---|
| 一句话解析地址、当前点、10/15/20 分钟、设施类别 | [`analysis_intent.py`](../backend/app/analysis_intent.py):120-170；[`schemas.py`](../backend/app/schemas.py):64-84 | 已有 | 保留规则兜底；地址必须逐字来自本轮输入，模型不能补坐标；不再另做一套参数解析。 |
| 共享参数填充与用户确认启动体检 | [`NaturalLanguageAnalysis.vue`](../../frontend/src/components/NaturalLanguageAnalysis.vue):1-49；[`App.vue`](../../frontend/src/App.vue):431-454 | 已有但不是连续对话 | 当前是“一句话填写”，公共表单仍是事实来源，没有消息时间线、草稿版本或可恢复会话。 |
| 报告摘要、盲区说明、快捷解读 | [`ai_assistant.py`](../backend/app/ai_assistant.py):106-140；[`main.py`](../backend/app/main.py):492-525 | 已有，校验不完整 | 证据 ID 会过滤，但旧链没有把摘要中的数值绑定到证据指标，不能称为可靠防幻觉。 |
| 工具调用规划助手 | [`planning_assistant.py`](../backend/app/planning_assistant.py):25-113、137-177、534-581 | 已有且较严格 | 五个白名单工具、严格 Pydantic 参数、当前报告/黄埔区/2 公里校验、工具次数和轮次上限；应作为统一命令注册表的首批实现。 |
| 规划助手的模拟与比较 | [`planning_assistant.py`](../backend/app/planning_assistant.py):350-455；[`simulations.py`](../backend/app/analysis/simulations.py):125-177 | 已有但执行层不统一 | 模拟深拷贝原报告并输出 before/after/delta；直接调用 `provider.walking_matrix`，尚未完全复用主分析的 WalkingService 缓存/预算包装。 |
| 体检异步任务和进度 | [`main.py`](../backend/app/main.py):357-385；[`repositories.py`](../backend/app/storage/repositories.py):19-110 | 部分具备 | FastAPI BackgroundTasks、SQLite 状态和轮询存在；没有 HTTP 幂等键、可取消任务、事件日志或跨进程租约。重启把 queued/running 标记 failed，而不是续算。 |
| 地图限流、路线缓存、数据质量来源 | [`baidu.py`](../backend/app/baidu.py):29-46、102-117；[`walking_cache.py`](../backend/app/storage/walking_cache.py):20-62；[`provider.py`](../backend/app/maps/provider.py):27-76 | 部分具备 | 有进程内 QPS、有限重试和方向坐标缓存；缓存种子会在启动时重盖 TTL（[`walking_cache_seed.py`](../backend/app/storage/walking_cache_seed.py):1-10、43-82），不能把 TTL 当作原始测量时间。 |
| 模型 JSON/工具传输 | [`llm.py`](../backend/app/llm.py):85-134 | 部分具备 | 发送 `response_format`、工具和 `parallel_tool_calls=false`，但 `LLMProvider` 没有 capability registry；兼容地址不代表具备相同协议能力。 |
| 前端响应类型校验 | [`analysisApi.ts`](../../frontend/src/services/analysisApi.ts):20-27 | 部分具备 | TypeScript 主要是 `payload as T`，运行时未验证服务端响应；统一工具契约后要增加 runtime schema 校验。 |
| 连续对话作为全系统入口 | [`AiPlanningAssistant.vue`](../../frontend/src/components/AiPlanningAssistant.vue):58-123；[`main.py`](../backend/app/main.py):468-490、492-535 | 需要新增 | 规划助手保存上一轮 ID，但快捷解读仍走另一 endpoint，且切换报告只清理局部状态；需要统一 ConversationService。 |

### 1.3 已确认的最高风险：旧解读可接受虚构数值

规划工具回答会拒绝摘要中的数字并要求改成定性表达（[`planning_assistant.py`](../backend/app/planning_assistant.py):534-581）。但旧的 `enhance_interpretation` 仅校验摘要非空、长度和证据 ID，随后由 `_filter_hallucinated_content` 过滤无效引用；后者并没有解析“分数、分钟、米”等数值是否由引用支持（[`llm.py`](../backend/app/llm.py):222-265；[`ai_assistant.py`](../backend/app/ai_assistant.py):106-140）。

已用完全离线 FakeProvider 复现：报告真实总分为 68，模型返回“报告总分99，药店步行1分钟”，带有该报告合法 ID；结果仍以 `llm_structured` 返回，摘要保留 99 和 1 分钟。该复现没有调用网络、地图或收费模型，说明“引用存在”不等于“引用支持该语义”。这是 P0 缺陷：在所有 AI 出口统一事实契约之前，不能对外宣称已实现可靠防幻觉。

## 2. 目标形态：统一对话工作台，而不是多套 AI 页面

### 2.1 目标闭环

```text
用户文字 / 地图点击 / 表单修改
              |
      ConversationService
  (意图 + 当前工作区 revision)
              |
       CommandRegistry
  (类型、权限、预算、前置条件)
              |
   Deterministic Domain Services
 (地图、POI、步行、盲区、模拟、比较)
              |
      Evidence/Fact Store
 (来源、时间、版本、未知原因)
              |
     Answer Renderer + UI State
 (事实数字服务端填充，AI只组织语言)
```

对话可覆盖：选择地址/“这里”、启动体检、解释网格或类别、询问为何是稀疏区、查看路线、切换图层、比较历史报告、提出设施情景模拟、导出报告、查询字段含义和数据质量。每一步仍执行现有服务端校验。模型只产生结构化 `Intent` 或 `Command`，不直接执行 Python、SQL、HTTP、shell、地图写操作。

### 2.2 WorkspaceState：一次状态，多个入口

服务端保存可序列化工作区，建议最小字段如下：

```json
{
  "conversation_id": "...",
  "revision": 12,
  "center": {"lng": 113.5, "lat": 23.1, "address": "...", "source": "user_selected"},
  "minutes": 15,
  "categories": ["market", "pharmacy"],
  "mode": "analysis",
  "active_report_id": "...",
  "active_job_id": "...",
  "selected_grid_id": "...",
  "selected_map_point": null,
  "scenario_ids": [],
  "layers": {"isochrone": true, "service_areas": true},
  "report_schema_version": "2.0"
}
```

地图点击、表单编辑、AI patch 都写成带 `base_revision` 的事件。服务端以当前 revision 决定是否接受；陈旧 patch 只能返回冲突并要求重新确认，不能静默覆盖用户刚在地图上选的点。“这里”绑定用户确认时的 `selected_map_point` 或 `center` 对象，不绑定会随缩放变化的视口中心。已生成的计划还要绑定报告 ID、报告 schema/rules 版本和 workspace revision；只要中心点、分钟数、类别或报告发生变化，原确认自动失效。

一次“开始体检”先返回参数、预计地图/模型调用档位和预算预览；只在需要外部收费计算或改变状态时请求确认。解释、切图层、查看已有证据和规则帮助可以直接执行。模拟中的地图点必须再次通过黄埔区和当前中心 2 公里限制；报告中的候选点是建议对象，不等于土地合法性、可建设性或最终选址许可。

### 2.3 会话与历史

`conversation_id`、`turn_id`、`workspace_revision`、`report_id`、`job_id`、`prompt_version` 和 `tool_trace` 写入 SQLite。前端显示完整消息列表而不是只显示最新回答；刷新页面时恢复会话和任务，切换报告时以服务端 report scope 重新加载。当前 `AiPlanningAssistant.vue` 只保留最新 `result`，并通过 `AbortController` 丢弃过期返回（:68-111），这可作为竞态保护，但 abort 客户端请求不等于后端已取消收费调用，需在 JobService 中补上显式取消语义。

## 3. 事实契约：让 AI 引用指标，而不是编数字

### 3.1 统一 Evidence/Fact 对象

所有报告、工具和解读统一使用版本化事实对象，示意：

```json
{
  "fact_id": "report:r1/summary.score",
  "report_id": "r1",
  "schema_version": "2.0",
  "rules_version": "blind-area-v3",
  "object": {"type": "report", "id": "r1"},
  "metric": {"name": "overall_score", "value": 68, "unit": "score"},
  "observed_at": "2026-10-13T08:00:00Z",
  "cached_at": null,
  "source": {"kind": "real_api", "provider": "baidu-web-service", "method": "..."},
  "status": "observed",
  "unknown_reason": null
}
```

还要区分 `observed_at`（地图返回或人工采集时间）、`imported_at`（种子导入时间）、`cached_at`、`expires_at` 和 `report_generated_at`。当前步行缓存只有 `created_at/expires_at` 和 `underlying_source`（[`walking_cache.py`](../backend/app/storage/walking_cache.py):44-60），而种子导入会使用启动时刻重盖 TTL；因此在补齐字段前，AI 不得回答“今天道路状态”。

### 3.2 模型输出格式

模型输出限制为：

```json
{
  "claims": [
    {"text_template": "该类别覆盖表现为 {{fact:report:r1/category.market.score}}。",
     "fact_refs": ["report:r1/category.market.score"],
     "kind": "observation|hypothesis|action"}
  ],
  "next_action": {"command": "show_grid", "arguments": {"grid_id": "g-1"}},
  "needs_clarification": false
}
```

服务端必须验证 fact ID、对象范围、指标类型、单位和 report/revision；渲染器从 Fact Store 插值数字、分钟和路线，不接受模型把数字拼进最终事实句。定性结论也要绑定事实或标为 `hypothesis`，因果词（“因为围墙导致”）没有路线/障碍证据时改为“可能原因，需核验”。无效引用、越权 report、未知事实、数字注入全部降级为确定性模板或澄清问题。

这套契约同时覆盖旧 `/ai/interpret` 和新 `/ai/plan`，然后再逐步合并 endpoint；不能只修规划助手而让快捷“体检摘要/汇报摘要”绕过校验。响应 schema 用 Pydantic 生成 OpenAPI/JSON Schema，前端生成类型并执行运行时验证，替代单纯的 `payload as T`。

### 3.3 “未知”是第一类结果

设施检索失败、候选为空、路线全部失败时，现有分类器返回 `unknown/calculation_incomplete`（[`service_areas.py`](../backend/app/analysis/service_areas.py):45-67）。工具和回答必须保留该状态：不能说“周边没有设施”，应说“当前检索或路线证据不足，无法判断”。`partial` 报告不能进入“全球最优”排名；跨报告比较要同时展示数据来源、时间和规则版本。

## 4. CommandRegistry 与能力矩阵

先把现有 endpoint 包装为受控命令，不让每个页面自行拼请求：

| 命令 | 读/写 | 前置条件 | 结果 |
|---|---|---|---|
| `resolve_location` | 读外部地图 | 地址文本或明确地图点 | 候选卡；模型不能选择未展示的坐标 |
| `prepare_analysis` | 读/预估 | center、minutes、categories 完整 | 参数 diff、预算和待确认项 |
| `start_analysis` | 付费计算/写 job | 用户确认、revision 最新 | `job_id`，异步进度和最终 report |
| `explain_report/grid` | 只读 | 当前 report/grid | Fact 引用和图层动作 |
| `simulate_facility` | 付费计算/写 scenario | 合法 candidate 或用户地图点 | 独立 scenario，不改原报告 |
| `compare_options` | 付费计算/写 scenarios | 同一原报告、2--3 方案 | 同口径 before/after/delta；缺数据排除排名 |
| `show_layer/export_report` | 显示/导出 | report 存在 | 前端动作或受控文件导出 |

每个命令声明 `read_only`、`display_only`、`paid_compute`、`side_effect`、输入/输出 schema、超时、预算、可取消性和允许的数据范围。`PlanningTools.execute` 已有白名单、类别校验、报告 scope 和 trace（[`planning_assistant.py`](../backend/app/planning_assistant.py):137-177），把它提升为全局注册表即可复用，而不是复制规则。

模型供应商还应在部署时登记 capability：`json_object`、严格 schema、native tools、parallel 禁用、视觉输入、最大上下文、取消支持、usage/cost 返回、区域和模型版本。当前 adapter 发送 JSON/tool 参数（[`llm.py`](../backend/app/llm.py):85-113），但 `LLMProvider` Protocol 只显式声明 `generate/close`（:27-32），规划代码依赖 `getattr(generate_tools)`；要用离线小样本验收每项能力，unsupported 不得反复重试收费。

## 5. JobService：可恢复、可取消、可计费

### 5.1 推荐状态机

```text
draft -> awaiting_location -> ready -> queued -> running
                                      |           |
                                      |           +--> cancel_requested -> cancelled
                                      |           +--> succeeded
                                      |           +--> partial
                                      |           +--> failed (可重试/不可重试)
```

先用 SQLite 事务和单进程受控执行器，避免赛前为了架构形式引入 Celery/Postgres。每个 job 记录：客户端 `idempotency_key`、规范化请求哈希、workspace/report/rules 版本、阶段、事件序号、租约、取消标志、预算预占/实际消耗、外部请求 ID、输出 report/scenario ID。SSE 可以作为增量事件通道，保留现有轮询作为降级。

当前 `TaskRepository.create` 每次生成随机 UUID（[`repositories.py`](../backend/app/storage/repositories.py):23-37），重复点击会重复计算；`recover_interrupted` 会把所有 queued/running 标为失败（:96-110），多进程启动时还可能误判其他实例任务。改造为：同一 owner、规范化请求哈希和有效窗口内的幂等键直接返回原 job；重启只回收租约过期任务，能够从已持久化 event/checkpoint 继续，无法恢复的外部请求标记“结果未知”并停止重试。扩容前先设计 worker lease，不要让多个进程同时抢同一 job。

### 5.2 取消和费用

客户端断开、`AbortController.abort()` 只表示不再等待响应，后端必须接收 `cancel_requested` 并在工具边界停止新请求；已发出的百度/模型请求可能无法撤销，账本要保留“已发送、成功、失败、未知”而不是承诺退款。模型目前有并发信号量、超时、最大 token 和有限重试（[`llm.py`](../backend/app/llm.py):56-60、74-83、100-134），但没有输入 token、实际 usage、租户预算或跨实例费用账本。5 个逻辑模型轮也不等于 5 次 HTTP 请求，每轮仍可能重试，因此预算要按请求/工具预占与实际消耗结算。

百度客户端的 QPS 节流是进程内共享发送节奏（[`baidu.py`](../backend/app/baidu.py):102-117），不等于多实例或多用户配额。步行批量常量 `BATCH_PAIR_LIMIT=100` 位于 [`maps/baidu.py`](../backend/app/maps/baidu.py):74、214；它是本地实现参数，必须在部署前按当前百度账号、接口版本、计费和矩阵对数限制重新验收，不能把历史常量当作官方配额。矩阵返回的零距离/零时长、非同点失败和批量分块要加入契约测试，避免被误判为成功路线。

## 6. AI 深度参与传统地理计算难题的可实施路径

### 6.1 语义设施分类与多源疑似匹配

模型适合从 POI 名称、地址、营业描述和政策文本给出候选类别、同义词、`quoted_evidence` 和置信度；不适合直接改坐标或新增 POI。流水线应为：

1. 原始结果保留 provider、原名、地址、坐标、抓取时间。
2. 模型仅输出 `candidate_label`、证据短引、置信度和“不确定原因”。
3. 规则校验类别枚举、坐标区域、重复/距离阈值和敏感词；冲突保留双方标签。
4. 低置信度进入待复核图层，不参与正式评分，人工修正形成带版本的标签集。

项目已有规则清洗以及可选高德只读核验：启动配置 `AMAP_VALIDATION_ENABLED` 后构造辅助校验器，结果声明 `affects_primary_analysis=false`（[`bootstrap.py`](../backend/app/bootstrap.py):45-61；[`validation/amap_facility.py`](../backend/app/validation/amap_facility.py):103-131；[`analysis/service.py`](../backend/app/analysis/service.py):144-150）。不能把该可选观察源宣传成已完成的双源主分析，也不能把模型标签当作独立数据源。

### 6.2 自适应采样：模型提假设，算法选点

赛题鼓励在没有底层路网时用 API 测时结果做空间插值/扇形采样。模型可根据历史网格、失败原因、设施缺口和道路障碍文本提出“哪里不确定、应验证什么”的假设；确定性主动学习/空间优化器再根据不确定度、空间覆盖、预算和 API 限额选择下一批采样点，最后由百度路线结果回填。必须和当前固定 4×4 网格基线（[`contest/algorithm-overview.md`](../contest/algorithm-overview.md):28）对比：误差、真实请求数、缓存命中率、最差区域遗漏率。

模型不能说“该点一定可达”或“该方案最优”。“最优”由固定目标函数和约束求解器计算，例如减少重点盲区、增加覆盖面积、改善指数三种目标的 Pareto 候选，再由用户选择权重。每个推断同时展示测量事实、插值/估计标记和待验证项。

### 6.3 居民反馈与障碍知识层

用户可用自然语言描述“围挡、天桥关闭、无障碍绕行”等。模型做实体/时间/位置抽取，生成 `reported_obstacle` 待核验对象；它不能修改真实路网和正式评分。经人工确认或地图 API 复核后，才可作为情景模拟约束。照片/文本的原始敏感信息按最小化原则进入短期隔离存储，报告只保留脱敏证据摘要。

### 6.4 知识问答与计算问答分流

“为什么这个网格是重点盲区”走 Fact Store；“上海导则要求什么”走带来源、发布日期和适用区域的知识检索；“如果增加药店会怎样”走模拟工具。三类回答在 UI 上明确标记 `report_fact`、`policy_reference`、`scenario_estimate`，避免把政策文本、实时地图事实和假设结果混成一个语气相同的答案。任何知识检索结果不能直接成为执行代码或设施数据。

## 7. 分阶段落地优先级

### P0：赛前必须做的正确性闭环

- 把旧 `/ai/interpret` 和规划助手都接入统一 Fact/Evidence validator；数字必须由服务端事实 renderer 填入。补齐“合法引用但语义不支持”的回归测试。
- 统一所有 AI 请求的强类型 payload：消息长度、report scope、grid/scenario ID、`base_revision`；拒绝当前 `dict[str,str]` 的宽松解读入口（[`main.py`](../backend/app/main.py):492-505）。
- 将已有自然语言填参、报告快捷解读、规划工具挂到一个 ConversationService 外壳，保留原 endpoint 兼容期；前端形成消息列表并展示事实来源/未知状态。
- 统一模拟路径的 WalkingService、缓存、QPS、失败分类和费用账本；检查步行矩阵零值、批量对数和坐标范围。
- 离线 FakeProvider/MockMapProvider 完成数字注入、越权 report、陈旧 revision、重复请求、取消、部分结果不排名、模型不支持工具等契约测试。

### P1：可恢复的工作台

- SQLite job/event/checkpoint、幂等键、取消标志、租约恢复、SSE/轮询双通道、刷新恢复。
- 只读 `show_grid`、`show_route`、`compare_reports`、`export_report` 命令和统一工具 trace；新增轻量会话 token、资源 owner、RPS/日预算。MVP 当前无登录/权限，CORS 不是认证，依据 [`main.py`](../backend/app/main.py):115 及项目 ADR 0005。
- 部署时对候选模型执行 JSON/tool/schema/usage capability matrix；unsupported 走规则模板或低能力适配器，不靠失败重试。
- 知识问答附来源日期和区域；用户地址、路线和反馈提供最小化保留/删除策略。

### P2：AI 参与数据质量和规划优化

- 语义 POI 分类、多源疑似匹配和人工复核闭环。
- 主动采样 benchmark 与固定网格基线对比；实测不达标就回退固定采样。
- 约束优化、多目标候选、障碍情景层和历史报告趋势。

这里的周期是优先级，不是承诺在 2026-10-16 截止前完成全部 P1/P2；提交材料必须把已实现、可演示、路线图三栏分开。赛题要求的真实社区对比测试不能用 AI 生成的指标代替。

## 8. 验证方案与验收门槛

### 8.1 离线确定性测试

1. `FactRenderer`：真实分数 68 时，模型无论返回 99、1 分钟还是合法但不相关证据，都不得进入最终事实摘要。
2. 工具边界：未知工具、额外字段、伪造坐标、别的 report/grid、超 2 公里地图点、`partial` 排名全部拒绝或降级。
3. 会话并发：相同幂等键只生成一个 job；旧 revision 的 AI patch 不覆盖新地图点击；报告切换丢弃旧流；客户端断开后服务端仍可查询 job。
4. 失败恢复：模型 JSON 不支持、工具超时、QPS 限流、路线零值和进程重启均产生可解释状态，不把失败当“无设施”。
5. 成本：每次模型/地图请求记录预算预占、实际 usage、重试次数、计费未知状态；超过硬预算在工具边界停止新请求。

### 8.2 真实地图与用户任务基准

至少建立“选中心点 → 运行体检 → 查看等时圈 → 点击网格解释 → 模拟设施 → 比较两方案 → 导出”的固定脚本，记录成功率、澄清轮数、人工点击数、P95 等待、缓存冷热、模型降级率和事实引用通过率。空间正确性指标由独立人工/地图样本核验；没有实测就不填百分比。冷缓存、暖缓存、种子缓存三者分开报告，种子不能被描述为当日 API 测算。

### 8.3 模型和地图供应商验收

为每个候选模型保存 capability JSON 和小样本响应：普通 JSON、严格字段、工具调用、拒绝并行、超时/取消、usage 返回、超长输入。为百度接口保存账号/接口版本、批量上限、QPS、矩阵零值语义、foot_fastest 权限与价格核验记录。未做真实收费验收前，只能在文档中标注“待核验”，不能将兼容 URL 或本地常量当作能力证明。

## 9. 风险与架构裁决

| 风险 | 影响 | 裁决 |
|---|---|---|
| 旧解读链虚构分数/时间 | 评审看到错误事实，破坏核心正确性 | P0 修复事实绑定；在修复前禁用 LLM 数值摘要 |
| 三个入口状态不一致 | 用户问答与地图/表单脱节 | WorkspaceState + revision 是唯一真相，文本只是意图 |
| 模型兼容能力误判 | 重试、费用和结果格式不可控 | capability registry + 部署验收 + 规则降级 |
| 外部收费调用无法取消 | 用户以为停止但仍产生费用 | Job cancel 只阻止新请求，账本披露已发送请求 |
| 缓存/种子被说成最新数据 | 违反真实路网交付边界 | 保留 observed/imported/cached/expires 时间和来源标签 |
| unknown 被模型说成无设施 | 误报服务盲区 | 未知为一等状态，禁止“没有/不可达”断言 |
| LLM 语义清洗直接改 POI | 空间事实被污染 | 模型只提候选标签，规则/人工确认后才进入分析 |
| 批量参数超过当前百度限制 | 批量请求失败或超额 | 运行时配置 + 账号级契约测试，不硬编码官方配额 |
| 为展示 AI 过早引入大平台 | 赛前部署和故障面扩大 | P0/P1 先 SQLite 单体，确有并发再拆 worker |

最终架构裁决：AI 是交互和假设生成层，地图/空间服务是事实和约束层，Fact Store 是两者之间的不可变边界，JobService 是费用/取消/恢复边界。任何“AI 说了算”的设计都不满足本赛题正确性要求；任何完全不用 AI 的设计又无法体现用户要求的智能入口和降低操作难度。

## 10. 证据索引

- 赛题原文：[`【开源AI工具赛道】基于地图开发能力的“15分钟生活圈”智能体检与规划助手.pdf`](../../../【开源AI工具赛道】基于地图开发能力的“15分钟生活圈”智能体检与规划助手.pdf)。
- 官方要求基线：[`contest-official-requirements-2026.md`](contest-official-requirements-2026.md)。
- 领域约束：[`CONTEXT.md`](../../CONTEXT.md)；[`contest/algorithm-overview.md`](../contest/algorithm-overview.md)。
- 自然语言解析：[`analysis_intent.py`](../backend/app/analysis_intent.py)、[`schemas.py`](../backend/app/schemas.py)。
- AI 解读与工具：[`ai_assistant.py`](../backend/app/ai_assistant.py)、[`llm.py`](../backend/app/llm.py)、[`planning_assistant.py`](../backend/app/planning_assistant.py)。
- 任务、缓存与地图：[`repositories.py`](../backend/app/storage/repositories.py)、[`walking_cache.py`](../backend/app/storage/walking_cache.py)、[`baidu.py`](../backend/app/baidu.py)、[`maps/baidu.py`](../backend/app/maps/baidu.py)、[`provider.py`](../backend/app/maps/provider.py)。
- 前端入口：[`NaturalLanguageAnalysis.vue`](../../frontend/src/components/NaturalLanguageAnalysis.vue)、[`AiPlanningAssistant.vue`](../../frontend/src/components/AiPlanningAssistant.vue)、[`App.vue`](../../frontend/src/App.vue)。

本报告本轮只完成源码/PDF 证据整理和离线 FakeProvider 漏洞复现，没有修改运行代码，没有调用收费地图或模型 API，也没有把未核验的供应商配额、价格或准确率写成既成事实。
