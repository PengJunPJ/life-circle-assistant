# 03：落地 Gitee CI/CD 质量门禁

Status: ready-for-agent

## 任务概述

在当前本地质量命令和 GitHub Actions 基础上，完成 Gitee Go PR 流水线、实际检查项登记、`master` 保护分支关联和反向验证，避免把“仓库有 CI 配置”误认为“Gitee 合并门禁已生效”。

## 验收项

- [ ] Gitee Go 流水线只对目标 `master` 的 PR 和合并后的 `master` 推送触发。
- [ ] 在实际 Gitee 执行环境中记录 Node、Python 和 Docker 能力，不因未知运行时而降级项目版本。
- [ ] PR 流水线至少运行后端测试、前端类型检查、前端测试和生产构建。
- [ ] Docker Compose 检查只在确认提供 Docker daemon 的执行资源中运行，或明确作为独立验收步骤。
- [ ] 流水线成功结果出现在 PR 检查项中，并被加入 `master` 保护分支必过门禁。
- [ ] 用故意失败 PR 验证合并被阻止，再用修复提交验证恢复可合并。
- [ ] 文档记录门禁名称、触发条件、运行时限制和已验证日期。

## Comments

- 现有 GitHub Actions 和 Gitee Go 调研不能替代实际 Gitee 开通、实跑和保护分支绑定。
- 分流标签：`ready-for-agent`
