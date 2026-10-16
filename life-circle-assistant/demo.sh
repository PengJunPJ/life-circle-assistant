#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE=(docker compose --project-name "${DEMO_PROJECT_NAME:-life-circle-demo}"
  --env-file "$SCRIPT_DIR/demo.env" -f "$SCRIPT_DIR/docker-compose.demo.yml")

usage() {
  printf '%s\n' \
    '用法：bash demo.sh [start|test|stop|logs|package [输出包]|load [images.tar]|help]' \
    '  start（默认）  编译、启动、验证并准备示例报告' \
    '  test          对运行中的演示执行完整冒烟测试（会新增一份报告）' \
    '  stop          停止演示并保留数据' \
    '  logs          查看最近的演示日志' \
    '  package       编译并导出当前机器架构的离线演示包' \
    '  load          导入镜像并直接启动、验证；默认读取同目录 images.tar' \
    '可设置 DEMO_WEB_PORT、DEMO_API_PORT 避免端口冲突。'
}

die() {
  printf '错误：%s\n' "$1" >&2
  exit 1
}

require_docker() {
  command -v docker >/dev/null 2>&1 || die '请先安装并启动 Docker Desktop 或 Docker Engine。'
  docker compose version >/dev/null 2>&1 || die '请安装 Docker Compose 插件（支持 up --wait）。'
  docker info >/dev/null 2>&1 || die 'Docker 服务未运行，请先启动 Docker Desktop 或 Docker Engine。'
}

verify_demo() {
  # 在已启动的容器内运行，不依赖宿主机 Python，也不创建额外数据卷。
  "${COMPOSE[@]}" exec -T \
    -e SMOKE_API_URL=http://127.0.0.1:8000 -e SMOKE_WEB_URL=http://web:80 \
    api python - "$@" < "$SCRIPT_DIR/scripts/smoke_test.py"
}

show_ready() {
  printf '\n演示验证通过；打开页面，在历史报告中查看已准备的沙涌长盛花园样例。\n'
  printf '页面：http://%s\n' "$("${COMPOSE[@]}" port web 80)"
  printf '接口文档：http://%s/docs\n' "$("${COMPOSE[@]}" port api 8000)"
}

start_demo() {
  printf '正在编译并启动离线演示；首次构建需要联网下载镜像和依赖……\n'
  "${COMPOSE[@]}" up --build --detach --wait --wait-timeout 120
  verify_demo --reuse-report
  show_ready
}

package_demo() {
  local output="${1:-$SCRIPT_DIR/dist/life-circle-demo.tar.gz}"
  [[ ! -e "$output" ]] || die "输出文件已存在，请指定新文件名：$output"
  [[ -f "$SCRIPT_DIR/../LICENSE" ]] || die '请在源码仓库中执行打包命令。'
  "${COMPOSE[@]}" build
  bundle_dir="$(mktemp -d)"
  # 仅清理 mktemp 创建的本次打包目录。
  trap 'rm -rf -- "$bundle_dir"' EXIT
  mkdir -p "$bundle_dir/life-circle-demo/scripts" "$(dirname -- "$output")"
  docker image save -o "$bundle_dir/life-circle-demo/images.tar" \
    life-circle-demo-api:local life-circle-demo-web:local
  docker image inspect --format '{{.RepoTags}} {{.Os}}/{{.Architecture}} {{.Id}}' \
    life-circle-demo-api:local life-circle-demo-web:local \
    > "$bundle_dir/life-circle-demo/images-info.txt"
  cp "$SCRIPT_DIR/demo.sh" "$SCRIPT_DIR/demo.env" "$SCRIPT_DIR/docker-compose.demo.yml" \
    "$SCRIPT_DIR/../LICENSE" "$SCRIPT_DIR/VERSION" "$bundle_dir/life-circle-demo/"
  cp "$SCRIPT_DIR/scripts/smoke_test.py" "$bundle_dir/life-circle-demo/scripts/"
  cp "$SCRIPT_DIR/docs/contest/quick-start.md" "$bundle_dir/life-circle-demo/README.md"
  tar -czf "$output" -C "$bundle_dir" life-circle-demo
  printf '离线包已生成：%s\n解压后执行：bash life-circle-demo/demo.sh load\n' "$output"
  printf '目标 Docker 必须支持 images-info.txt 中记录的镜像架构。\n'
}

load_demo() {
  local archive="${1:-$SCRIPT_DIR/images.tar}"
  [[ -f "$archive" ]] || die "找不到镜像文件：$archive；请先解压完整离线包。"
  docker image load --input "$archive"
  "${COMPOSE[@]}" up --no-build --pull never --detach --wait --wait-timeout 120
  verify_demo --reuse-report
  show_ready
}

action="${1:-start}"
case "$action" in
  help|-h|--help) usage; exit 0 ;;
  start|test|stop|logs|package|load) ;;
  *) usage >&2; exit 2 ;;
esac
require_docker
case "$action" in
  start) start_demo ;;
  test) verify_demo ;;
  stop)
    "${COMPOSE[@]}" down
    printf '演示已停止，历史报告和数据卷已保留。\n'
    ;;
  logs) "${COMPOSE[@]}" logs --tail 100 api web ;;
  package) package_demo "${2:-}" ;;
  load) load_demo "${2:-}" ;;
esac
