# 评审一键演示指南

需要安装并启动 Docker Desktop（Windows 使用 WSL 2），或 Docker Engine 和支持 `up --wait` 的 Compose 插件。macOS/Linux 可直接使用 Bash；Windows 在 WSL 中执行以下命令。无需安装 Python、Node.js 或数据库，也无需地图和模型密钥。

## 从源码一键启动

在仓库根目录或内层 `life-circle-assistant/` 应用目录执行：

```bash
bash demo.sh
```

脚本会编译前后端、等待健康检查、生成沙涌长盛花园的 15 分钟七类设施示例报告，验证分析、JSON/CSV/PDF/WGS84 GeoJSON 导出、角色报告和前端同源代理，最后输出访问地址。再次启动会复用匹配的已有示例报告。首次编译需要联网下载基础镜像及依赖；后续离线分析不调用地图和模型服务。

默认页面为 <http://localhost:5173>，接口文档为 <http://localhost:8000/docs>。打开页面后可从历史报告查看已生成的样例，也可以按默认参数点击“开始快照体检”。示例为明确标注的离线合成数据，用于复现流程，规则解读不代表外部模型能力。

演示使用独立的 `docker-compose.demo.yml`、`demo.env`、`life-circle-demo` 项目及其数据卷，固定关闭外部服务，不读取或修改开发用 `.env`。现有部署占用默认端口时，可在运行前编辑应用目录 `demo.env`，或为每次命令设置相同的端口：

```bash
DEMO_WEB_PORT=15173 DEMO_API_PORT=18000 bash demo.sh
```

`DEMO_PROJECT_NAME` 可指定另一套演示项目；之后的测试、停止等命令须保持相同项目名。端口调整仅影响宿主机访问，不影响容器内同源代理。

## 自动测试、日志与停止

```bash
bash demo.sh test
bash demo.sh logs
bash demo.sh stop
```

`test` 对运行中的演示执行完整链路测试，会新增一份样例报告；失败时返回非零退出码。它不替代开发质量门禁 `make quality`。`stop` 只停止并移除演示容器，保留历史报告和数据卷。重新执行启动命令即可恢复。

若提示无法连接 Docker，先启动 Docker 服务；若提示端口被占用，调整 `demo.env` 或使用上述端口变量；若构建下载失败，检查镜像仓库／依赖源网络，或使用维护者提供的离线包。演示验证失败后容器保留，可用 `logs` 排查。

## 维护者制作离线包

在完整源码仓库中执行：

```bash
bash demo.sh package
```

默认生成应用目录 `dist/life-circle-demo.tar.gz`，包含前后端镜像、启动脚本、专用配置、冒烟脚本、版本、架构信息、许可证及本指南，不包含个人 `.env`、凭证和运行数据库。打包会重新构建当前源码，需要联网或已有完整构建缓存。已存在的包不会被覆盖，可传入新路径：

```bash
bash demo.sh package /path/to/life-circle-demo-amd64.tar.gz
```

离线包包含制作机器上构建的 Linux 镜像架构，详见包内 `images-info.txt`。评审 Docker 须支持该架构。建议提前确认评审机器，在对应的 AMD64 或 ARM64 环境制作并验证包；修改文件名不会改变镜像架构。

## 评审使用离线包

收到包后，在任意目录解压并执行：

```bash
tar -xzf life-circle-demo.tar.gz
bash life-circle-demo/demo.sh load
```

`load` 自动导入同目录 `images.tar`，以 `--no-build --pull never` 启动，再准备示例和验证链路；无需联网、源码、Python 或 Node.js。后续离线重启仍执行 `load`。也可传入镜像归档路径：`bash life-circle-demo/demo.sh load /path/to/images.tar`。

解压后的目录不要删掉配置、脚本及 `scripts/smoke_test.py`。该目录下同样可使用 `test`、`logs`、`stop`；源码编译入口 `start` 和 `package` 需回到完整源码仓库执行。
