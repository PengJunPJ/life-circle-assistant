.PHONY: quality backend-check frontend-check container-check

quality: backend-check frontend-check container-check

backend-check:
	BAIDU_MAP_MODE=mock python3 -m pytest backend/tests

frontend-check:
	cd frontend && npm ci
	cd frontend && npm run typecheck
	cd frontend && npm test
	cd frontend && npm run build

container-check:
	./scripts/container-smoke.sh
