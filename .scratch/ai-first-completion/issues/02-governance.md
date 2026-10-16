# 语义与居民观察治理
Type: task
Status: resolved

覆盖 A1、A2、A10、B4、A11 语义评估：嵌入装配、版本目录及审核重算、文字图片OCR、规范角色报告及语义独立评估。

## Comments

原报告不可变；所有未知或未审核输入不得成为正式事实。

## Answer

已补齐显式配置的中文嵌入服务/本地模型、原始多源来源保留、审核目录版本与审计、类别及实体接纳/驳回/修正、人工拆分后正式新任务重算。旧报告不可变；已核验停业或从属的记录不会被旧分类建议重新计数。

已补齐居民文字/图片/OCR待核验、原图人工查看、关闭/入口/漏设施/围挡审核闭环。围挡空间证据与目录审核在同一SQLite事务中保存；未审核观察不进入正式事实。

已补齐居民/社区/规划师角色报告、事实/假设/措施/核验条件分层、项目规则与可配置外部规范文段检索及带版本/SHA的引用。项目规则不冒充法规；MVP操作者字段不冒充身份认证。

已补齐独立社区语义评估与五组同预算消融工具。标签不传模型、重复标签与训练泄漏拒绝；未知预测/token/价格保留。预算、数量、类别、容量、用地和受益人口约束均检查，人口按独立覆盖网格并集去重，不能把候选人口相加。

配置/接口/评估说明：`life-circle-assistant/docs/governance/ai-first-governance-and-evaluation.md`。

五组合成证据：`life-circle-assistant/docs/validation/ai-first-ablation-fixture-2026-10-14.md` 与同名JSON。

专项回归：`pytest tests/test_ablations.py tests/test_governance.py tests/test_semantic_review.py tests/test_amap_validation.py tests/test_multisource_poi_evaluation.py tests/test_native_isochrone.py -q`，73 passed；本子任务源文件、脚本和测试Ruff通过。测试默认禁用/清空本机嵌入、OCR与原生等时圈配置，不调用本机付费服务。

真实中文嵌入/LLM效果、现场路线精度、实际配额节省、审核人效和账单金额尚需真实账号/授权数据及独立标注实测，合成结果不替代现场成绩。
