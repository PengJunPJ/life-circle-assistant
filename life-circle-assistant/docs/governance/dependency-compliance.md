# 依赖合规清单

本清单用于工程审计和发布前复核，不构成法律意见。许可证信息应以各组件发布包、仓库 NOTICE 和官方元数据为准；无法确认时保持 `needs-review`，不得凭名称推断许可证。

## 直接依赖与运行时组件

| 组件 | 版本来源 | 用途 | 许可证状态 | 直接/间接 | 证据 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| Python 生产包 | `backend/requirements.txt` | API、HTTP、配置、PDF | 逐包核对官方元数据 | 直接 | requirements + PyPI 元数据 | needs-review |
| Python 开发包 | `backend/requirements-dev.txt` | 测试、格式检查、PDF 断言 | 逐包核对官方元数据 | 直接/继承生产 | requirements-dev | needs-review |
| npm 生产包 | `frontend/package.json` + `package-lock.json` | Vue、Element Plus、ECharts | 逐包核对 npm license/NOTICE | 直接/间接 | package-lock | needs-review |
| npm 开发包 | `frontend/package.json` + `package-lock.json` | Vite、Vitest、TypeScript、ESLint | 逐包核对 npm license/NOTICE | 直接/间接 | package-lock | needs-review |
| Python 基础镜像 | `backend/Dockerfile` | API 运行时 | Alpine/Python 镜像及系统包需单独核对 | 运行时 | Dockerfile、镜像 manifest | needs-review |
| Node 构建镜像 | `frontend/Dockerfile` | 前端构建 | Alpine/Node 镜像及系统包需单独核对 | 构建时 | Dockerfile、镜像 manifest | needs-review |
| Nginx 基础镜像 | `frontend/Dockerfile` | 静态文件服务 | Alpine/Nginx 镜像及系统包需单独核对 | 运行时 | Dockerfile、镜像 manifest | needs-review |
| GitHub Actions | `.github/workflows/*.yml` | CI、安全、发布 | 各 Action 仓库许可证和版本需复核 | 供应链工具 | workflow 文件 | needs-review |

`package-lock.json` 是前端实际解析版本的唯一安装口径；Python requirements 是直接依赖口径，传递依赖应以安装环境或 SBOM 为准。Dockerfile 中的 tag 不是完整软件物料清单，发布前应按 digest 扫描。

## 已有工程证据

- Python 漏洞审计：`python3 -m pip_audit -r backend/requirements.txt` 和开发依赖命令，见 `docs/contest/dependency-audit-2026-10-09.md`。
- npm 漏洞审计：`npm audit --audit-level=high`，使用官方 npm registry。
- CodeQL、Dependency Review、Gitleaks：见 `.github/workflows/security.yml`。
- Dependabot：`.github/dependabot.yml` 覆盖 pip、npm、Docker 和 GitHub Actions。
- 发布镜像：`.github/workflows/release.yml` 使用 Docker Buildx 的 SBOM/provenance 选项；容器扫描脚本为 `scripts/container-audit.sh`，命令入口为 `make container-audit`。

2026-10-11 的首次容器审计归档于 `docs/contest/container-audit-2026-10-11.md`；修复和双扫描器复验见 `docs/contest/container-audit-remediation-2026-10-11.md`。API/Web 最终运行镜像在 Trivy 和 Grype 中均为 0 Critical / 0 High，发布门禁通过。原始基础镜像及不发布的 Node 构建阶段仍有发现，处置边界和残余风险已在复验记录中保留。漏洞扫描通过只表示当前数据库快照下未发现目标级别漏洞，不表示未来无漏洞，也不替代许可证、服务条款和数据授权审查。

## 外部服务合规边界

百度地图、高德地图和可选 OpenAI-compatible API 不属于 Apache-2.0 项目依赖。它们各自的开发者协议、配额、归属标识、缓存、再分发和数据留存规则优先于本项目文档。高德 Key 只用于认证，不代表可将原始 POI 写入仓库、长期缓存或公开展示；当前高德状态是辅助观察、默认关闭、书面许可待确认。

## 发布前检查

1. 核对直接和传递依赖的 SPDX/许可证与 NOTICE；未知项标记 `needs-review`。
2. 运行 pip-audit、npm audit 和 Docker Trivy/Grype，并保存版本、日期、镜像 digest。
3. 生成 SPDX 或 CycloneDX SBOM，确认不含 `.env`、Key、数据库、原始地图响应。
4. 复核 GitHub Actions 权限、第三方 Action 版本和仓库许可证。
5. 复核地图/模型服务条款、公开展示范围和数据删除方式。
