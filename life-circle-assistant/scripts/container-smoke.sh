#!/usr/bin/env bash
set -euo pipefail

project_name="life-circle-quality"

cleanup() {
  docker compose --project-name "$project_name" down --volumes --remove-orphans
}

trap cleanup EXIT

export BAIDU_MAP_MODE=mock
export BAIDU_MAP_AK=
export BAIDU_MAP_SECRET=
export VITE_BAIDU_MAP_AK=

docker compose --project-name "$project_name" up --build --detach --wait
python3 scripts/smoke_test.py
