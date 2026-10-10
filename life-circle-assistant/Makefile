.PHONY: quality backend-check frontend-check container-check dependency-audit performance-snapshot benchmark-help multisource-audit amap-probe

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

dependency-audit:
	@command -v pip-audit >/dev/null || (echo 'pip-audit is required; install it before running dependency-audit' >&2; exit 1)
	python3 -m pip_audit -r backend/requirements.txt
	python3 -m pip_audit -r backend/requirements-dev.txt
	cd frontend && npm_config_registry=https://registry.npmjs.org npm audit --audit-level=high
	@echo 'Docker image CVE scanning is not part of this target yet; use Trivy or Grype and record the result in docs/governance/dependency-compliance.md.'

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
