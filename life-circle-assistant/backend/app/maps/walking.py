from __future__ import annotations

import asyncio
import os
import time
from dataclasses import asdict, dataclass, replace
from typing import Awaitable, Callable

from ..storage.walking_cache import WalkingCacheRepository
from .provider import MapProvider, MapProviderError, WalkingResult


Sleep = Callable[[float], Awaitable[None]]
Coordinate = tuple[float, float]
Pair = tuple[Coordinate, Coordinate]


@dataclass(frozen=True)
class WalkingSettings:
    cache_ttl_seconds: int = 86_400
    max_concurrency: int = 6
    qps: float = 8.0
    timeout_seconds: float = 8.0
    max_retries: int = 2
    retry_base_seconds: float = 0.25

    @classmethod
    def from_env(cls) -> "WalkingSettings":
        return cls(
            cache_ttl_seconds=max(1, int(os.getenv("WALKING_CACHE_TTL_SECONDS", "86400"))),
            max_concurrency=max(1, int(os.getenv("WALKING_MAX_CONCURRENCY", "6"))),
            qps=max(0.0, float(os.getenv("WALKING_QPS", "8"))),
            timeout_seconds=max(0.01, float(os.getenv("WALKING_TIMEOUT_SECONDS", "8"))),
            max_retries=max(0, int(os.getenv("WALKING_MAX_RETRIES", "2"))),
            retry_base_seconds=max(0.0, float(os.getenv("WALKING_RETRY_BASE_SECONDS", "0.25"))),
        )


@dataclass
class WalkingMetrics:
    provider_calls: int = 0
    api_calls: int = 0
    batch_calls: int = 0
    concurrent_fallback_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_expired: int = 0
    retries: int = 0
    rate_limits: int = 0
    timeouts: int = 0
    format_errors: int = 0
    failures: int = 0
    degraded_results: int = 0
    duration_ms: int = 0

    def report_values(self) -> dict[str, int]:
        return {f"walking_{key}": value for key, value in asdict(self).items()}


class WalkingService:
    """为地图提供方增加缓存、批量优先、受控并发和有限重试。"""

    def __init__(
        self,
        provider: MapProvider,
        cache: WalkingCacheRepository | None = None,
        settings: WalkingSettings | None = None,
        *,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.provider = provider
        self.cache = cache
        resolved_settings = settings or WalkingSettings.from_env()
        # 快照/测试提供方不消耗外部配额；即使应用层传入默认设置，也不应人为按真实 API QPS 降速。
        if provider.descriptor.mode != "real" and "WALKING_QPS" not in os.environ:
            resolved_settings = replace(resolved_settings, qps=0)
        self.settings = resolved_settings
        self.metrics = WalkingMetrics()
        self._sleep = sleep
        self._rate_lock = asyncio.Lock()
        self._next_request_at = 0.0

    @property
    def descriptor(self):
        return self.provider.descriptor

    async def walking_matrix(
        self,
        origins: list[Coordinate],
        destinations: list[Coordinate],
    ) -> list[list[WalkingResult]]:
        started = time.perf_counter()
        if not origins or not destinations:
            return [[] for _ in origins]

        pairs = [(origin, destination) for origin in origins for destination in destinations]
        results: dict[Pair, WalkingResult] = {}
        misses: list[Pair] = []
        for pair in dict.fromkeys(pairs):
            lookup = (
                self.cache.get(self.provider.descriptor.id, pair[0], pair[1])
                if self.cache is not None
                else None
            )
            if lookup is not None and lookup.status == "hit" and lookup.result is not None:
                self.metrics.cache_hits += 1
                results[pair] = lookup.result
                self._count_success_source(lookup.result)
                continue
            self.metrics.cache_misses += 1
            if lookup is not None and lookup.status == "expired":
                self.metrics.cache_expired += 1
            misses.append(pair)

        if misses:
            fetched = await self._fetch_misses(misses, origins, destinations)
            for pair, result in fetched.items():
                results[pair] = result
                if result.success:
                    self._count_success_source(result)
                    if self.cache is not None:
                        self.cache.put(
                            self.provider.descriptor.id,
                            result,
                            ttl_seconds=self.settings.cache_ttl_seconds,
                        )
                else:
                    self.metrics.failures += 1

        self.metrics.duration_ms += round((time.perf_counter() - started) * 1_000)
        return [
            [results.get((origin, destination)) or self._failure(origin, destination, "format_error", "步行结果缺失") for destination in destinations]
            for origin in origins
        ]

    async def _fetch_misses(
        self,
        pairs: list[Pair],
        requested_origins: list[Coordinate],
        requested_destinations: list[Coordinate],
    ) -> dict[Pair, WalkingResult]:
        supports_batch = getattr(self.provider, "supports_batch_walking", True)
        if not supports_batch:
            return await self._fetch_concurrently(pairs)

        fetched: dict[Pair, WalkingResult] = {}
        if len(pairs) == len(requested_origins) * len(requested_destinations):
            try:
                fetched = await self._request_with_retries(
                    requested_origins,
                    requested_destinations,
                    batch=True,
                )
            except MapProviderError as exc:
                if exc.code == "batch_not_supported":
                    fetched = await self._fetch_concurrently(pairs)
                else:
                    fetched = {
                        pair: self._failure(pair[0], pair[1], exc.code, str(exc))
                        for pair in pairs
                    }
                    return fetched
            return await self._retry_failed_results(fetched)

        grouped: dict[Coordinate, list[Coordinate]] = {}
        for origin, destination in pairs:
            grouped.setdefault(origin, []).append(destination)
        for origin, destinations in grouped.items():
            try:
                row_results = await self._request_with_retries([origin], destinations, batch=True)
            except MapProviderError as exc:
                if exc.code == "batch_not_supported":
                    fallback_pairs = [(origin, destination) for destination in destinations]
                    fetched.update(await self._fetch_concurrently(fallback_pairs))
                    continue
                row_results = {
                    (origin, destination): self._failure(
                        origin,
                        destination,
                        exc.code,
                        str(exc),
                    )
                    for destination in destinations
                }
            fetched.update(row_results)

        return await self._retry_failed_results(fetched)

    async def _retry_failed_results(self, fetched: dict[Pair, WalkingResult]) -> dict[Pair, WalkingResult]:
        retry_pairs = [pair for pair, result in fetched.items() if not result.success and _is_retryable_code(result.error_code)]
        if retry_pairs:
            semaphore = asyncio.Semaphore(self.settings.max_concurrency)

            async def retry(pair: Pair) -> tuple[Pair, WalkingResult]:
                async with semaphore:
                    return pair, await self._retry_pair(pair, fetched[pair])

            retried = dict(await asyncio.gather(*(retry(pair) for pair in retry_pairs)))
            fetched.update(retried)
        return fetched

    async def _fetch_concurrently(self, pairs: list[Pair]) -> dict[Pair, WalkingResult]:
        semaphore = asyncio.Semaphore(self.settings.max_concurrency)

        async def fetch(pair: Pair) -> tuple[Pair, WalkingResult]:
            async with semaphore:
                self.metrics.concurrent_fallback_calls += 1
                try:
                    result_map = await self._request_with_retries([pair[0]], [pair[1]], batch=False)
                    result = result_map.get(pair)
                    if result is None:
                        result = self._failure(pair[0], pair[1], "format_error", "步行接口未返回坐标对结果")
                    if not result.success and _is_retryable_code(result.error_code):
                        result = await self._retry_pair(pair, result)
                    return pair, result
                except MapProviderError as exc:
                    return pair, self._failure(pair[0], pair[1], exc.code, str(exc))

        return dict(await asyncio.gather(*(fetch(pair) for pair in pairs)))

    async def _request_with_retries(
        self,
        origins: list[Coordinate],
        destinations: list[Coordinate],
        *,
        batch: bool,
    ) -> dict[Pair, WalkingResult]:
        for attempt in range(self.settings.max_retries + 1):
            try:
                return await self._request_matrix(origins, destinations, batch=batch)
            except MapProviderError as exc:
                if not exc.retryable or attempt >= self.settings.max_retries:
                    raise
                self.metrics.retries += 1
                await self._backoff(attempt)
        raise AssertionError("有限重试循环不应越界")

    async def _retry_pair(self, pair: Pair, previous: WalkingResult) -> WalkingResult:
        result = previous
        for attempt in range(self.settings.max_retries):
            self.metrics.retries += 1
            await self._backoff(attempt)
            try:
                result_map = await self._request_matrix([pair[0]], [pair[1]], batch=False)
            except MapProviderError as exc:
                result = self._failure(pair[0], pair[1], exc.code, str(exc))
            else:
                result = result_map.get(pair) or self._failure(
                    pair[0], pair[1], "format_error", "重试未返回坐标对结果"
                )
            if result.success or not _is_retryable_code(result.error_code):
                break
        return result

    async def _request_matrix(
        self,
        origins: list[Coordinate],
        destinations: list[Coordinate],
        *,
        batch: bool,
    ) -> dict[Pair, WalkingResult]:
        await self._wait_for_rate_limit()
        self.metrics.provider_calls += 1
        if self.provider.descriptor.source == "real_api":
            self.metrics.api_calls += 1
        if batch and len(origins) * len(destinations) > 1:
            self.metrics.batch_calls += 1
        try:
            matrix = await asyncio.wait_for(
                self.provider.walking_matrix(origins, destinations),
                timeout=self.settings.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            self.metrics.timeouts += 1
            raise MapProviderError(
                f"步行请求超过 {self.settings.timeout_seconds:g} 秒超时",
                code="timeout",
                retryable=True,
            ) from exc
        except MapProviderError as exc:
            self._count_error(exc.code, exc.rate_limited)
            raise
        except (KeyError, TypeError, ValueError) as exc:
            self.metrics.format_errors += 1
            raise MapProviderError(f"步行接口返回格式错误：{exc}", code="format_error") from exc

        expected_rows = len(origins)
        if not isinstance(matrix, list) or len(matrix) != expected_rows:
            self.metrics.format_errors += 1
            return {
                (origin, destination): self._failure(origin, destination, "format_error", "步行矩阵行数不符合请求")
                for origin in origins
                for destination in destinations
            }
        results: dict[Pair, WalkingResult] = {}
        for row_index, origin in enumerate(origins):
            row = matrix[row_index]
            if not isinstance(row, list) or len(row) != len(destinations):
                self.metrics.format_errors += 1
                for destination in destinations:
                    results[(origin, destination)] = self._failure(
                        origin, destination, "format_error", "步行矩阵列数不符合请求"
                    )
                continue
            for destination_index, destination in enumerate(destinations):
                result = row[destination_index]
                if not isinstance(result, WalkingResult):
                    self.metrics.format_errors += 1
                    result = self._failure(origin, destination, "format_error", "步行矩阵元素格式错误")
                if not result.success:
                    self._count_error(result.error_code)
                results[(origin, destination)] = result
        return results

    async def _wait_for_rate_limit(self) -> None:
        if self.settings.qps <= 0:
            return
        interval = 1 / self.settings.qps
        async with self._rate_lock:
            current = time.monotonic()
            delay = self._next_request_at - current
            if delay > 0:
                await self._sleep(delay)
                current = time.monotonic()
            self._next_request_at = max(current, self._next_request_at) + interval

    async def _backoff(self, attempt: int) -> None:
        delay = self.settings.retry_base_seconds * (2**attempt)
        if delay:
            await self._sleep(delay)

    def _count_error(self, code: str | None, rate_limited: bool = False) -> None:
        normalized = (code or "").lower()
        if rate_limited or "rate" in normalized or "limit" in normalized or normalized in {"302", "429"}:
            self.metrics.rate_limits += 1
        if "timeout" in normalized:
            self.metrics.timeouts += 1
        if "format" in normalized:
            self.metrics.format_errors += 1

    def _count_success_source(self, result: WalkingResult) -> None:
        source = result.underlying_source or result.source
        if source in {"interpolation", "degraded_estimate"}:
            self.metrics.degraded_results += 1

    @staticmethod
    def _failure(origin: Coordinate, destination: Coordinate, code: str, message: str) -> WalkingResult:
        return WalkingResult(
            origin=origin,
            destination=destination,
            success=False,
            distance_m=None,
            duration_s=None,
            source="real_api",
            method="reliable_walking_service",
            error_code=code,
            error_message=message,
        )


def _is_retryable_code(code: str | None) -> bool:
    normalized = (code or "").lower()
    return any(token in normalized for token in ("timeout", "rate", "limit", "temporary", "busy", "http_5"))
