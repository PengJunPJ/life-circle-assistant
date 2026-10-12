# 2026-10-12 依赖许可证证据复核

已逐包整理 440 条组件记录（不同范围可能重复），4 条缺少许可证声明。

`declaration-found` 表示元数据有声明；不代表通知义务已全部履行、法律相容性已获批准或地图服务授权已完成。

前端 SBOM 包含已安装包的许可证文本证据；Python 使用固定版本 PyPI 元数据；镜像使用 Trivy 软件包声明。

完整条目和证据见 [JSON](license-review-20261012.json)。

| SBOM | 组件数 |
| --- | ---: |
| [ api-image-20261012.cdx.json ](sbom/api-image-20261012.cdx.json) | 74 |
| [ backend-development-20261012.cdx.json ](sbom/backend-development-20261012.cdx.json) | 33 |
| [ backend-production-20261012.cdx.json ](sbom/backend-production-20261012.cdx.json) | 26 |
| [ frontend-20261012.cdx.json ](sbom/frontend-20261012.cdx.json) | 235 |
| [ web-image-20261012.cdx.json ](sbom/web-image-20261012.cdx.json) | 72 |

待人工确认：第三方地图/模型服务条款；打包分发的通知义务；以下缺少声明的组件。

| 范围 | 组件 | 版本 |
| --- | --- | --- |
| api-image-20261012.cdx.json | alpine | 3.24.2 |
| api-image-20261012.cdx.json | .python-rundeps | 20261001.215423 |
| frontend-20261012.cdx.json | config-chain | 1.1.13 |
| web-image-20261012.cdx.json | alpine | 3.24.2 |
