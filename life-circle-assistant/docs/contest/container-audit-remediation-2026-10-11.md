# 容器 Critical/High 漏洞处置记录（2026-10-11）

## 结论

API 与 Web 最终运行镜像经 Trivy `0.75.0` 和 Grype `0.120.1` 复扫，均为 **0 Critical / 0 High**。发布门禁 `no-high-or-critical` 通过，原始 JSON、镜像检查结果、扫描器版本和数据库状态归档于 [audit-results/container/2026-10-11-remediated](../../audit-results/container/2026-10-11-remediated/)。

这表示当前数据库快照下，最终运行镜像没有被两个扫描器判定为 Critical/High 的已知漏洞；不表示未来无漏洞，也不覆盖部署配置、业务逻辑或许可证结论。

## 处置措施

- API 从 `python:3.12.14-slim` 迁移到 `python:3.12.15-alpine`，构建时执行 Alpine 安全更新并安装中文字体。
- 前端构建环境从 `node:22.22.2-alpine` 升级到 `node:22.23.2-alpine`，升级 Alpine 包和 npm `12.2.0`。
- Nginx 最终阶段构建时执行 Alpine 安全更新，修复 `pcre2`、`tiff`、`zlib`、`libexpat` 和 OpenSSL 等系统包发现。
- 审计脚本固定使用 Trivy 官方 GHCR 数据库源，修正严重级别汇总，并在 API/Web 运行镜像存在可修复 Critical/High 时返回非零状态。

## 前后对比

| 发布镜像 | 处置前 Grype | 处置后 Grype | 处置后 Trivy |
| --- | ---: | ---: | ---: |
| API | 1 Critical / 75 High | 0 Critical / 0 High | 0 Critical / 0 High |
| Web | 0 Critical / 12 High | 0 Critical / 0 High | 0 Critical / 0 High |

处置后镜像 ID：

- API：`sha256:5c53979f691634adef0f2ac16fe0d2aaf5420fcfe63674c1f18c98123ea3a015`
- Web：`sha256:354e5998a44e7d38d0e46f6919303b5393919fa72a5600a15ec8e4057b0ffeb5`

## 基础镜像和构建阶段边界

原始基础镜像仍完整扫描，不把 Dockerfile 中的后续升级层倒推成基础镜像本身无漏洞：

| 对象 | Critical / High（Grype） | 处置方式 |
| --- | ---: | --- |
| `python:3.12.15-alpine` | 0 / 1 | API 构建层执行 `apk upgrade` 后，最终镜像为 0 / 0 |
| `node:22.23.2-alpine` | 1 / 22 | 仅用于构建；升级系统包和 npm，最终 Web 镜像不包含 Node/npm |
| `nginx:1.31-alpine` | 0 / 12 | Web 构建层执行 `apk upgrade` 后，最终镜像为 0 / 0 |

升级后的前端构建阶段为 0 Critical / 4 High。其中 3 项来自 npm `12.2.0` 内置的 `undici`/`brace-expansion`，底层包虽已有修复版本，但截至本次扫描 npm 尚未发布整合版本；另 1 项 `http-cache-semantics` 尚无修复。该阶段不进入发布镜像，Dockerfile 不接收秘密挂载，风险暂按构建期残余风险接受，并在 npm 后续版本整合修复后升级。不得据此宣称全部基础镜像或构建供应链“零漏洞”。

## 复现命令

```bash
docker build -t life-circle-audit-api:latest backend
docker build -t life-circle-audit-web:latest frontend
make container-audit
```

如需同时审计构建阶段，先使用 `--target build` 构建并设置 `WEB_BUILD_IMAGE`。发布前必须使用最新漏洞数据库重新执行，不能永久复用本次结论。
