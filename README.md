# 安装使用说明

适用项目：15分钟生活圈智能体检与规划助手。本文按当前 `2.3.0` 候选版的代码和配置编写。

第一次使用建议选择 **Docker 离线演示**：无需申请地图密钥，也无需在电脑上安装 Python、Node.js 或数据库。需要修改代码时，再选择本地开发方式。

## 一、获取代码并进入正确目录

安装 Git。Docker 方式还需要安装并启动 Docker Desktop（Windows 使用 WSL 2 后端），或在 Linux 安装 Docker Engine 和 Compose 插件。以下命令使用 `docker compose`，不使用旧版 `docker-compose`。

当前候选版开发在 `feature_pjj_1.0.0` 分支，克隆时明确指定分支：

```bash
git clone --branch feature_pjj_1.0.0 https://github.com/PengJunPJ/life-circle-assistant.git
cd life-circle-assistant
cd life-circle-assistant
```

这里两次 `cd` 是有意的：外层是 Git 仓库，内层才是应用目录。进入正确目录后，应能看到 `docker-compose.yml`、`.env.example`、`backend/` 和 `frontend/`。

如果已经克隆了仓库，在**仓库根目录**执行：

```bash
git switch feature_pjj_1.0.0
git pull --ff-only
cd life-circle-assistant
```

如果默认克隆到了 `main`，不要直接把它当作本文所述候选版；正式版本合并并发布后，可按维护者指定的分支或标签安装。

**版本可获取性说明（2026-10-12）：** 本地提交 `a654c24` 尚未推送；外部克隆只能获取远端已有提交，不能获取尚未推送的变更。本文本身也需要由维护者提交并推送后，才能随克隆获得。

## 二、方式 A：Docker 启动（推荐）

以下命令均在包含 `docker-compose.yml` 的**应用目录**执行。

### 1. 检查 Docker

```bash
docker --version
docker compose version
docker info
```

`docker info` 应正常返回服务端信息。如果提示无法连接 Docker daemon，先启动 Docker Desktop 或 Docker 服务。

### 2. 创建本地配置

macOS、Linux 或 Git Bash：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

已有 `.env` 时先检查内容，不要再次复制覆盖自己的配置。这里使用的是**应用目录的 `.env`**，不是外层仓库的 `.env.local`。

初次演示保留以下配置，其余保持模板默认值：

```dotenv
BAIDU_MAP_MODE=mock
BAIDU_MAP_AK=
BAIDU_MAP_SECRET=
VITE_BAIDU_MAP_AK=
VITE_API_BASE_URL=
AMAP_VALIDATION_ENABLED=false
LLM_ENABLED=false
```

Docker 模式下 `VITE_API_BASE_URL` 保持空值，由前端 Nginx 将 `/api` 转发到后端。第一次构建需要联网下载镜像及依赖；镜像构建完成后，离线快照分析无需请求地图服务。

### 3. 构建并启动

```bash
docker compose up --build --detach --wait
docker compose ps
```

正常情况下 `api` 和 `web` 都会显示为运行且健康。首次构建耗时取决于下载速度，不要在构建尚未完成时判断页面是否可用。

### 4. 打开页面并检查后端

- 使用入口：<http://localhost:5173>
- 后端健康检查：<http://localhost:8000/api/health>
- API 交互文档：<http://localhost:8000/docs>

离线模式的健康检查应包含 `"status": "ok"` 和 `"mode": "mock"`。页面应显示“本地快照”状态；没有百度真实底图是离线模式的正常表现。

### 5. 停止与再次启动

```bash
docker compose down
docker compose up --detach --wait
```

以上两条是停止、再启动的示例，按需要分别执行。修改代码或拉取更新后，重新使用 `docker compose up --build --detach --wait`。

历史报告与步行缓存保存在 Docker 的 `analysis-data` 命名卷中；普通 `down` 不会删除这些数据。不要为日常停止添加 `--volumes` 或 `-v`，它们会删除持久化数据。

## 三、第一次如何使用

1. 打开 <http://localhost:5173>，按页面引导查看当前数据来源。
2. 离线演示保留默认中心：广州市黄埔区红山街道海韵东路离线样例中心，BD-09 坐标为经度 `113.4872`、纬度 `23.1068`。离线快照不支持任意城市或任意地址，只支持样例中心周边约 1 公里；WGS84、GCJ-02 转换需要真实模式。
3. 首次可选择“快速分析”、15 分钟，选择需要体检的设施类别。菜市场、药店、小学、医疗服务参与盲区网格测算；养老、公园绿地、便利超市展示覆盖度和最近可达情况。
4. 点击“开始快照体检”，等待进度完成。系统不会仅因为打开页面就自动开始分析。
5. 查看等时圈、各类设施评分、正常覆盖区、设施稀疏区和重点服务盲区；点击设施可查看路线，结合数据质量说明理解结果。
6. 查看规划建议。在“新增设施改善模拟”中选择设施类别，使用建议候选点或“地图选点”，再点击“运行改善模拟”，查看模拟前后指标。
7. 在报告面板导出 JSON、CSV、GeoJSON 或 PDF。GeoJSON 中的坐标使用 BD-09，导入 GIS 工具时需要确认坐标口径。
8. 在历史报告列表打开已有报告，或使用原参数重新运行；选择两份历史报告可进行对比。
9. 使用报告解读功能获取摘要、类别优先级或模拟解读。默认由规则模板生成，不需要模型密钥；启用外部模型的方法见下文。

离线模式使用标记为合成样例的本地快照，部分路线采用明确披露的估算，结果用于演示和复现，不代表当前真实设施状况。“正式分析”是分析精度选项，**不会把 `mock` 自动切换成真实地图模式**。

## 四、切换真实百度地图（可选）

### 1. 准备两类凭证

在百度地图开放平台申请并配置：

- **服务端 Web 服务 AK**：用于地理编码、逆地理编码、地点检索、步行路线/步行矩阵及坐标转换。按项目调用的接口确认权限和配额；若应用采用签名校验，还需要匹配的 Secret。
- **浏览器端 JavaScript API AK**：用于加载百度底图。将实际使用的 `localhost`、`127.0.0.1` 或访问域名加入相应白名单。

两类 AK 用途不同。服务端 AK 和 Secret 仅供后端使用；浏览器 AK 会用于浏览器地图加载，应通过域名限制使用范围。

### 2. 编辑应用目录的 `.env`

以下是配置模板，替换中文占位值；不使用签名校验时 `BAIDU_MAP_SECRET` 留空。

```dotenv
BAIDU_MAP_MODE=real
BAIDU_MAP_AK=替换为服务端AK
BAIDU_MAP_SECRET=
VITE_BAIDU_MAP_AK=替换为浏览器端AK
BAIDU_MAP_QPS=1.5
AMAP_VALIDATION_ENABLED=false
```

QPS 按自己的控制台配额设置。真实模式会消耗接口额度，“快速分析”也会请求百度服务。

### 3. 让配置生效并验证

Docker 用户执行：

```bash
docker compose up --build --detach --wait
```

修改 `.env` 后使用 `up` 让 Compose 重新创建需要更新的容器；只执行 `restart` 不会更新 Compose 注入的环境变量。本地开发用户应停止并重新启动后端。

刷新页面，确认已配置真实模式，点击“验证 Web API”，再确认百度底图已加载。健康检查和状态页只说明配置情况；“验证 Web API”会调用一次地理编码服务，探测成功也不代表地点检索、步行接口和底图权限全部可用。最后在黄埔区选择中心并完成一次真实分析。

真实冷缓存分析可能需要数分钟，耗时取决于设施数量、网络、配额和分析精度。默认会在空缓存时导入随仓库提供的演示中心步行缓存种子，报告会披露缓存命中；这不意味着所有路线都是现场新请求。若需要现场测算，可设置 `LIFE_CIRCLE_SEED_WALKING_CACHE=0` 后使用新的独立数据存储；该开关只阻止启动导入，不会清除已存在的缓存。

当前支持范围仍是广州市黄埔区样例。高德辅助验证不是启动必需项，默认保持关闭。

## 五、方式 B：本地开发启动

不使用 Docker 时，需要自行安装 **Python 3.12** 和 **Node.js 22.22.2 或更新的 22.x**（也可使用符合 `frontend/package.json` 的 Node.js 24.15.0 或更新的 24.x），以及 npm。前端当前依赖不适合使用 Node.js 18、20 或早期 22.x。

先按第二部分创建应用目录的 `.env`，初次使用保留 `mock`。分别打开两个终端启动前后端，不要同时运行占用相同端口的 Docker 版本。

### 1. 终端 A：后端

从**应用目录**开始，macOS/Linux：

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Windows PowerShell 从**应用目录**开始：

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

PowerShell 方式直接使用虚拟环境解释器，无需修改脚本执行策略。后端会向上查找应用目录的 `.env`；已导出的同名环境变量优先于文件配置。保持此终端运行，可先打开 <http://localhost:8000/api/health> 确认启动成功。

本地开发的报告和缓存默认保存到 `backend/data/runtime/life-circle.db`，无需额外安装数据库。

### 2. 终端 B：前端

从**应用目录**开始：

```bash
cd frontend
npm ci
```

用编辑器在 `frontend/` 下创建 `.env.local`，写入：

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

然后运行：

```bash
npm run dev -- --port 5173 --strictPort
```

打开 <http://localhost:5173>。后端和前端终端都必须保持运行，停止时分别按 `Ctrl+C`。

本地 Vite 不会自动读取上一级应用目录的 `.env`，也没有配置 `/api` 代理，因此不要把 Docker 使用的空 `VITE_API_BASE_URL` 原样写入前端 `.env.local`。浏览器地图 AK 由后端 `/api/map/config` 提供，真实模式仍在应用目录 `.env` 配置。

### 3. 需要预览生产构建时

在前端目录执行：

```bash
npm run build
npm run serve
```

访问 <http://localhost:4173>，同时保持后端运行。应用目录 `.env` 中的 `CORS_ALLOW_ORIGINS` 需加入 `http://localhost:4173`（用逗号与已有来源分隔），并重启后端。`VITE_API_BASE_URL` 在构建时固化，修改后必须重新构建。

不要双击 `frontend/index.html` 或 `dist/index.html`，需要通过 HTTP 服务访问。

## 六、启用外部模型解读（可选）

默认 `LLM_ENABLED=false`，规则模板即可使用。已有兼容 Chat Completions 协议的模型服务时，可在应用目录 `.env` 中配置：

```dotenv
LLM_ENABLED=true
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=替换为模型服务的API基础地址
LLM_API_KEY=替换为模型服务密钥
LLM_MODEL=替换为服务支持的模型名称
```

Docker 用户重新执行 `docker compose up --detach --wait`；本地用户重启后端。模型用于左侧“用一句话发起体检”的需求提取、报告事实解读，以及报告内规划助手的工具选择。路线、盲区、评分和模拟仍由后端计算；配置缺失、请求失败或输出校验不合格时，会明确标注规则模式或降级。调用外部模型需要联网，会向该服务发送需求文本、上一轮参数、报告上下文及工具结果，并可能产生费用。

自然语言入口示例：“体检红山街道海韵东路，步行15分钟，关注买菜和买药”。点击“整理需求”，补充缺失信息并确认地址候选，核对可编辑的参数后点击“确认并开始体检”。也可明确使用“当前选点”。不配置模型也可以体验规则解析；离线模式仍只支持内置样例。详见 [自然语言体检入口说明](life-circle-assistant/docs/自然语言体检入口.md)。

完成体检后，在右侧“可解释 AI 规划助手”输入：“查一下菜市场盲区，再模拟新增一个菜市场”。助手会展示实际工具执行记录，模拟成功后同步地图和前后指标。工具问答要求模型服务支持原生 `tools` / `tool_calls` 协议；仅支持文本生成的兼容接口会降级。不启用模型时也可体验明确标注的规则工具流程。详见 [工具规划助手说明](life-circle-assistant/docs/工具规划助手.md)。

## 七、常见问题与检查步骤

| 现象 | 检查与处理 |
| --- | --- |
| 提示找不到 Compose 配置 | 当前目录必须包含 `docker-compose.yml`；确认进入了仓库内的应用子目录。 |
| Docker 无法连接服务端 | 启动 Docker Desktop/Engine，用 `docker info` 确认。 |
| 首次构建下载超时 | 检查能否访问镜像源、Python 包源和 npm 源；网络恢复后重试构建。首次安装不能完全离线。 |
| `8000` 或 `5173` 被占用 | 停止占用端口的旧进程；或在应用 `.env` 添加 `API_HOST_PORT=18000`、`WEB_HOST_PORT=15173` 后重新执行 Compose `up`，改访问 `http://localhost:15173` 和 `http://localhost:18000/api/health`。Docker 的内部代理无需修改。 |
| 页面空白 | 通过 HTTP 地址打开，不要双击 HTML；确认 `web` 已健康，并查看浏览器控制台。 |
| 页面能打开，接口请求失败 | Docker 检查 `api` 是否健康、前端 API 地址是否为空；本地开发检查后端 `8000` 是否运行、前端 `.env.local` 是否指向它。 |
| 本地访问出现 CORS 错误 | 页面地址的协议、主机、端口必须与后端 `CORS_ALLOW_ORIGINS` 中的一项完全一致；修改后重启后端。默认只允许 `localhost:5173` 和 `127.0.0.1:5173`。 |
| `npm ci` 提示 Node 版本不兼容 | 核对 `node --version`，使用上文指定版本，不用 `npm install` 替代锁文件安装。 |
| 仍显示本地快照 | 核对应用目录 `.env` 的 `BAIDU_MAP_MODE=real` 和服务端 AK；重新创建 Docker 容器或重启本地后端，并检查同名 shell 环境变量是否覆盖文件值。 |
| 真实底图没有加载 | 检查浏览器 AK 的应用类型、域名白名单和网络；底图加载与 Web 服务连通性需要分别验证。 |
| 搜索地址或确认坐标失败 | 离线使用默认中心或范围内 BD-09 坐标；任意地址和外部坐标转换需真实模式。黄埔区范围外暂不支持。 |
| 真实分析缓慢或返回部分结果 | 查看任务阶段、数据质量和服务日志，核对接口额度、权限、限流和超时；先降低分析精度，不要反复并发提交。 |
| 本地 PDF 中文显示异常 | Docker 镜像已包含中文字体；本地可安装文泉驿字体，或用 `LIFE_CIRCLE_PDF_FONT_PATH` 指向可被 ReportLab 加载的中文 TrueType 字体后重启后端。 |

Docker 用户可在应用目录查看状态和日志：

```bash
docker compose ps
docker compose logs --tail 100 api web
```

本地开发用户查看前后端终端输出。对外分享配置和日志前去除密钥；不要提交 `.env`、`.env.local` 或自己的运行数据库。

## 八、开发者验证（非普通使用的必需步骤）

如果需要修改代码，可在应用目录、已激活后端虚拟环境的终端安装开发依赖并运行检查：

```bash
python -m pip install -r backend/requirements-dev.txt
make quality
```

`make quality` 会运行后端与前端检查、构建及隔离端口的 Docker 冒烟测试，需要 `make`、Python、npm、Docker 和 Bash；后端测试还需要 `pdftotext` 及中文字体（Ubuntu/Debian 可安装 `poppler-utils` 和 `fonts-wqy-zenhei`）。Windows 建议在 WSL 中运行统一检查。它固定使用离线模式，无需地图密钥。

项目详细说明见 [应用 README](life-circle-assistant/README.md)，候选版范围与限制见 [V2.3.0 发布说明](life-circle-assistant/docs/releases/v2.3.0.md)。
