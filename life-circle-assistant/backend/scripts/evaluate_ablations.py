"""Five-arm offline smoke or independent per-community artifact evaluation."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.validation.ablations import compare_ablation_artifacts, run_fixture_ablations  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="五组同预算社区隔离消融")
    parser.add_argument("--fixture", action="store_true", help="仅运行无需外部请求的合成契约")
    parser.add_argument("--dataset", type=Path, help="五组实际产物与独立标签JSON")
    args = parser.parse_args()
    if args.fixture == bool(args.dataset):
        parser.error("必须且只能指定 --fixture 或 --dataset")
    result = (
        asyncio.run(run_fixture_ablations())
        if args.fixture
        else compare_ablation_artifacts(json.loads(args.dataset.read_text(encoding="utf-8")))
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
