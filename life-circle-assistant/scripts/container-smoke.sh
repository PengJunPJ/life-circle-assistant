#!/usr/bin/env bash
set -euo pipefail

project_name="${CONTAINER_SMOKE_PROJECT_NAME:-life-circle-quality}"

cleanup() {
  docker compose --project-name "$project_name" down --volumes --remove-orphans
}

trap cleanup EXIT

export BAIDU_MAP_MODE=mock
export BAIDU_MAP_AK=
export BAIDU_MAP_SECRET=
export VITE_BAIDU_MAP_AK=
export AMAP_VALIDATION_ENABLED=false
export AMAP_WEB_SERVICE_KEY=
export LLM_ENABLED=false
export LLM_API_KEY=
export BAIDU_NATIVE_ISOCHRONE_ENABLED=false
export SEMANTIC_EMBEDDING_ENABLED=false
export SEMANTIC_EMBEDDING_API_KEY=
export SEMANTIC_EMBEDDING_MODEL_PATH=
export OBSERVATION_OCR_ENABLED=false
export OBSERVATION_OCR_API_KEY=
export LIFE_CIRCLE_NORMS_PATH=
export API_HOST_PORT="${CONTAINER_SMOKE_API_PORT:-18000}"
export WEB_HOST_PORT="${CONTAINER_SMOKE_WEB_PORT:-15173}"
export SMOKE_API_URL="http://localhost:${API_HOST_PORT}"
export SMOKE_WEB_URL="http://localhost:${WEB_HOST_PORT}"

docker compose --project-name "$project_name" up --build --detach --wait
python3 scripts/smoke_test.py
