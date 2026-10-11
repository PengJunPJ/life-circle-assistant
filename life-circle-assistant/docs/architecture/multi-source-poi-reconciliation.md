# 多源 POI 对齐策略（设计与实现边界）

状态：已实现离线候选对齐模块；真实高德双源样本和独立准确率验证待取得许可与 API Key 后完成。  
策略版本：1.0。运行时默认关闭；当前 `AnalysisApplicationService` 不调用该模块。

## 目标与非目标

目标是将同一社区、同一设施类别的不同地图来源记录形成可解释的候选实体组，保留各来源溯源信息、字段冲突和时效线索，并支持对人工标注对照样本计算匹配指标。

本策略不把百度或高德任一来源定义为地面真值，不用未召回推断设施不存在，不自动覆盖现有百度主报告，也不把离线 fixture 当成真实双源验证结果。

## 模块 seam

```text
来源适配器（百度 / 高德 / 获许可的开放数据）
  → 来源字段归一化与坐标统一
  → reconcile_facilities(records)
  → CanonicalFacility + decisions + summary
  → 验证报告（默认不进入主分析报告）
```

`reconcile_facilities(records, as_of=None)` 是对齐模块唯一的记录级 interface。它是纯计算模块，不访问网络、数据库或环境变量。`decide_candidate_features(...)` 为数据最小化的评估接口，只接受已经计算的名称/地址相似度、距离、类别和坐标兼容性特征。来源 API 调用、许可证审查、人工标签和持久化由调用模块负责。高德原生返回 GCJ-02 坐标，观察适配器先通过百度 Geoconv `model=1` 转为 BD-09，再交给该接口；登记表同时保留原生和比较坐标系。

当前已增加 `AmapPoiClient` 和 `AmapFacilityValidator` 作为辅助观察链路。它们只在 `AMAP_VALIDATION_ENABLED=true` 时运行，百度仍负责正式设施、步行、评分和盲区分析；高德失败、限流或截断只会写入 `multisource_validation` 辅助摘要，不会使百度主报告替换来源或静默补齐数据。高德原始 POI 仅在进程内使用，公开报告不包含名称、地址、坐标或来源 ID。

## 输入记录契约

每条记录需要：

| 字段 | 含义 |
| --- | --- |
| `source` | 来源稳定标识，如 `baidu`、`amap` |
| `source_record_id` | 仅在来源内唯一；不得跨源直接比较 |
| `name` / `address` | 当次运行内存使用的原始字段 |
| `category` | 通过版本化映射表归一后的项目类别 |
| `lng` / `lat` | 已统一到相同比较坐标系 |
| `coordinate_system` | 坐标系标记；不同坐标系不计算距离、不匹配 |
| `retrieved_at` | 本次查询时间，不等于来源数据的实际更新时间 |
| `source_updated_at` | 来源明确提供时的更新时间；缺失必须保留为未知 |
| `source_priority` | 来源登记表配置的字段级 tie-break 优先级；缺省为 0 |

高德 POI ID 与百度 UID 分别只形成 `amap:<id>`、`baidu:<uid>` 来源标识。任何一方的 ID 都不是全局实体 ID。

## 候选决策规则

名称与地址相似度由 Unicode NFKC、空白/标点规整后以 `SequenceMatcher` 得到，取值 `[0, 1]`。当前首版权重是项目初始假设，不是行业标准：

```text
score = 0.35 × name_score
      + 0.30 × address_score
      + 0.25 × max(0, 1 - distance_m / 100)
      + 0.10 × category_match
```

规则顺序：

1. 坐标系不同：`coordinate_system_conflict`，不计算距离，不自动匹配。
2. 规范化类别不同：`category_conflict`，不合并并保留冲突决策。
3. 距离大于 100 米：`unmatched`，同名也默认视为不同门店/校区。
4. 距离 50–100 米：最高只进入 `needs_review`，不得自动合并。
5. 距离不超过 50 米，且总分至少 0.85 或地址相似度至少 0.80：`matched`。
6. 其他候选只有总分至少 0.65 时标记 `needs_review`，否则 `unmatched`。
7. 一个记录同时命中多个实体组时，标记 `multiple_cluster_candidates`，不做传递式合并。

“未匹配”只表示当前采集策略下没有匹配到另一个来源记录，不表示设施不存在。来源 API 的搜索上限、关键词和失败状态必须随验证结果披露。

## 冲突、代表字段与时效性

- `aliases` 保留合并组中全部规范化名称。
- 地址差异显著时，`reconciliation.conflicts` 包含 `address`，并保留各地址值；不得静默覆盖。
- 合并组坐标最大两两距离大于 25 米时记录 `coordinates` 与 `coordinate_spread_m`。
- 代表记录按 `retrieved_at` 新者优先，再按来源优先级和地址完整度打破同一时间的平局。优先级只是选择展示代表字段，不代表该来源更真实。
- 只有来源明确提供 `source_updated_at` 才计算时效状态：30 天内为本项目策略的 `fresh`，超过 30 天为 `stale`；缺失或无效为 `unknown`。`retrieved_at` 只说明查询时间，不能伪装成地图数据更新时间。
- POI 名称、地址、坐标和 ID 冲突均不得因代表记录选择而丢失；本模块记录地址和坐标冲突，来源别名保存在结果中。

来源顺序和类别映射见 [`../validation/multisource-poi/source-registry.yaml`](../validation/multisource-poi/source-registry.yaml)。两个来源当前同属观察级，未配置任何一方的权威性优势。

## 验证与可审计输出

自动单测覆盖跨源合并、远距离同名分店、类别冲突、坐标系不一致、50–100 米人工复核、观测时间/优先级选择和特征级评估。测试中的记录是人工构造的规则样例，不是高德真实数据证据。

正式离线审计必须使用 50–100 对独立人工标签，至少包含匹配、非匹配、类别/字段冲突与边界样本。报告 `match precision/recall/F1`、人工冲突识别召回率、待复核率和混淆矩阵；标签应由未参与匹配规则编写的复核者确认，并记录复核人代号与时间。

为减少第三方数据保留，公开 fixture 只保留名称相似度、地址相似度、距离、类别一致性、坐标兼容性、人工标签及哈希化样本编号，不保存 POI 名称、地址、坐标或来源 ID。任何特征留存和公开展示须以高德书面许可范围为前提。当前 fixture 状态为 `awaiting_live_capture`，没有填入虚构的真实样本。

```bash
cd life-circle-assistant
python3 backend/scripts/evaluate_multisource_poi.py \
  --fixture docs/validation/multisource-poi/fixture.json \
  --json-output docs/validation/multisource-poi/evaluation.json \
  --markdown-output docs/validation/multisource-poi/evaluation.md
```

脚本只有在书面许可、50–100 对人工标注样本及元数据齐备后才会运行。它拒绝把原始名称、地址或来源 POI ID 存入 fixture；评估输出不含这些字段。

## 实施状态与启用门槛

- ✅ 策略、输入契约和来源登记表。
- ✅ `reconcile_facilities()` 默认未接入主分析，纯计算单测通过。
- ✅ 支持特征级人工标注指标评估工具。
- ⬜ 高德书面许可、Web 服务 Key、受控真实双源采集。
- ⬜ 50–100 对独立人工标签及真实评估结果。
- ⬜ 通过预先登记的指标门槛后，另行决策是否设计运行时开关；本策略不自动打开。

当前不得宣称项目已具备多源运行时分析、多源准确率或独立真值验证。
