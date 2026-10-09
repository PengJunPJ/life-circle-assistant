# GitHub CI/CD 落地手册

本项目的自动化配置位于：

- `.github/workflows/quality.yml`：后端、前端、容器检查，以及统一的 `质量门禁汇总`；
- `.github/workflows/security.yml`：CodeQL、依赖漏洞和密钥扫描；
- `.github/workflows/release.yml`：`vX.Y.Z` 标签发布、GHCR 镜像、GitHub Release；
- `.github/dependabot.yml`：Python、npm、Docker 和 Actions 依赖更新。

## 1. 主分支保护

在 GitHub 仓库 `Settings -> Branches -> Add branch ruleset`（或 Branch protection rule）中，为 `main` 配置：

1. 要求 Pull Request，禁止直接推送；
2. 要求至少 1 名 Reviewer；
3. 要求分支与 `main` 最新提交同步；
4. 要求状态检查通过，选择 `质量门禁汇总`；
5. 要求解决全部 review conversation；
6. 禁止 force push 和删除分支；
7. 管理员也遵守规则。

先创建一个测试 PR 并等待 workflow 成功，再选择状态检查。检查名称必须使用 GitHub 实际显示的 `质量门禁汇总`，不要只选择内部 job id。

`CodeQL 静态分析`、`密钥泄露扫描` 和 PR 上的 `PR 依赖变更审查` 可以纳入必需检查。全量 `Python 依赖漏洞扫描` 与 `npm 依赖漏洞扫描` 当前会上传 JSON 报告并告警，不因已存在的历史漏洞直接阻断；这是临时收敛策略，待 Dependabot 升级 PR 清理现有漏洞后，再把两项扫描改为阻断。

当前安全债务包括：后端 `pypdf`、`starlette`、`python-dotenv` 及测试依赖版本偏旧，前端 Vitest/ECharts 传递依赖存在上游安全公告。不要直接执行 `npm audit fix --force` 或跨 FastAPI/Vitest/ECharts 大版本升级；应由 Dependabot 逐个 PR 升级，并通过完整 `make quality` 与人工回归后合并。

## 2. GHCR 和发布

推送形如 `v2.3.0` 的标签会触发发布 workflow。它会：

1. 校验标签格式和 `life-circle-assistant/VERSION` 完全一致；
2. 执行 `make -C life-circle-assistant quality`；
3. 构建并推送两个 GHCR 镜像；
4. 生成 SBOM 和 provenance；
5. 创建 GitHub Release。

镜像名称为：

```text
ghcr.io/pengjunpj/life-circle-assistant-api:vX.Y.Z
ghcr.io/pengjunpj/life-circle-assistant-web:vX.Y.Z
```

在仓库 `Settings -> Actions -> General` 保持允许 Actions 创建和写入 packages。第一次发布后，到 GHCR package 设置中确认可见性和仓库关联。生产部署应使用不可变版本标签，不应只依赖 `latest`。

## 3. Environment 与生产部署

当前配置只负责构建制品和发布 Release，没有假设具体云厂商或服务器。确定部署平台后再配置：

- `staging` Environment：自动部署和冒烟验证；
- `production` Environment：配置 Required reviewers，发布前人工批准；
- 生产 API 密钥只放在 `production` Environment，不放在仓库级 Secrets；
- PR 和普通 CI 继续使用 `BAIDU_MAP_MODE=mock`，不消耗真实地图配额。

生产部署目标（Docker Compose、Kubernetes 或云容器平台）确定前，不要把 SSH 私钥、云 Token 或真实百度/LLM 密钥加入 Actions。

## 4. 发布前核对

- `VERSION`、前端 `package.json` 和变更日志版本一致；
- 测试 PR 的成功、失败、修复恢复流程均验证过；
- `main` 保护规则已绑定 `质量门禁汇总`；
- GHCR package 权限和可见性已确认；
- 发布标签指向已通过门禁的 commit；
- staging 冒烟成功后才允许 production 部署。
