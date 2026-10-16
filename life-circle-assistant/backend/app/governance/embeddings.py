"""Configured Chinese embeddings, without implicit model downloads or paid calls."""

from __future__ import annotations

import asyncio
import math
import os
from pathlib import Path

import httpx

from ..execution_ledger import charge_external, record_version


def validate_vectors(value, count: int) -> list[list[float]]:
    if not isinstance(value, list) or len(value) != count:
        raise ValueError("嵌入响应数量与输入不一致")
    dimensions = set()
    for vector in value:
        if not isinstance(vector, list) or not vector or len(vector) > 8192:
            raise ValueError("嵌入向量维度无效")
        if any(type(x) not in {float, int} or not math.isfinite(x) for x in vector):
            raise ValueError("嵌入向量必须为有限数值")
        dimensions.add(len(vector))
    if len(dimensions) > 1:
        raise ValueError("嵌入向量维度不一致")
    return value


def validate_texts(texts):
    if (
        not isinstance(texts, list)
        or len(texts) > 256
        or any(not isinstance(text, str) or len(text) > 2048 for text in texts)
    ):
        raise ValueError("嵌入输入必须为不超过256条的文本列表，每条不超过2048字符")


class CompatibleEmbeddingProvider:
    def __init__(self, base_url: str, api_key: str, model: str, *, client=None):
        self.model = model
        self.calls = 0
        self.input_tokens = 0
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            timeout=10,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        validate_texts(texts)
        if not texts:
            return []
        record_version("embedding_model", self.model)
        charge_external("embedding_http_attempts")
        self.calls += 1
        response = await self._client.post("embeddings", json={"model": self.model, "input": texts})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("嵌入响应必须为对象")
        data = payload.get("data", [])
        if (
            not isinstance(data, list)
            or len(data) != len(texts)
            or any(not isinstance(item, dict) or type(item.get("index")) is not int for item in data)
            or {item["index"] for item in data} != set(range(len(texts)))
        ):
            raise ValueError("嵌入返回索引缺失或重复")
        usage = payload.get("usage")
        tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
        if type(tokens) is int and tokens >= 0:
            self.input_tokens += tokens
            charge_external("embedding_input_tokens", tokens)
        else:
            charge_external("embedding_usage_unknown")
        return validate_vectors([item["embedding"] for item in sorted(data, key=lambda x: x["index"])], len(texts))

    async def close(self):
        await self._client.aclose()


class LocalEmbeddingProvider:
    """SentenceTransformer reads an explicitly provisioned local model only."""

    def __init__(self, model_path: str):
        path = Path(model_path).expanduser().resolve()
        if not path.is_dir():
            raise ValueError("本地中文嵌入模型目录不存在")
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ValueError("本地嵌入需要安装 sentence-transformers 并预置模型") from exc
        self.model = str(path)
        self._model = SentenceTransformer(str(path), local_files_only=True)
        self.calls = 0
        self.input_tokens = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        validate_texts(texts)
        if not texts:
            return []
        record_version("embedding_model", self.model)
        charge_external("embedding_local_calls")
        self.calls += 1
        vectors = await asyncio.to_thread(self._model.encode, texts, normalize_embeddings=True)
        return validate_vectors(vectors.tolist(), len(texts))

    async def close(self):
        pass


def create_embedding_provider_from_env():
    if os.getenv("SEMANTIC_EMBEDDING_ENABLED", "false").lower() not in {"true", "1", "yes"}:
        return None
    provider = os.getenv("SEMANTIC_EMBEDDING_PROVIDER", "openai_compatible")
    if provider == "local":
        return LocalEmbeddingProvider(os.getenv("SEMANTIC_EMBEDDING_MODEL_PATH", ""))
    if provider != "openai_compatible":
        raise ValueError("不支持的嵌入提供方")
    model = os.getenv("SEMANTIC_EMBEDDING_MODEL", "").strip()
    base_url = os.getenv("SEMANTIC_EMBEDDING_BASE_URL", "").strip()
    if not model or not base_url:
        raise ValueError("启用中文嵌入时必须配置模型和服务地址")
    return CompatibleEmbeddingProvider(base_url, os.getenv("SEMANTIC_EMBEDDING_API_KEY", ""), model)
