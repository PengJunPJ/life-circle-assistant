# 容器镜像漏洞审计记录（2026-10-11）

## 范围与口径

本次审计覆盖本地已构建的应用镜像和 Dockerfile 中的三个基础镜像。Grype 使用本机有效的 Anchore 数据库 `v6.1.10`（构建时间 2026-10-10T06:30:01Z）；Trivy 使用 `0.75.0`，但数据库下载因当前网络无法连接 `mirror.gcr.io` 而失败，因此没有把 Trivy 失败写成“无漏洞”。镜像 digest、原始 JSON、版本、数据库状态和日志见 [归档目录](../audit-results/container/2026-10-11/)。

扫描命令：

```bash
API_IMAGE=life-circle-audit-api:20261010 \
WEB_IMAGE=life-circle-audit-web:20261010 \
CONTAINER_AUDIT_OUTPUT_DIR=./audit-results/container/2026-10-11 \
CONTAINER_AUDIT_ALLOW_SCANNER_FAILURE=1 \
./scripts/container-audit.sh
```

## 结果摘要

| 镜像 | 镜像 ID | Grype Critical | Grype High | Grype Medium | Trivy |
| --- | --- | ---: | ---: | ---: | --- |
| `life-circle-audit-api:20261010` | `sha256:a45b8d3c...` | 1 | 75 | 81 | 数据库下载失败 |
| `life-circle-audit-web:20261010` | `sha256:772af2fe...` | 0 | 12 | 16 | 数据库下载失败 |
| `python:3.12.14-slim` | `sha256:8630ab77...` | 1 | 70 | 78 | 数据库下载失败 |
| `node:22.22.2-alpine` | `sha256:dd9b0226...` | 7 | 57 | 41 | 数据库下载失败 |
| `nginx:1.31-alpine` | `sha256:a2b80c42...` | 0 | 12 | 16 | 数据库下载失败 |

Grype 结果包含固定、未修复、未知和 `wont-fix` 状态；本表只展示严重性计数，不能替代逐项处置。当前结果明确存在 Critical/High 漏洞，不能作为发布通过证据。应先升级或更换受影响基础镜像/包，重新构建应用镜像，再用更新数据库复扫。

## Trivy 重跑条件

在可访问 Trivy OCI 数据库的网络环境中执行同一命令，去掉 `CONTAINER_AUDIT_ALLOW_SCANNER_FAILURE=1`，确认五个镜像均生成非空 `*.trivy.json` 后，才可更新本记录的 Trivy 结论。Grype 数据库也应在发布前更新并重新归档。审计仅是工程证据，不替代许可证、供应商条款或部署环境配置复核。
