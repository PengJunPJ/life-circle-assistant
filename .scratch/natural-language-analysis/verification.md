# 验证记录

日期：2026-10-12。

## 实际执行结果

| 检查 | 结果 |
| --- | --- |
| 后端 `LLM_ENABLED=false .venv/bin/python -m pytest -q` | 162项通过，0跳过；一个已有 Starlette 弃用警告 |
| 后端 `ruff check app tests` | 通过 |
| 本次后端改动 `ruff format --check` | 通过 |
| 前端 `npm run typecheck` | 通过 |
| 前端 `npm run lint` | 通过 |
| 前端 `npm test` | 17个文件、58项通过 |
| 前端 `npm run build` | 生产构建通过 |
| `git diff --check` | 通过 |
| 桌面1440×1000、深色 | 补充地点、改为20分钟、确认启动、报告显示成功 |
| 移动390×844、浅色 | 同一链路成功；对话区域无横向溢出 |

浏览器分别检查了确认前0次、确认后1次 `/api/analyze` 请求，实际请求时间20分钟、设施为药店与医疗服务；草稿激活时手工启动按钮隐藏。没有浏览器运行时异常。

## 环境与限制

本机使用 Python 3.11.1、Node.js 22.17.0、Ruff 0.16.10、pytest 9.1.1、pytest-asyncio 1.4.0。仓库推荐部署版本仍以安装文档为准，本记录不等于已在全部推荐运行时上复测。

初次全量测试因虚拟环境缺少异步测试插件跳过3项既有测试；安装仓库开发依赖中声明的插件后，全量测试无跳过。随后扩大模型测试发现未经用户表达选择当前选点的验证顺序问题，已将校验移到草稿合并之前，并在最终全量测试中通过。

模型测试使用模拟提供方验证正常提取、地址溯源、结构错误、空输出与异常降级；未访问外部模型，未验证真实服务连通性、计费或实际语义表现。地图和浏览器测试均使用离线快照；不能视为真实社区测算或实地步行核验。

## 浏览器复现

脚本：[browser-smoke.mjs](browser-smoke.mjs)。需安装 Chrome 与前端依赖，先启动隔离后端8017端口、前端5177端口：后端设置 `BAIDU_MAP_MODE=mock`、`LLM_ENABLED=false`、`AMAP_VALIDATION_ENABLED=false`、独立的 `LIFE_CIRCLE_DATABASE_PATH`、`CORS_ALLOW_ORIGINS=http://127.0.0.1:5177`；前端设置 `VITE_API_BASE_URL=http://127.0.0.1:8017`，以5177端口运行 Vite。然后从仓库根目录运行：

```bash
node .scratch/natural-language-analysis/browser-smoke.mjs
```

脚本在系统临时目录保存截图，输出实际路径与验证结果；使用隔离数据库，避免给开发报告历史写入测试记录。
