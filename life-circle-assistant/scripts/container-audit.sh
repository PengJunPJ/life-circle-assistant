#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATE_UTC="${CONTAINER_AUDIT_DATE:-$(date -u +%F)}"
OUTPUT_DIR="${CONTAINER_AUDIT_OUTPUT_DIR:-${ROOT_DIR}/audit-results/container/${DATE_UTC}}"
TRIVY_TIMEOUT="${TRIVY_TIMEOUT:-2m}"
ALLOW_SCANNER_FAILURE="${CONTAINER_AUDIT_ALLOW_SCANNER_FAILURE:-0}"

mkdir -p "${OUTPUT_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi
if ! command -v grype >/dev/null 2>&1; then
  echo "grype is required" >&2
  exit 1
fi
if ! command -v trivy >/dev/null 2>&1; then
  echo "trivy is required" >&2
  exit 1
fi

declare -a LABELS=(api web python-base node-base nginx-base)
declare -a IMAGES=(
  "${API_IMAGE:-life-circle-audit-api:latest}"
  "${WEB_IMAGE:-life-circle-audit-web:latest}"
  "${PYTHON_BASE_IMAGE:-python:3.12.14-slim}"
  "${NODE_BASE_IMAGE:-node:22.22.2-alpine}"
  "${NGINX_BASE_IMAGE:-nginx:1.31-alpine}"
)

grype version > "${OUTPUT_DIR}/grype-version.txt" 2>&1
trivy version > "${OUTPUT_DIR}/trivy-version.txt" 2>&1
grype db status > "${OUTPUT_DIR}/grype-db-status.txt" 2>&1 || true

overall_rc=0
for index in "${!LABELS[@]}"; do
  label="${LABELS[${index}]}"
  image="${IMAGES[${index}]}"
  inspect_file="${OUTPUT_DIR}/${label}.image-inspect.json"
  grype_file="${OUTPUT_DIR}/${label}.grype.json"
  trivy_file="${OUTPUT_DIR}/${label}.trivy.json"
  grype_log="${OUTPUT_DIR}/${label}.grype.log"
  trivy_log="${OUTPUT_DIR}/${label}.trivy.log"

  if ! docker image inspect "${image}" > "${inspect_file}" 2> "${OUTPUT_DIR}/${label}.image-inspect.log"; then
    echo "image not found: ${image}" >&2
    overall_rc=1
    continue
  fi

  set +e
  grype "${image}" --output json > "${grype_file}" 2> "${grype_log}"
  grype_rc=$?
  set -e

  rm -f "${trivy_file}"
  trivy_args=(image --scanners vuln --severity UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL --exit-code 0 --timeout "${TRIVY_TIMEOUT}" --format json --output "${trivy_file}")
  if [[ -n "${TRIVY_DB_REPOSITORY:-}" ]]; then
    trivy_args+=(--db-repository "${TRIVY_DB_REPOSITORY}")
  fi
  set +e
  trivy "${trivy_args[@]}" "${image}" > /dev/null 2> "${trivy_log}"
  trivy_rc=$?
  set -e

  if [[ "${grype_rc}" -ne 0 ]]; then
    overall_rc=1
  fi
  if [[ "${trivy_rc}" -ne 0 && "${ALLOW_SCANNER_FAILURE}" != "1" ]]; then
    overall_rc=1
  fi
  trivy_report_present=false
  [[ -s "${trivy_file}" ]] && trivy_report_present=true
  printf '%s\n' "{\"image\":\"${image}\",\"grype_exit_code\":${grype_rc},\"trivy_exit_code\":${trivy_rc},\"trivy_report_present\":${trivy_report_present},\"trivy_log\":\"${trivy_log##*/}\"}" > "${OUTPUT_DIR}/${label}.status.json"
done

python3 - "${OUTPUT_DIR}" "${DATE_UTC}" "${LABELS[@]}" <<'PY'
import json
import pathlib
import sys

output_dir = pathlib.Path(sys.argv[1])
scan_date = sys.argv[2]
labels = sys.argv[3:]
summary = {"scan_date_utc": scan_date, "images": [], "scanner": "grype-and-trivy"}
severity_order = ["Critical", "High", "Medium", "Low", "Negligible", "Unknown"]
for label in labels:
    status_path = output_dir / f"{label}.status.json"
    if not status_path.exists():
        continue
    status = json.loads(status_path.read_text())
    entry = {"label": label, **status, "grype_counts": {}, "trivy_counts": {}}
    grype_path = output_dir / f"{label}.grype.json"
    if grype_path.exists() and grype_path.stat().st_size:
        report = json.loads(grype_path.read_text())
        entry["image_id"] = report.get("source", {}).get("target", {}).get("imageID")
        entry["manifest_digest"] = report.get("source", {}).get("target", {}).get("manifestDigest")
        for match in report.get("matches", []):
            severity = match.get("vulnerability", {}).get("severity", "Unknown")
            entry["grype_counts"][severity] = entry["grype_counts"].get(severity, 0) + 1
    trivy_path = output_dir / f"{label}.trivy.json"
    if trivy_path.exists() and trivy_path.stat().st_size:
        report = json.loads(trivy_path.read_text())
        for result in report.get("Results", []):
            for vulnerability in result.get("Vulnerabilities") or []:
                severity = vulnerability.get("Severity", "Unknown")
                entry["trivy_counts"][severity] = entry["trivy_counts"].get(severity, 0) + 1
    summary["images"].append(entry)

for entry in summary["images"]:
    entry["grype_counts"] = {key: entry["grype_counts"][key] for key in severity_order if key in entry["grype_counts"]}
    entry["trivy_counts"] = {key: entry["trivy_counts"][key] for key in severity_order if key in entry["trivy_counts"]}
(output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
PY

echo "container audit reports written to ${OUTPUT_DIR}"
exit "${overall_rc}"
