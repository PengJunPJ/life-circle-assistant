.PHONY: quality backend-check frontend-check container-check performance-snapshot benchmark-help multisource-audit amap-probe

quality: backend-check frontend-check container-check

backend-check:
	python3 -m pip install --quiet -r backend/requirements-dev.txt
	cd backend && ruff check . && ruff format --check .
	BAIDU_MAP_MODE=mock python3 -m pytest backend/tests

frontend-check:
	cd frontend && npm ci
	cd frontend && npm run lint
	cd frontend && npm run typecheck
	cd frontend && npm test
	cd frontend && npm run build

container-check:
	./scripts/container-smoke.sh

performance-snapshot:
	python3 scripts/performance_baseline.py --runs 2 --output docs/performance/latest-snapshot.json

benchmark-help:
	python3 backend/scripts/evaluate_benchmark.py --help

multisource-audit:
	python3 backend/scripts/evaluate_multisource_poi.py \
		--fixture docs/validation/multisource-poi/fixture.json \
		--json-output docs/validation/multisource-poi/evaluation.json \
		--markdown-output docs/validation/multisource-poi/evaluation.md

amap-probe:
	python3 backend/scripts/probe_amap.py
