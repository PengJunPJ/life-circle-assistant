import asyncio
from datetime import datetime, timedelta, timezone

from app.maps.provider import ProviderDescriptor, WalkingResult
from app.maps.walking import WalkingService, WalkingSettings
from app.storage import Database, WalkingCacheRepository


ORIGIN = (113.5, 23.1)
DESTINATION = (113.51, 23.11)


class MatrixProvider:
    supports_batch_walking = True

    def __init__(self, behaviors=None):
        self.behaviors = list(behaviors or [])
        self.calls = []

    @property
    def descriptor(self):
        return ProviderDescriptor(
            id="walking-test-provider",
            mode="fixture",
            source="real_api",
            label="步行测试提供方",
            is_latest_real_measurement=True,
        )

    async def walking_matrix(self, origins, destinations):
        self.calls.append((origins, destinations))
        behavior = self.behaviors.pop(0) if self.behaviors else "success"
        if behavior == "timeout":
            await asyncio.sleep(0.05)
        if behavior == "malformed":
            return []
        return [
            [
                WalkingResult(
                    origin=origin,
                    destination=destination,
                    success=behavior != "rate_limited",
                    distance_m=800 if behavior != "rate_limited" else None,
                    duration_s=600 if behavior != "rate_limited" else None,
                    source="real_api",
                    method="fixture_batch",
                    error_code="rate_limited" if behavior == "rate_limited" else None,
                    error_message="测试限流" if behavior == "rate_limited" else None,
                )
                for destination in destinations
            ]
            for origin in origins
        ]


class ConcurrentOnlyProvider(MatrixProvider):
    supports_batch_walking = False

    def __init__(self):
        super().__init__()
        self.active = 0
        self.max_active = 0

    async def walking_matrix(self, origins, destinations):
        self.calls.append((origins, destinations))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return [
            [
                WalkingResult(
                    origin=origins[0],
                    destination=destinations[0],
                    success=True,
                    distance_m=800,
                    duration_s=600,
                    source="real_api",
                    method="fixture_single",
                )
            ]
        ]


class SnapshotFixtureProvider(MatrixProvider):
    @property
    def descriptor(self):
        return ProviderDescriptor(
            id="snapshot-walking-test-provider",
            mode="snapshot",
            source="local_snapshot",
            label="快照步行测试提供方",
            is_latest_real_measurement=False,
        )


def settings(**overrides):
    values = {
        "cache_ttl_seconds": 60,
        "max_concurrency": 2,
        "qps": 0,
        "timeout_seconds": 0.01,
        "max_retries": 1,
        "retry_base_seconds": 0,
    }
    values.update(overrides)
    return WalkingSettings(**values)


def test_cache_miss_then_hit_and_batch_priority(tmp_path):
    database = Database(tmp_path / "walking-cache.db")
    database.migrate()
    cache = WalkingCacheRepository(database)
    provider = MatrixProvider()

    first = WalkingService(provider, cache, settings())
    destinations = [DESTINATION, (113.52, 23.12)]
    first_result = asyncio.run(first.walking_matrix([ORIGIN], destinations))
    assert all(item.success for item in first_result[0])
    assert len(provider.calls) == 1
    assert len(provider.calls[0][1]) == 2
    assert first.metrics.batch_calls == 1
    assert first.metrics.cache_misses == 2

    second = WalkingService(provider, cache, settings())
    second_result = asyncio.run(second.walking_matrix([ORIGIN], destinations))
    assert len(provider.calls) == 1
    assert second.metrics.cache_hits == 2
    assert all(item.source == "cache" for item in second_result[0])
    assert all(item.underlying_source == "real_api" for item in second_result[0])


def test_provider_without_batch_uses_configured_concurrency_limit():
    provider = ConcurrentOnlyProvider()
    service = WalkingService(provider, settings=settings(max_concurrency=2, timeout_seconds=1))
    destinations = [(113.51 + index * 0.001, 23.11) for index in range(4)]

    result = asyncio.run(service.walking_matrix([ORIGIN], destinations))

    assert all(item.success for item in result[0])
    assert len(provider.calls) == 4
    assert provider.max_active == 2
    assert service.metrics.concurrent_fallback_calls == 4


def test_snapshot_provider_is_not_artificially_throttled_by_default_real_api_qps(monkeypatch):
    monkeypatch.delenv("WALKING_QPS", raising=False)
    service = WalkingService(SnapshotFixtureProvider(), settings=settings(qps=8))

    assert service.settings.qps == 0


def test_expired_cache_is_not_used(tmp_path):
    database = Database(tmp_path / "expired-cache.db")
    database.migrate()
    cache = WalkingCacheRepository(database)
    cached_result = WalkingResult(
        origin=ORIGIN,
        destination=DESTINATION,
        success=True,
        distance_m=500,
        duration_s=400,
        source="real_api",
        method="old_result",
    )
    cache.put(
        "walking-test-provider",
        cached_result,
        ttl_seconds=1,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    provider = MatrixProvider()
    service = WalkingService(provider, cache, settings())
    result = asyncio.run(service.walking_matrix([ORIGIN], [DESTINATION]))

    assert result[0][0].method == "fixture_batch"
    assert service.metrics.cache_expired == 1
    assert service.metrics.cache_misses == 1
    assert len(provider.calls) == 1


def test_timeout_is_retried_a_finite_number_of_times_and_reported():
    provider = MatrixProvider(["timeout", "timeout"])
    service = WalkingService(provider, settings=settings(max_retries=1))
    result = asyncio.run(service.walking_matrix([ORIGIN], [DESTINATION]))

    assert result[0][0].success is False
    assert result[0][0].error_code == "timeout"
    assert len(provider.calls) == 2
    assert service.metrics.retries == 1
    assert service.metrics.timeouts == 2


def test_rate_limit_result_is_classified_and_retried():
    provider = MatrixProvider(["rate_limited", "success"])
    service = WalkingService(provider, settings=settings(max_retries=1))
    result = asyncio.run(service.walking_matrix([ORIGIN], [DESTINATION]))

    assert result[0][0].success is True
    assert len(provider.calls) == 2
    assert service.metrics.rate_limits == 1
    assert service.metrics.retries == 1


def test_malformed_matrix_becomes_visible_pair_failure_without_exception():
    provider = MatrixProvider(["malformed"])
    service = WalkingService(provider, settings=settings(max_retries=0))
    result = asyncio.run(service.walking_matrix([ORIGIN], [DESTINATION]))

    assert result[0][0].success is False
    assert result[0][0].error_code == "format_error"
    assert service.metrics.format_errors >= 1
    assert service.metrics.failures == 1
