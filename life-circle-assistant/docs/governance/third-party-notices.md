# 第三方声明

本文件列出项目已知的第三方代码、构建物和外部服务类别。完整传递依赖清单以锁文件、安装环境 SBOM 和发布附件为准；具体许可证未完成逐包核对时不得从本文件推断已获法律确认。

## 项目自身

本项目代码以 Apache License 2.0 发布，详见仓库根目录 [`LICENSE`](../../LICENSE)。Apache-2.0 不授予第三方地图或模型数据的再分发权。

## 软件与构建物

- Python 直接依赖来自 `backend/requirements.txt`，开发和测试依赖来自 `backend/requirements-dev.txt`。
- 前端直接依赖来自 `frontend/package.json`，实际解析版本来自 `frontend/package-lock.json`。
- Docker 基础镜像来自 `backend/Dockerfile` 和 `frontend/Dockerfile`；镜像内 Debian/Alpine、Python、Node、Nginx 和系统包需要按发布 digest 另行核对。
- GitHub Actions 来自 `.github/workflows/` 中声明的官方或社区 Action；其许可证、版本和权限应在发布前复核。

依赖许可证、NOTICE、漏洞和 SBOM 状态见 [依赖合规清单](dependency-compliance.md)。

## 外部地图和模型服务

- 百度地图 Web 服务和 JavaScript 地图：仅按百度开发者协议、配额、归属标识、缓存和数据使用规则调用。
- 高德地图 Web 服务：当前仅为默认关闭的辅助验证观察源。Key 不等于数据留存或公开展示许可；未取得书面许可前不提交原始 POI、地址、坐标、ID、响应或截图，不将高德结果计入百度主评分。
- OpenAI-compatible API：可选的报告文字增强服务。模型 Key、提示上下文和返回内容不得写入仓库；调用方需自行确认服务商的隐私、留存和再处理条款。

外部服务条款可能变化，发布前应重新核对官方页面并在证据索引中记录核查日期。工程扫描和本声明不是法律意见。
