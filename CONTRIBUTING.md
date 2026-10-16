# 贡献指南

感谢参与 `life-circle-assistant`。本项目是功能型 Beta，贡献必须保持结果可解释、凭证不泄露、外部数据授权边界清晰。

## 开始开发

```bash
cd life-circle-assistant
cp .env.example .env
make quality
```

离线质量检查使用 `BAIDU_MAP_MODE=mock` 和仓库内快照，不需要地图 Key。后端、前端和容器的单项检查也可分别运行：`make backend-check`、`make frontend-check`、`make container-check`。

## 分支与提交

- 从目标分支创建短生命周期分支，建议使用 `codex/`、`feature/`、`fix/` 或 `docs/` 前缀。
- 每个提交聚焦一个可审查的目的，提交信息使用中文动词开头并说明影响范围，例如 `feat: 完善百度地图降级处理`。
- 不要把 `.env`、数据库、构建产物、真实 API 响应、原始地图 POI、坐标或用户数据提交到仓库。

## Pull Request 要求

PR 描述至少包含：变更目的、影响模块、测试命令及结果、数据/隐私影响、是否改变报告契约，以及是否需要更新赛事证据或限制披露。

代码变更应通过 `make quality`。依赖、Docker 基础镜像或 GitHub Actions 变更还应运行 `make dependency-audit`，并更新 `life-circle-assistant/docs/governance/dependency-compliance.md` 或对应审计记录。

涉及百度或高德的请求、缓存、导出、展示和字段变更时，必须检查服务条款、配额、坐标系、留存和公开展示边界。高德当前只允许默认关闭的辅助观察；没有书面许可，不得新增原始高德数据 fixture 或公开展示高德 POI。

文档变更应同步更新链接、证据索引和限制披露。新增验证数据必须使用最小化、可审计且不含凭证的 fixture，并注明采集时间、来源角色和人工复核状态。

## 评审重点

维护者会重点检查：测试是否覆盖失败和降级路径、报告是否诚实披露来源、是否把同源一致性误写成准确率、是否引入未授权数据留存，以及依赖许可证和漏洞状态是否有证据。

本项目目前未启用 DCO 或强制签名提交；贡献者仍须确认自己有权提交变更及其附带材料。
