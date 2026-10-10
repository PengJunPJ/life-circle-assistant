# SBOM 生成说明

SBOM 用于回答“本次发布包含哪些软件物料”，不等于许可证或漏洞已经自动合规。发布附件不得包含 `.env`、API Key、数据库、原始地图响应或用户数据。

## 推荐格式

优先使用 SPDX 或 CycloneDX，并保存生成日期、工具版本、源码提交、镜像 digest 和扫描范围。前端以 `frontend/package-lock.json` 为锁定输入；Python 以两个 requirements 文件和实际安装环境为输入；Docker API 与 Web 镜像分别生成，不要只用源码清单代替镜像清单。

## 本地示例

工具未安装时不要伪造结果，先记录安装版本和失败原因：

```bash
# Node 依赖（需安装 cyclonedx-npm）
cd frontend && cyclonedx-npm --output-format json --output-file ../docs/governance/sbom/frontend.cdx.json

# Python 环境（需安装 cyclonedx-bom）
cd backend && cyclonedx-py requirements -i requirements.txt -o ../docs/governance/sbom/backend.cdx.json

# 镜像（需安装 syft）
syft <image>@<digest> -o cyclonedx-json=docs/governance/sbom/<image>.cdx.json
```

正式发布工作流已在 GHCR 构建中启用 Docker Buildx 的 `sbom: true` 和 `provenance: true`。仍需在发布记录中保存镜像 digest，并在目标环境使用 Trivy 或 Grype 复核 CVE。

## 审计规则

审计输入和 SBOM 生成不能读取或上传 `.env`。许可证未知、镜像未按 digest 固定、第三方 Action 未核对或外部 API 条款未确认时，状态保持 `needs-review`。
