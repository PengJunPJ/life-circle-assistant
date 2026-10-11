# 证据索引

状态约定：✅ 已有可直接引用；🟡 部分满足（材料在但结论或完成度受限）；⬜ 待补。负责人：自动 = 仓库内脚本/CI/我可生成；人工 = 需账号权限或现场核查。

| ID | 证据条目 | 位置 | 状态 | 负责人 |
| --- | --- | --- | --- | --- |
| E-01 | 源码托管与开源许可证（Apache-2.0） | GitHub `main` 参赛主仓库；根 [LICENSE](../../../LICENSE) | ✅ | — |
| E-02 | 一键构建/部署与示例数据（Docker Compose + 合成快照 + 缓存种子） | [../../README.md](../../README.md)、[../../docker-compose.yml](../../docker-compose.yml)、[../../backend/data/baidu_snapshot.json](../../backend/data/baidu_snapshot.json)、[../../backend/data/walking_cache_seed.json](../../backend/data/walking_cache_seed.json) | ✅ | — |
| E-03 | 无凭证离线演示闭环 | [demo-script.md](demo-script.md) 路径 A | ✅ | — |
| E-04 | 真实模式地图能力（坐标转换/地理编码/POI/步行/等时圈） | [demo-script.md](demo-script.md) 路径 B；[algorithm-overview.md](algorithm-overview.md)；[../architecture/v2-trustworthy-analysis.md](../architecture/v2-trustworthy-analysis.md) | ✅ WGS84/GCJ-02 经百度 Geoconv V2 统一为 BD-09；其余地图能力已实现 | — |
| E-05 | 定稿真实跑报告归档（含执行指标） | [../validation/reports/shachong-changsheng-20261004.json](../validation/reports/shachong-changsheng-20261004.json)；历史对照：[红山报告](../validation/reports/hongshan-haiyundonglu-20260921.json) | 🟡 现有报告早于 2.3.0 候选版；可证明历史真实链路，不能证明当前候选版真实复跑 | 自动 |
| E-06 | 等时圈生成算法（扇形采样+二分细化+降级标识） | [algorithm-overview.md](algorithm-overview.md)；[../../../docs/adr/0004-等时圈精度分档与报告导出.md](../../../docs/adr/0004-等时圈精度分档与报告导出.md) | ✅ | — |
| E-07 | 地图 API 调用策略（逐词 POI、预筛、批量算路分块、缓存/限流/重试） | [algorithm-overview.md](algorithm-overview.md)；[../../../docs/adr/0009-百度地图调用的两阶段筛选策略.md](../../../docs/adr/0009-百度地图调用的两阶段筛选策略.md) | ✅ | — |
| E-08a | 百度单源 POI 多关键词语义归一与去重 | [../architecture/v2.1-facility-normalization.md](../architecture/v2.1-facility-normalization.md)；[../../backend/app/maps/baidu.py](../../backend/app/maps/baidu.py) | ✅ 当前运行时能力仅限百度单源 | — |
| E-08b | 跨来源对齐策略、来源登记与默认关闭的纯计算模块 | [../architecture/multi-source-poi-reconciliation.md](../architecture/multi-source-poi-reconciliation.md)；[multisource-poi/](../validation/multisource-poi/README.md)；[../../backend/app/analysis/facility_reconciliation.py](../../backend/app/analysis/facility_reconciliation.py) | 🟡 策略、匹配规则和测试已具备；真实高德样本、许可和 50–100 对人工标签未完成 | 自动+人工 |
| E-08c | 高德辅助观察适配器与百度主报告摘要 | [../../backend/app/amap.py](../../backend/app/amap.py)；[../../backend/app/validation/amap_facility.py](../../backend/app/validation/amap_facility.py)；[../../backend/scripts/probe_amap.py](../../backend/scripts/probe_amap.py) | 🟡 Key 连通性已验证；默认关闭，不改变百度主分析，不保存原始高德 POI | 自动 |
| E-08d | 多源运行时启用与独立准确率验证 | [../../backend/scripts/evaluate_multisource_poi.py](../../backend/scripts/evaluate_multisource_poi.py)；同 E-08b | ⬜ 书面许可、真实 fixture 和人工标签待办；无多源准确率结论 | 人工+自动 |
| E-09 | 服务盲区识别算法与分级网格口径 | [../../../docs/adr/0006-mvp设施类别与盲区判定标准.md](../../../docs/adr/0006-mvp设施类别与盲区判定标准.md) | ✅ | — |
| E-10 | 真实社区对比核查（地址/坐标/口径一致性修复记录） | [../validation/v2-real-community-comparison.md](../validation/v2-real-community-comparison.md) | ✅ | — |
| E-11 | 64 网格人工基准 → verified 指标（准确率/精确率/召回率/F1/混淆矩阵） | [../validation/benchmarks/](../validation/benchmarks/)、[../validation/results/shachong-changsheng-20261004.md](../validation/results/shachong-changsheng-20261004.md)、[../validation/v2.1-benchmark-evaluation.md](../validation/v2.1-benchmark-evaluation.md) | 🟡 沙涌长盛花园 64/64 已完成；与系统同源同规则，仅作一致性证据；红山基准仍为 draft | 自动+人工 |
| E-12 | 性能三档实测（冷 124s / 种子 19s / 全缓存 12.5s）与批量对照 | [../performance/v2-baseline.md](../performance/v2-baseline.md) | ✅ | — |
| E-13 | 容错与降级证据（限流/超时/重试/部分失败/降级估算披露） | 报告 `data_quality` 区；[../architecture/v2-trustworthy-analysis.md](../architecture/v2-trustworthy-analysis.md) | ✅ | — |
| E-14 | 可视化与交互（等时圈、网格色块、柱状+tooltip、雷达图、七类图层） | [../releases/v2.3.0.md](../releases/v2.3.0.md)；截图待补 | 🟡 功能已有，截图待补 | 自动 |
| E-15 | AI 解读能力与证据约束（引用校验、防幻觉过滤、无密钥规则降级） | [../../backend/app/ai_assistant.py](../../backend/app/ai_assistant.py)；[demo-script.md](demo-script.md) A6 | ✅ | — |
| E-16 | 质量门禁（CI 三 job + 本地 `make quality`） | [../../../.github/workflows/quality.yml](../../../.github/workflows/quality.yml)、[../../Makefile](../../Makefile) | 🟡 本地候选版后端 140、前端 46 测试通过；Ruff、ESLint、类型检查、构建和容器冒烟通过。GitHub `main` 最近一次后端 job 因开发依赖漏声明 `pytest-asyncio` 失败，补依赖后待远端重跑 | 自动 |
| E-17 | 密钥脱敏扫描记录（仓库无 AK/Secret/模型密钥） | [security-scan-2026-10-08.md](security-scan-2026-10-08.md) | ✅ 工作树与 Git 历史未发现高置信度凭证值；发布物仍需复核 | 自动 |
| E-18 | Gitee 镜像仓库 CI/保护分支（可选，不作为 GitHub 主仓库参赛阻断项） | [../research/gitee-go-quality-gate.md](../research/gitee-go-quality-gate.md)（调研已有，实跑未做） | ⬜ | 人工+自动配合 |
| E-19 | 截图集（深浅主题、图层、盲区依据、雷达、AI、导出、执行指标） | [screenshots/](screenshots/README.md) | ⬜ | 自动 |
| E-20 | 演示录屏（3~5 分钟） | 赛事平台附件 | ⬜ | 人工 |
| E-21 | 限制与披露汇总 | [limitations.md](limitations.md) | ✅ | — |
| E-22 | 赛事平台材料（报名表、作品描述、视频上传） | 外部系统 | ⬜ | 人工 |
| E-23 | 依赖与容器漏洞审计（Python/npm + 应用/基础镜像） | [dependency-audit-2026-10-09.md](dependency-audit-2026-10-09.md)、[container-audit-2026-10-11.md](container-audit-2026-10-11.md)、[修复复验](container-audit-remediation-2026-10-11.md)、[../../../.github/workflows/security.yml](../../../.github/workflows/security.yml) | ✅ Python/npm 审计为 0；API/Web 运行镜像经 Trivy/Grype 复验为 0 Critical / 0 High；基础镜像和构建期残余风险已披露 | 自动 |
| E-24 | 开源治理规则（许可证、Issue/PR、评审、发布、安全和外部服务责任边界） | [../../../CONTRIBUTING.md](../../../CONTRIBUTING.md)、[../../../SECURITY.md](../../../SECURITY.md)、[../../../MAINTAINERS.md](../../../MAINTAINERS.md)、[../governance/open-source-governance.md](../governance/open-source-governance.md) | ✅ 初版材料已提交；DCO/CLA、分支保护实际配置和安全联系入口仍以 GitHub 设置为准 | 自动+人工 |
| E-25 | 依赖合规、第三方声明和 SBOM 生成口径 | [../governance/dependency-compliance.md](../governance/dependency-compliance.md)、[../governance/third-party-notices.md](../governance/third-party-notices.md)、[../governance/sbom/README.md](../governance/sbom/README.md)、[../governance/dependency-inventory.yaml](../governance/dependency-inventory.yaml)、[修复复验](container-audit-remediation-2026-10-11.md) | 🟡 运行镜像双扫描已通过并归档；许可证逐包复核、正式 SBOM 和构建期 npm 残余风险仍待发布前复核 | 自动+人工 |
| E-26 | 维护路线和多源验证门槛 | [../governance/maintenance-roadmap.md](../governance/maintenance-roadmap.md)、[../architecture/multi-source-poi-reconciliation.md](../architecture/multi-source-poi-reconciliation.md) | 🟡 路线与验收标准已记录；高德书面许可、50–100 对双源人工标签和独立指标仍待完成 | 自动+人工 |

## 使用规则

- 评审询问"准确率"时，明确区分 E-11 的沙涌同源一致性与独立来源、多社区准确性验证；不把 100% 一致率宣传为泛化成绩。
- 引用性能数字时必须注明档位（冷/种子/全缓存）与 `BAIDU_MAP_QPS` 配置，见 E-12。
- E-05 每次重大版本后重跑一次定稿真实跑并归档，保持"最新真实能力"证据不过期。
- E-08b/E-08c 的测试和 Key 探测不等于真实双源准确率；E-08d 只有在书面许可、50–100 对双源人工标签和评估报告归档后才可升级状态。
