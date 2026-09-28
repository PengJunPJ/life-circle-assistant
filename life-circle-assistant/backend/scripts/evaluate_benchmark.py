#!/usr/bin/env python3
"""生成或评估真实社区全网格基准。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.validation.benchmarks import (  # noqa: E402
    evaluate_benchmark,
    generate_benchmark_template,
    render_markdown_report,
)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON 格式错误：{path}:{exc.lineno}:{exc.colno} {exc.msg}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"JSON 顶层必须是对象：{path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成或评估生活圈全网格基准")
    subparsers = parser.add_subparsers(dest="command", required=True)

    template = subparsers.add_parser("init", help="从体检报告生成待标注模板")
    template.add_argument("--report", type=Path, required=True)
    template.add_argument("--benchmark-id", required=True)
    template.add_argument("--community-name")
    template.add_argument("--output", type=Path, required=True)

    evaluate = subparsers.add_parser("evaluate", help="对比体检报告与人工基准")
    evaluate.add_argument("--report", type=Path, required=True)
    evaluate.add_argument("--benchmark", type=Path, required=True)
    evaluate.add_argument("--json-output", type=Path)
    evaluate.add_argument("--markdown-output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = load_json(args.report)

    try:
        if args.command == "init":
            template = generate_benchmark_template(
                report,
                benchmark_id=args.benchmark_id,
                community_name=args.community_name,
            )
            write_json(args.output, template)
            print(f"已生成待标注基准模板：{args.output}")
            return

        benchmark = load_json(args.benchmark)
        evaluation = evaluate_benchmark(report, benchmark)
    except ValueError as exc:
        raise SystemExit(f"基准评估失败：{exc}") from exc

    rendered_json = json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n"
    rendered_markdown = render_markdown_report(evaluation)
    if args.json_output:
        write_json(args.json_output, evaluation)
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(rendered_markdown, encoding="utf-8")
    if not args.json_output and not args.markdown_output:
        print(rendered_json, end="")
    else:
        if args.json_output:
            print(f"已生成 JSON 评估结果：{args.json_output}")
        if args.markdown_output:
            print(f"已生成 Markdown 评估报告：{args.markdown_output}")


if __name__ == "__main__":
    main()
