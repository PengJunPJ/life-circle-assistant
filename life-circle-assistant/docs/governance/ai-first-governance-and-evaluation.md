# AI 语义治理、居民观察与独立评估

本次补齐 A1、A2、A10、B4 及 A11 的语义和五组消融部分。大模型、嵌入和 OCR 产生的是审核材料；只有人工确认的目录变更，经过正式路径测量和规则重算后，才形成一份新的正式报告。旧报告保留不变。

## 配置与运行边界

嵌入默认关闭。启用服务模式时，需要设置以下变量：

```dotenv
SEMANTIC_EMBEDDING_ENABLED=true
SEMANTIC_EMBEDDING_PROVIDER=openai_compatible
SEMANTIC_EMBEDDING_BASE_URL=https://你的服务地址/v1
SEMANTIC_EMBEDDING_MODEL=你已部署的中文嵌入模型
SEMANTIC_EMBEDDING_API_KEY=你的凭证
```

服务遵循 `POST embeddings` 的 JSON 契约：输入为 `model` 和 `input` 文本列表，输出为带整数 `index` 的 `data[].embedding`。每批不超过 256 条、每条不超过 2048 字符，向量必须数量、维度一致且只含有限数。返回的 `usage.prompt_tokens` 如有则记录；缺失时保持未知。

本地模式使用 `SEMANTIC_EMBEDDING_PROVIDER=local` 和 `SEMANTIC_EMBEDDING_MODEL_PATH`，目录须已准备好。部署者另外安装 `sentence-transformers`；代码以 `local_files_only=True` 读取，不自动下载模型。未配置、超时或响应无效时，语义审核降级为规则候选，并显示诊断原因。

图片 OCR 同样默认关闭：

```dotenv
OBSERVATION_OCR_ENABLED=true
OBSERVATION_OCR_ENDPOINT=https://你的OCR服务地址/extract
OBSERVATION_OCR_API_KEY=你的凭证
```

OCR 的请求为 `{image_base64, mime_type, language: "zh"}`，响应为 `{text: "识别出的中文"}`，文本不超过 5000 字符。图片支持 PNG、JPEG、WebP，最多 4 MiB，Base64、MIME 与文件头需要一致。OCR 未配置或失败时仍保存原图，供人工复核，不丢弃居民提交。

嵌入和 OCR 在发送 HTTP 请求前计入统一执行账本；预算用尽时不会发送请求。本地嵌入调用也单独记录。模型名称、目录版本、OCR 契约和规范来源散列随执行记录留存。

## 费用估算与防止双算

账本记录实际用量，`estimated_total` 为人民币估算；未人工核验账单时，`settled_total` 为 `null`。费用不从“模型调用次数”推造，未配置价格、计价口径不确定或必要用量缺失时，估算总额同样保持未知。

| 服务 | 计价配置 | 互斥和未知处理 |
| --- | --- | --- |
| 普通地图 | `MAP_PRICING_UNIT=request` 配 `MAP_REQUEST_PRICE_CNY`，或 `route_pair` 配 `ROUTE_PAIR_PRICE_CNY` | 每次执行只使用一种口径；按路线对计价无法代表 POI 检索、地理编码等请求，存在这些调用时总费用仍未知 |
| 中文嵌入服务 | `EMBEDDING_PRICING_UNIT=request` 配 `EMBEDDING_REQUEST_PRICE_CNY`，或 `tokens` 配 `EMBEDDING_PRICE_CNY_PER_MILLION` | 请求价与 token 价不相加；按 token 计价时服务未返回有效用量，总费用未知 |
| 原生等时圈 | `NATIVE_ISOCHRONE_PRICE_CNY` | 按原生 HTTP 请求计价；这些请求从普通地图请求计价数中扣除，避免重复收费估算 |
| OCR | `OCR_REQUEST_PRICE_CNY` | 按 OCR HTTP 请求计价，失败尝试仍记录实际请求 |
| 大语言模型 | `LLM_INPUT_PRICE_CNY_PER_MILLION` 与 `LLM_OUTPUT_PRICE_CNY_PER_MILLION` | 输入、输出分别估算；模型未返回必要 token 用量时保持未知 |

地图或嵌入的计价单位留空时，只有一个对应价格已配置才自动推断口径；同时配置两种价格、都不配置价格或单位无效时，口径保持未知。显式选择单位后只采用该单位的价格，即使另一个价格也有配置也不相加。价格必须是有限的非负数；配置 `0` 表示提供方已确认免费，留空表示尚未核验。单价按一次请求/一路线对或一百万 token 计算，应以实际提供方计费规则设置，不能把请求数量与逻辑路线对数混用。

本地嵌入记录 `embedding_local_calls`；当前不估算设备、电力或模型部署费用，不能把云服务估算当作系统总拥有成本。所有可选配置模板位于项目根目录 `.env.example`。

报告说明中的“预算与版本账本”提供人工账单结算及历史入口。`GET /api/executions/{id}/settlements` 读取追加历史；`POST` 同路径录入本次执行的全服务核验总额，要求 `amount_cny`、`bill_reference`、`reviewer`、`evidence`、`expected_version`、`expected_usage_sha256` 与 `scope=execution_total`。仅终态执行可录入，金额非负、最多两位小数，零金额合法；前端不将估算自动填作账单金额。

结算版本只追加，数据库禁止修改或删除。版本与实际用量指纹在事务内校验，并发冲突返回409；更正必须追加下一版。续算或新增用量会使旧结算标记 `settlement_stale`，当前 `settled_total` 回到未知，需重新核验。人工记录不冒充提供方自动结算，`reviewer` 仍是审计字段；合成账单测试只验证流程，不构成真实费用证据。

## 语义审核与正式重算

目录保存 `records` 正式设施与 `source_records` 原始来源。规则去重前记录和高德辅助验证原始记录均保留，来源标识重复时加命名空间。辅助数据不会自动成为正式设施；坐标系不同的记录不会直接进行空间实体比较。

语义审核独立处理类别与实体关系。中文类别锚点嵌入可召回类别候选，名称嵌入只能在同坐标系、120 米空间邻近门禁内召回实体候选。同品牌、名称相似、同类别均不代表同一机构。入口、科室、不同分店、地址冲突需要分别处理；任何模型结果都保留为 `pending_human_review`。

HTTP 前缀为 `/api/reports/{report_id}`：

| 方法与路径 | 行为 |
| --- | --- |
| `POST /ai/semantic-review`，`{use_model: true或false}` | 基于原始来源生成并保存审核批次，返回 `review_id` 和目录版本 |
| `GET /governance` | 读取当前目录、全部审核批次、居民观察、审计和历史版本 |
| `POST /governance/decisions` | 接纳、驳回或修正类别/实体建议 |
| `POST /governance/recompute`，无请求体 | 用最新已审核目录新建任务，重新测路、生成服务区和评分，返回新报告 |

决策示例：

```json
{
  "review_id": "保存后的批次标识",
  "kind": "category",
  "record_id": "原始来源标识",
  "decision": "correct",
  "category": "pharmacy",
  "reviewer": "复核人",
  "reason": "现场复核编号或数据来源",
  "expected_version": 1
}
```

实体决策使用 `kind=entity`、`left_id`、`right_id`；修正时增加 `relation`，取值为 `same_entity`、`different_entity`、`department` 或 `entrance`。未决建议不能直接合并，需人工确定关系。规则已合并的不同实体可从原始来源恢复；入口和科室关系保持关联而不独立计数。人工已纠正的类别可解除旧类别冲突，其他分店/入口等门禁保留。

`expected_version` 与最新版本不符时返回 409。审核决定、目录新版本和审计在同一 SQLite 事务中保存。已核验停业的来源被排除，旧分类建议不能重新将其纳入目录；已审核入口或科室也不能被旧建议重新计作独立设施。重新计算跳过旧自动去重，避免人工拆分后再次合并。

`reviewer` 当前为操作者填写的审计字段，不是已经认证的账号身份。本地 MVP 未提供权限体系，不能将此字段宣称为已完成身份认证。

## 居民观察闭环

| 方法与路径 | 行为 |
| --- | --- |
| `POST /observations` | 接收文字或图片，以及可选 BD-09 经纬度；返回待核验观察 |
| `GET /observations/{observation_id}/image` | 查看原始图片，返回 `no-store` 和 `nosniff` 响应 |
| `POST /observations/{observation_id}/decision` | 人工核验后接纳、驳回或修正事件 |

提交体为 `{text?, image_base64?, mime_type?, lng?, lat?}`。文字与图片至少提供一项，经纬度同时提供。观察包含 `id`、`kind`、`status`、`ocr_text`、`ocr_status`、`location`、`has_image`、`image_url` 和 `affects_official_facts=false`。OCR 文本只作为来源材料，不执行其中的指令。

决策必须提供 `decision`、`reviewer`、`reason`、`expected_version`，并按事件核验字段：关闭需 `facility_id`；入口变更需设施与 BD-09 坐标；补录设施需名称、类别和坐标；围挡需当前服务网格中两个直接相邻的网格标识。进入正式目录的坐标须在支持范围内。围挡证据与审核目录一起事务保存，错误网格不会留下半写入结果。

## 规范检索与角色报告

`POST /audience-report` 输入 `{audience: "resident"|"community"|"planner", query?: "问题"}`。居民视图突出设施数量、步行时间和短板；社区视图突出复核工作；规划师视图增加空间依据与规划输入核验。

角色报告使用固定报告事实槽位组装观察，并输出独立的 `possible_causes`、`measures` 和 `verification_conditions`。原因标记为假设，措施标记为建议，用户问题不能插入新事实或改变分数。

默认检索项目 ADR 0006、0010、0011，引用明确标记 `scope=项目规则`。这些文件不冒充地方规划法规。外部规范通过 `LIFE_CIRCLE_NORMS_PATH` 指向 JSON 列表，每条必须有 `id/title/version/source/scope/text/verified_by/verified_at`。检索返回文段、来源、适用范围、版本和 SHA-256；报告保留 `citations`，执行账本保留规范版本。实际适用的地方规范仍需部署者核验并配置。

## 独立语义评估

在后端目录执行：

```sh
.venv/bin/python scripts/evaluate_semantics.py 独立标签.json
.venv/bin/python scripts/evaluate_semantics.py 独立标签.json --use-embedding --use-model
```

第二条会使用显式配置的服务并可能消耗配额。数据示例：

```json
{
  "dataset_kind": "independently_labeled",
  "label_source": "独立复核台账及标注版本",
  "communities": [{
    "community_id": "社区标识",
    "coordinate_system": "BD09",
    "records": [
      {"id": "a", "name": "药房甲", "category": "pharmacy", "lng": 113.4, "lat": 23.1},
      {"id": "b", "name": "药房乙", "category": "pharmacy", "lng": 113.4001, "lat": 23.1}
    ],
    "category_labels": {"a": "pharmacy", "b": "pharmacy"},
    "entity_labels": [{"left_id": "a", "right_id": "b", "same_entity": false}]
  }]
}
```

每个社区单独生成候选；类别标签和实体标签不传给模型。记录及实体对不可重复，实体标签必须为布尔值。输出类别准确率、弃答数量、错误合并、漏合并、合并精确率/召回率和未决对数。未决不算正确合并，也不计为已正确判定的不同实体。这里的“社区隔离”指分别运行候选与评估，并不自动证明数据来源已经经过现场审核。

## 五组消融评估

```sh
.venv/bin/python scripts/evaluate_ablations.py --fixture
.venv/bin/python scripts/evaluate_ablations.py --dataset 五组实际产物与独立标签.json
```

`--fixture` 不访问外部服务，执行意图解析、语义审核、采样回归、约束编译和组合求解。完整 stdout 含结果及 `artifacts` 原始产物；`artifacts` 可直接作为 `--dataset` 的输入。请保存完整 JSON，不将截断的终端文本当成证据。

`--dataset` 的顶层为 `dataset_kind/label_source/communities`；每个社区包含 `community_id`、`candidates`、`truth` 与 `arms`。五组键固定为 `no_model/conversation_only/semantic_review/active_sampling/full_system`。

- `truth` 包含 `category_labels`、`entity_labels`、`route_minutes`、`threshold_minutes`、`intent` 和与规划接口相同的 `constraints`。本评估契约要求所有实体对涉及的记录都出现在类别标签中。
- 若有最低受益人口限制，`truth` 还需提供独立 `candidate_coverage`（候选标识到可达网格标识列表）和 `population_by_grid`（网格标识到核验人口）。按选中候选覆盖并集去重计算，缺少标签不能认为约束满足，也不能把各候选的服务人口直接相加。
- 每组产物包含 `category_predictions`、`entity_predictions`、`sampling`、`selected_ids`、`predictions_used_for_official_score=false`、`usage`、`latency_ms`、`review_workload` 和 `user_steps`。
- `sampling` 包含不重叠的 `training_ids/validation_ids`、`route_pair_budget` 和 `predictions[{point_id,mean_minutes}]`，可直接使用采样实验输出。五组必须具有相同留出集、阈值和路线对预算。
- `usage` 中 `route_pairs/model_calls` 为实际记录的非负整数；`total_tokens` 或 `physical_http_requests` 未知时用 `null`。`review_workload/user_steps` 应源于操作记录，不填估算的“节省比例”。

重复标签、错误关系、重复预测、训练泄漏或预算不一致会拒绝评估。超预算、未知选址、重复选址、违反数量/预算/类别/容量/用地限制、预测污染正式分数均计为违规。成本或容量未知时不能认定约束已满足。留出预测未知时保持未知，不能记为零误差。

当前合成运行结果见 [五组消融合成验证](../validation/ai-first-ablation-fixture-2026-10-14.md)。真实模型收益、独立现场精度、实际 API 节省、人效与账单成本仍须使用真实来源和独立标注实测。
