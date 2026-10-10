# 前端安全审计报告

## 执行摘要

审计日期：2026-10-09。范围为 Vue 3/Vite 前端源码、构建配置、Nginx 生产配置、npm 依赖、敏感信息暴露面和本地只读运行态。结论：未发现已确认的凭据泄露、认证绕过、业务 XSS、开放重定向或生产 source map；npm 与 Python 依赖审计均为 0 个已知漏洞。

结构化问题：Critical 0，High 0，Medium 1，Low 0。Medium 项是浏览器地图 AK 的设计性暴露面，必须依靠域名白名单和配额控制。生产 Nginx 的基础安全响应头已补齐，并由容器冒烟重新验证。

## 审计范围

- Vue 组件、composables、API 服务、Vite 配置和 Nginx 配置。
- 排除 node_modules、dist、原型 HTML 和第三方生成物的噪音；生产 dist 仍检查是否有 source map。
- 运行态使用 Vite preview 绑定 `127.0.0.1`，仅执行 GET 只读检查。

## 已确认问题

### Medium：浏览器百度 AK 依赖域名白名单

证据：[frontend/src/composables/useMapRenderer.ts](../frontend/src/composables/useMapRenderer.ts) 417-423。浏览器端地图 SDK 需要 AK，这是预期架构，不是后端 Secret 泄露。若控制台白名单过宽，第三方可复制该公开 AK 消耗额度。整改为精确域名白名单、配额和告警，并在凭据曾外传时轮换。

### 已修复：生产安全响应头

证据：[frontend/nginx.conf](../frontend/nginx.conf) 1-9。已加入 `X-Content-Type-Options: nosniff`、`X-Frame-Options: SAMEORIGIN`、`Referrer-Policy` 和 `Permissions-Policy`。未直接加入 CSP，因为百度地图 SDK 的脚本、连接和底图域名需要按实际部署域名逐项白名单；后续可在网关层补充经过验证的 CSP。

## 未发现项

- `frontend/src` 未发现 `v-html`、`innerHTML`、`outerHTML`、`insertAdjacentHTML`、`postMessage`、`window.open` 或动态重定向业务入口。
- `localStorage` 只保存主题和首次使用引导状态，不保存认证令牌或权限信息；项目未发现前端认证流程。
- Vite 生产构建未生成 `.map`；不存在可访问的配置脚本、证书或安装包。
- 未发现前端上传、WebSocket、Socket.IO、SIP 或压缩包处理入口。

## 依赖与构建证据

详见 [dependency-audit.json](dependency-audit.json) 和 [build-audit.json](build-audit.json)。`npm audit --audit-level=high`、Python 生产/开发 `pip-audit`、前端 lint/typecheck/test/build、后端 Ruff/pytest、Docker 健康检查和离线 PDF 冒烟均通过。

## 限制

本次未连接真实百度账号验证控制台白名单、配额和计费策略，也未对生产公网域名做动态扫描；这两项需部署前人工确认。前端不承担后端授权，若未来增加登录/多租户功能，必须新增后端授权审计。

## 产物

- [audit-dashboard.html](audit-dashboard.html)
- [findings.json](findings.json)
- [framework-inventory.json](framework-inventory.json)
- [build-audit.json](build-audit.json)
- [dependency-audit.json](dependency-audit.json)
- [secret-scan.json](secret-scan.json)
