# 参赛证据包导览（评审阅读顺序）

本目录是"15 分钟生活圈智能体检与规划助手"参加 2026 上海开源软件应用创新大赛（开源 AI 工具赛道）的证据包入口。目标：评审人员不需要开发者口头解释，按下列顺序即可复现运行、核验能力、读取限制。

当前应用版本 `2.3.0`（候选 tag `v2.3.0`），许可证 Apache-2.0（仓库根 `LICENSE`）。本文档以 GitHub `main` 为参赛主仓库；只有完整质量与安全门禁通过后才创建标签。

## 阅读与核验顺序

1. **定位与价值**：[../../README.md](../../README.md)（项目定位、快速运行、模式说明）与 [../releases/v2.3.0.md](../releases/v2.3.0.md)（本版本范围与验证记录）。
2. **一键复现**：按 README 的 `cp .env.example .env && docker compose up --build` 启动；无凭证即进入离线快照演示，凭证齐备切真实模式。缓存种子使干净环境首跑约 19 秒，见 [../performance/v2-baseline.md](../performance/v2-baseline.md)。
3. **现场演示**：按 [demo-script.md](demo-script.md) 逐步操作，每步给出预期观察与证据指针；离线与真实两条路径分开。
4. **算法与 API 策略**：先读一页纸 [algorithm-overview.md](algorithm-overview.md)，再按需深入 [../architecture/v2-trustworthy-analysis.md](../architecture/v2-trustworthy-analysis.md)、[../architecture/v2.1-facility-normalization.md](../architecture/v2.1-facility-normalization.md)、[多源 POI 对齐策略](../architecture/multi-source-poi-reconciliation.md) 与 [../../../docs/adr/](../../../docs/adr/) 决策记录。
5. **真实社区证据**：[沙涌长盛花园真实报告](../validation/reports/shachong-changsheng-20261004.json)、[64 条核查基准](../validation/benchmarks/shachong-changsheng-20261004.json)、[评估结果](../validation/results/shachong-changsheng-20261004.md) 与[评估口径](../validation/v2.1-benchmark-evaluation.md)。沙涌 64/64 核查已完成，但属于百度同源一致性证据；跨来源准确率和多社区泛化仍未验证。
6. **性能与优化**：[../performance/v2-baseline.md](../performance/v2-baseline.md) 三档实测（冷 124s / 种子预热 19s / 全缓存 12.5s）与批量算路对照。
7. **质量与安全门禁**：[../../../.github/workflows/quality.yml](../../../.github/workflows/quality.yml)、[../../../.github/workflows/security.yml](../../../.github/workflows/security.yml) 与本地 `make quality`；候选版本的测试规模为后端 126 项、前端 46 项，生产与开发依赖漏洞审计和 npm high/critical 审计为阻断项。
8. **限制与披露**：[limitations.md](limitations.md) 汇总全部可信度边界，评审可据此判断哪些结论可直接使用。
9. **证据索引**：[evidence-index.md](evidence-index.md) 给出每条证据的位置、状态与负责人，含尚未完成项的诚实标注。
10. **治理与合规**：[开源治理](../governance/open-source-governance.md)、[维护路线](../governance/maintenance-roadmap.md)、[依赖合规](../governance/dependency-compliance.md) 和 [第三方声明](../governance/third-party-notices.md) 说明仓库维护、依赖审计、SBOM 与外部地图服务边界。

## 三条硬承诺

- 离线合成快照、历史缓存种子与真实测算在界面、报告和本证据包中**始终显式区分**，不混用结论。
- 沙涌长盛花园 64/64 同源核查已完成，但跨来源准确率和泛化能力未验证，**不将 100% 一致率宣传为整体准确率**。
- 当前体检运行时只接入百度单一 POI 来源；默认关闭的跨源对齐模块尚无高德真实双源验证，不将其描述为已上线多源能力。
- 真实 AK/Secret 不进入报告、截图、日志或版本库；所有示例凭证脱敏。

## 目录内容

| 文件 | 用途 |
| --- | --- |
| [demo-script.md](demo-script.md) | 现场演示脚本：操作→预期观察→证据指针 |
| [evidence-index.md](evidence-index.md) | 证据索引：位置、状态（已有/待补）、负责人 |
| [algorithm-overview.md](algorithm-overview.md) | 算法与 API 策略一页纸（10 分钟可读） |
| [limitations.md](limitations.md) | 限制与披露汇总 |
| [screenshots/](screenshots/README.md) | 截图清单与命名规范（图待补） |
