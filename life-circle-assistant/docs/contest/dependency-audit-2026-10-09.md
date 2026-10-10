# 依赖漏洞审计记录（2026-10-09）

## 范围与结果

使用官方 npm registry 审计候选版本锁文件，并分别审计 Python 生产和开发依赖。

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| Python 生产依赖 | `python3 -m pip_audit -r backend/requirements.txt` | 0 个已知漏洞，退出码 0 |
| Python 开发依赖（含生产依赖） | `python3 -m pip_audit -r backend/requirements-dev.txt` | 0 个已知漏洞，退出码 0 |
| npm 全部依赖 | `npm_config_registry=https://registry.npmjs.org npm audit --audit-level=high` | Critical 0、High 0、Moderate 0、Low 0，退出码 0 |

审计针对 2026-10-09 的公开漏洞数据库快照；不能推出依赖未来不会出现新漏洞。CI 和发布工作流都执行阻断式审计，并由 Dependabot 提交升级候选。

## 变更

- Python 生产依赖只保留运行时包；pytest、pypdf、ruff 移至开发依赖清单。
- 升级 FastAPI、Uvicorn、Pydantic、python-dotenv、pytest、pypdf、Ruff，以及 ECharts、Element Plus、Vite、Vitest、jsdom、vue-tsc 等前端依赖。
- 前端统一使用 `package-lock.json` 与 `npm ci`；锁文件 tarball 地址统一为 `registry.npmjs.org`，移除不同步的 pnpm 锁文件。
- Python 生产/开发扫描和 npm high/critical 扫描失败均阻断 CI 与标签发布工作流。

## 限制

- 本记录只覆盖 Python requirements 和 npm 锁定依赖，不包含 Docker 基础镜像的 CVE 数据库扫描；容器按版本标签锁定并在构建/冒烟中验证，但尚未执行 Trivy/Grype 镜像漏洞扫描。
- GitHub Actions 工作流配置已更新，远端运行结果需以 GitHub Actions 实际执行记录为准。
