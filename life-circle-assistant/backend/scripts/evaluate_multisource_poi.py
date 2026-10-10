#!/usr/bin/env python3
"""Evaluate a permission-cleared, privacy-minimized Baidu/Amap match fixture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.validation.multisource_poi import evaluate_labeled_pairs  # noqa: E402

MIN_PAIRS = 50
MAX_PAIRS = 100


def load_fixture(path: Path) -> dict[str, Any]:
    try:
        fixture = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"多源审计 fixture 不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"fixture JSON 格式错误：{path}:{exc.lineno}:{exc.colno} {exc.msg}") from exc
    if not isinstance(fixture, dict):
        raise SystemExit("fixture 顶层必须是 JSON 对象")
    return fixture


def evaluate_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    manifest = fixture.get("manifest") or {}
    if manifest.get("status") != "ready":
        raise SystemExit("fixture 尚未就绪：需要真实双源查询、人工标签和许可核验")
    if manifest.get("permission_status") != "written_permission_received":
        raise SystemExit("未记录高德书面许可；不得将来源数据用于可持久化审计 fixture")
    pairs = fixture.get("pairs")
    if not isinstance(pairs, list) or not MIN_PAIRS <= len(pairs) <= MAX_PAIRS:
        raise SystemExit(
            f"人工标注样本必须为 {MIN_PAIRS}–{MAX_PAIRS} 对；当前为 {len(pairs) if isinstance(pairs, list) else 0}"
        )
    if any(not isinstance(pair.get("features"), dict) for pair in pairs):
        raise SystemExit("fixture 仅允许保存特征分数和人工标签，不得持久化原始名称、地址或来源 POI ID")
    if any(not pair.get("reviewer") or not pair.get("reviewed_at") for pair in pairs):
        raise SystemExit("每一对样本都必须记录复核人代号和复核时间")
    return evaluate_labeled_pairs(pairs)


def render_markdown(result: dict[str, Any], manifest: dict[str, Any]) -> str:
    metrics = result["match_metrics"]
    return "\n".join(
        [
            "# 多源 POI 实体对齐评估",
            "",
            f"- 评估日期：{manifest.get('evaluated_at', '未提供')}",
            f"- 规则版本：{result['rules_version']}",
            f"- 样本数：{result['sample_count']}",
            f"- 查询指纹：{manifest.get('query_fingerprint', '未提供')}",
            "",
            "| 指标 | 结果 |",
            "| --- | ---: |",
            f"| 匹配精确率 | {metrics['precision']:.4f} |",
            f"| 匹配召回率 | {metrics['recall']:.4f} |",
            f"| 匹配 F1 | {metrics['f1']:.4f} |",
            f"| 人工冲突识别召回率 | {result['human_conflict_recall']:.4f} |",
            f"| 待人工复核率 | {result['unresolved_rate']:.4f} |",
            f"| 显式冲突率 | {result['conflict_rate']:.4f} |",
            "",
            "本报告只使用高德书面许可范围内留存的特征分数与标签；不包含 POI 名称、地址、坐标或来源 ID。",
            "",
        ]
    )


def write_output(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="评估高德/百度 POI 人工标注样本")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()

    fixture = load_fixture(args.fixture)
    manifest = fixture.get("manifest") or {}
    result = evaluate_fixture(fixture)
    rendered_json = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    rendered_markdown = render_markdown(result, manifest)
    if args.json_output:
        write_output(args.json_output, rendered_json)
    if args.markdown_output:
        write_output(args.markdown_output, rendered_markdown)
    if not args.json_output and not args.markdown_output:
        print(rendered_json, end="")


if __name__ == "__main__":
    main()
