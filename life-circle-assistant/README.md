# 15分钟生活圈智能体检与规划助手

面向广州市黄埔区社区规划场景的开源空间分析工具。系统基于真实步行可达性，生成 15 分钟等时圈，统计菜市场、药店、小学和医疗服务覆盖情况，并识别重点服务盲区与设施稀疏区。

## 快速运行

```bash
cp .env.example .env
docker compose up --build
```

日常开发建议保持 `.env` 的 `BAIDU_MAP_MODE=mock`，系统会优先读取 `backend/data/baidu_snapshot.json`，不会请求百度 Web 服务，也不会加载百度 JavaScript 地图，从而减少 API 额度消耗。需要联调真实数据时再切换为 `real`。

打开 <http://localhost:5173>。本地快照模式下使用离线数据；真实模式需要同时配置服务器端 `BAIDU_MAP_AK` 和浏览器端 `VITE_BAIDU_MAP_AK`。

当百度 Web 服务恢复可用后，可执行以下命令抓取一次真实体检报告并更新本地快照；抓取失败不会覆盖旧文件：

```bash
BAIDU_MAP_MODE=real PYTHONPATH=backend backend/.venv/bin/python backend/scripts/cache_baidu_snapshot.py
```

不要直接双击 `frontend/index.html`。该文件是 Vite 源码入口，使用 `file://` 打开时浏览器会拦截 `/src/main.ts` 等 ES module 请求，页面会显示空白。请使用上面的开发服务器，或先构建再通过 HTTP 静态服务器访问：

```bash
cd frontend
npm run build
npm run serve
```

然后打开 <http://localhost:4173>。

## 本地开发

后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

如果 `.env` 位于项目根目录，后端会自动读取其中的百度地图配置；也可以在启动前通过 shell 环境变量导出 `BAIDU_MAP_AK`。

## 模式

- `mock`：读取本地百度数据快照，适合开发、测试和离线演示，不消耗百度地图 API 额度。
- `real`：调用百度地图地理编码、POI、步行路线 Web 服务，并加载百度地图 JavaScript 底图。

真实模式需要同时满足：百度 Web 服务 AK 已开通地理编码、地点检索和步行路线权限；浏览器端 AK 已将 `localhost` 或实际访问域名加入域名白名单。`BAIDU_MAP_SECRET` 只在后端使用，不会返回给浏览器。

## 测试

```bash
cd backend
pytest
```

项目文档、领域术语和架构决策位于上级 `docs/` 目录。
