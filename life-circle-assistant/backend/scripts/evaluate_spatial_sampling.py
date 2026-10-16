#!/usr/bin/env python3
"""同预算、同误差、跨社区主动采样离线评估。"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.validation.spatial_sampling import evaluate_spatial_sampling  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="独立社区空间块留出的五策略评估；不调用收费地图服务")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--budgets", type=int, nargs="+", default=[12, 20, 32])
    parser.add_argument("--target-mae", type=float, default=2.0)
    parser.add_argument("--max-false-reachable-rate", type=float, default=0.05)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    result = asyncio.run(
        evaluate_spatial_sampling(
            fixture,
            budgets=args.budgets,
            target_mae_minutes=args.target_mae,
            max_false_reachable_rate=args.max_false_reachable_rate,
        )
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered, encoding="utf-8")
        print(f"评估结果已保存：{args.json_output}；状态：{result['status']}；策略次数：{len(result['results'])}")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
