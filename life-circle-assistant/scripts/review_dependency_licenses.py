"""汇总 SBOM 许可证证据；未知声明不自动提升为合规。"""
from __future__ import annotations

import hashlib
import json
import ssl
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import certifi

ROOT = Path(__file__).resolve().parents[1]
SBOM_DIR = ROOT / "docs/governance/sbom"


def pypi_license(component: dict) -> dict:
    name, version = component["name"], component["version"]
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=30, context=ssl.create_default_context(cafile=certifi.where())) as response:
            info = json.load(response)["info"]
        declarations = [item for item in info.get("classifiers", []) if item.startswith("License ::")]
        return {
            "expression": info.get("license_expression"),
            "classifiers": declarations,
            "declared_text": (info.get("license") or "")[:4000],
            "source": url,
        }
    except Exception as error:
        return {"source": url, "error": type(error).__name__}


def main() -> None:
    records = []
    inputs = []
    python_components = {}
    for path in sorted(SBOM_DIR.glob("*-20261012.cdx.json")):
        bom = json.loads(path.read_text())
        if bom.get("bomFormat") != "CycloneDX" or not bom.get("components"):
            raise ValueError(f"SBOM 无效：{path.name}")
        inputs.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "component_count": len(bom["components"]), "spec_version": bom["specVersion"]})
        for component in bom["components"]:
            key = (component["name"], component.get("version", ""))
            if path.name.startswith("backend-"):
                python_components[key] = component
            records.append({"scope": path.name, "name": key[0], "version": key[1],
                            "purl": component.get("purl"), "licenses": component.get("licenses", [])})
    with ThreadPoolExecutor(max_workers=4) as pool:
        python_evidence = dict(zip(python_components, pool.map(pypi_license, python_components.values())))
    for record in records:
        if record["scope"].startswith("backend-"):
            record["pypi_evidence"] = python_evidence[(record["name"], record["version"])]
        evidence = record.get("pypi_evidence", {})
        record["status"] = "declaration-found" if (
            record["licenses"] or evidence.get("expression") or evidence.get("classifiers") or evidence.get("declared_text")
        ) else "needs-review"
    result = {"reviewed_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), "inputs": inputs,
              "boundary": "逐包声明和证据核对，不是授权或相容性法律结论。镜像仅对应已审计本地镜像，未宣称为 GHCR 发布。",
              "components": records}
    (SBOM_DIR.parent / "license-review-20261012.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    missing = [r for r in records if r["status"] == "needs-review"]
    lines = ["# 2026-10-12 依赖许可证证据复核", "",
             f"已逐包整理 {len(records)} 条组件记录（不同范围可能重复），{len(missing)} 条缺少许可证声明。", "",
             "`declaration-found` 表示元数据有声明；不代表通知义务已全部履行、法律相容性已获批准或地图服务授权已完成。", "",
             "前端 SBOM 包含已安装包的许可证文本证据；Python 使用固定版本 PyPI 元数据；镜像使用 Trivy 软件包声明。", "",
             "完整条目和证据见 [JSON](license-review-20261012.json)。", "",
             "| SBOM | 组件数 |", "| --- | ---: |"]
    lines += [f"| [ {item['file']} ](sbom/{item['file']}) | {item['component_count']} |" for item in inputs]
    lines += ["", "待人工确认：第三方地图/模型服务条款；打包分发的通知义务；以下缺少声明的组件。", "",
              "| 范围 | 组件 | 版本 |", "| --- | --- | --- |"]
    lines += [f"| {r['scope']} | {r['name']} | {r['version']} |" for r in missing]
    (SBOM_DIR.parent / "license-review-20261012.md").write_text("\n".join(lines) + "\n")
    print(f"复核 {len(records)} 条；缺少声明 {len(missing)} 条；未自动批准许可证相容性。")


if __name__ == "__main__":
    main()
