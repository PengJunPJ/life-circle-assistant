"""Run independent semantic labels; write JSON to stdout for reproducible archival."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.governance.embeddings import create_embedding_provider_from_env  # noqa: E402
from app.governance.evaluation import evaluate_semantics  # noqa: E402
from app.llm import create_llm_provider  # noqa: E402


async def run(args):
    embedding = create_embedding_provider_from_env() if args.use_embedding else None
    model = create_llm_provider() if args.use_model else None
    try:
        dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
        return await evaluate_semantics(dataset, embedder=embedding, provider=model)
    finally:
        if embedding:
            await embedding.close()
        if model:
            await model.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="按独立社区评估语义分类、错误合并和漏合并")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--use-embedding", action="store_true")
    parser.add_argument("--use-model", action="store_true")
    print(json.dumps(asyncio.run(run(parser.parse_args())), ensure_ascii=False, indent=2))
