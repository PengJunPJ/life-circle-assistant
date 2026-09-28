"""Optional large-language-model enhancement for report interpretation.

The deterministic report interpreter remains the source of truth. This module
only turns verified report facts into clearer language and always returns a
validated fallback when the provider is unavailable or produces bad output.
"""

from __future__ import annotations

import json
import os
import time
from asyncio import Lock, Semaphore, sleep
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .ai_assistant import _filter_hallucinated_content


class LLMError(RuntimeError):
    """Raised when an LLM request cannot produce a usable interpretation."""


class LLMProvider(Protocol):
    model: str

    async def generate(self, *, system: str, user: str) -> dict[str, Any]: ...

    async def close(self) -> None: ...


@dataclass(frozen=True)
class LLMSettings:
    enabled: bool
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float
    max_tokens: int
    max_concurrency: int
    max_retries: int
    retry_base_seconds: float

    @classmethod
    def from_env(cls) -> LLMSettings:
        return cls(
            enabled=os.getenv("LLM_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"},
            provider=os.getenv("LLM_PROVIDER", "openai_compatible").strip() or "openai_compatible",
            base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/"),
            api_key=os.getenv("LLM_API_KEY", "").strip(),
            model=os.getenv("LLM_MODEL", "").strip(),
            timeout_seconds=max(3.0, float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))),
            max_tokens=max(256, int(os.getenv("LLM_MAX_TOKENS", "1200"))),
            max_concurrency=max(1, int(os.getenv("LLM_MAX_CONCURRENCY", "2"))),
            max_retries=max(0, int(os.getenv("LLM_MAX_RETRIES", "2"))),
            retry_base_seconds=max(0.1, float(os.getenv("LLM_RETRY_BASE_SECONDS", "0.5"))),
        )

    @property
    def available(self) -> bool:
        return self.enabled and bool(self.base_url and self.api_key and self.model)


class OpenAICompatibleProvider:
    """Small dependency-light adapter for OpenAI-compatible chat APIs."""

    def __init__(self, settings: LLMSettings) -> None:
        self.model = settings.model
        self._settings = settings
        self._semaphore = Semaphore(settings.max_concurrency)
        self._lock = Lock()
        self._calls = 0
        self._failures = 0
        self._total_latency_ms = 0.0
        self._client = httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=httpx.Timeout(settings.timeout_seconds),
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )

    async def generate(self, *, system: str, user: str) -> dict[str, Any]:
        async with self._semaphore:
            started = time.perf_counter()
            last_error: Exception | None = None
            for attempt in range(self._settings.max_retries + 1):
                try:
                    response = await self._client.post(
                        "/chat/completions",
                        json={
                            "model": self.model,
                            "temperature": 0.1,
                            "max_tokens": self._settings.max_tokens,
                            "response_format": {"type": "json_object"},
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": user},
                            ],
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    content = payload["choices"][0]["message"]["content"]
                    if isinstance(content, list):
                        content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
                    result = json.loads(str(content))
                    if not isinstance(result, dict):
                        raise LLMError("模型返回的 JSON 顶层结构不是对象")
                    await self._record_call(time.perf_counter() - started)
                    return result
                except Exception as exc:
                    last_error = exc
                    if attempt < self._settings.max_retries:
                        await sleep(self._settings.retry_base_seconds * (2**attempt))
            await self._record_call(time.perf_counter() - started, failed=True)
            raise LLMError(f"模型调用或解析失败：{last_error}") from last_error

    async def _record_call(self, latency: float, *, failed: bool = False) -> None:
        async with self._lock:
            self._calls += 1
            self._total_latency_ms += latency * 1000
            if failed:
                self._failures += 1

    def health(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "provider": "openai_compatible",
            "model": self.model,
            "calls": self._calls,
            "failures": self._failures,
            "average_latency_ms": round(self._total_latency_ms / self._calls, 1) if self._calls else 0,
        }

    async def close(self) -> None:
        await self._client.aclose()


def create_llm_provider() -> LLMProvider | None:
    settings = LLMSettings.from_env()
    if not settings.available:
        return None
    if settings.provider != "openai_compatible":
        raise ValueError(f"不支持的 LLM_PROVIDER：{settings.provider}")
    return OpenAICompatibleProvider(settings)


def llm_configuration() -> dict[str, Any]:
    settings = LLMSettings.from_env()
    missing = [
        name
        for name, value in (
            ("LLM_API_KEY", settings.api_key),
            ("LLM_MODEL", settings.model),
        )
        if not value
    ]
    return {
        "enabled": settings.enabled,
        "available": settings.available,
        "provider": settings.provider,
        "model": settings.model or None,
        "base_url": settings.base_url,
        "missing": missing,
    }


def _context(report: dict[str, Any], deterministic: dict[str, Any]) -> dict[str, Any]:
    """Send only report facts relevant to interpretation, not raw geometry."""
    summary = report.get("summary") or {}
    return {
        "report_id": report.get("report_id") or report.get("id"),
        "center": (report.get("center") or {}).get("address"),
        "parameters": report.get("parameters") or {},
        "summary": {
            "score": summary.get("score"),
            "critical_zone_count": summary.get("critical_zone_count"),
            "sparse_zone_count": summary.get("sparse_zone_count"),
        },
        "category_scores": report.get("category_scores") or [],
        "recommendations": report.get("recommendations") or [],
        "deterministic_interpretation": {
            "intent": deterministic.get("intent"),
            "summary": deterministic.get("summary"),
            "recommendations": deterministic.get("recommendations"),
            "evidence_refs": deterministic.get("evidence_refs"),
        },
        "allowed_evidence_refs": deterministic.get("evidence_refs") or [],
    }


def _canonical_refs(result: dict[str, Any]) -> dict[tuple[str, str], dict[str, str]]:
    refs: dict[tuple[str, str], dict[str, str]] = {}
    for ref in result.get("evidence_refs") or []:
        if isinstance(ref, dict) and ref.get("type") and ref.get("id"):
            refs[(str(ref["type"]), str(ref["id"]))] = ref
    for recommendation in result.get("recommendations") or []:
        for ref in recommendation.get("evidence_refs") or []:
            if isinstance(ref, dict) and ref.get("type") and ref.get("id"):
                refs[(str(ref["type"]), str(ref["id"]))] = ref
    return refs


def _validate_model_result(
    model_result: dict[str, Any],
    report: dict[str, Any],
    deterministic: dict[str, Any],
) -> dict[str, Any]:
    summary = model_result.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise LLMError("模型没有返回有效摘要")

    canonical = _canonical_refs(deterministic)

    def refs(value: Any) -> list[dict[str, str]]:
        valid: list[dict[str, str]] = []
        for ref in value if isinstance(value, list) else []:
            if not isinstance(ref, dict):
                continue
            key = (str(ref.get("type", "")), str(ref.get("id", "")))
            if key in canonical:
                valid.append(canonical[key])
        return valid

    recommendations: list[dict[str, Any]] = []
    for item in model_result.get("recommendations") or []:
        if not isinstance(item, dict) or not str(item.get("title", "")).strip():
            continue
        recommendations.append(
            {
                "title": str(item["title"])[:120],
                "text": str(item.get("text") or item.get("rationale") or "")[:600],
                "priority": str(item.get("priority") or "medium"),
                "evidence_refs": refs(item.get("evidence_refs")),
            }
        )

    enhanced = {
        **deterministic,
        "summary": summary.strip()[:1200],
        "recommendations": recommendations,
        "evidence_refs": refs(model_result.get("evidence_refs")),
        "uncertainties": [str(item)[:300] for item in (model_result.get("uncertainties") or []) if str(item).strip()][
            :5
        ],
    }
    return _filter_hallucinated_content(enhanced, report)


async def enhance_interpretation(
    provider: LLMProvider | None,
    report: dict[str, Any],
    deterministic: dict[str, Any],
    *,
    question: str | None = None,
) -> dict[str, Any]:
    """Enhance a deterministic result, or return it unchanged on any failure."""
    if provider is None:
        return deterministic

    system = (
        "你是城市生活圈规划报告解读助手。只能根据用户提供的报告事实回答。"
        "不得创造设施、地址、分数、步行时间或模拟结果。必须返回 JSON，不要 Markdown。"
        '格式：{"summary": string, "recommendations": [{"title": string, "text": string, '
        '"priority": "high|medium|low", "evidence_refs": [{"type": string, "id": string}]}], '
        '"evidence_refs": [{"type": string, "id": string}], "uncertainties": [string]}。'
        "证据引用只能使用 allowed_evidence_refs 中已有的 type/id。"
    )
    user = json.dumps(
        {"question": question or "", "report": _context(report, deterministic)},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    try:
        model_result = await provider.generate(system=system, user=user)
        enhanced = _validate_model_result(model_result, report, deterministic)
        enhanced["mode"] = "llm_structured"
        enhanced["model"] = provider.model
        enhanced["prompt_version"] = "llm-structured-v1"
        return enhanced
    except Exception:
        fallback = {**deterministic, "mode": "rule_template_degraded"}
        fallback["data_quality_notice"] = (
            f"{deterministic.get('data_quality_notice', '')} "
            "大模型暂时不可用或输出未通过证据校验，已使用确定性规则解读。"
        ).strip()
        return fallback
