import asyncio

import pytest

from app.execution_ledger import (
    ExecutionRepository,
    LedgerMapProvider,
    bind_execution,
    charge_external,
    record_model_usage,
)
from app.maps.provider import LocationResult, MapProviderError, ProviderDescriptor
from app.storage import Database


class CountingProvider:
    descriptor = ProviderDescriptor(
        id="test", label="测试", mode="mock", source="local_snapshot", is_latest_real_measurement=False
    )
    calls = 0

    async def reverse_geocode(self, lng, lat):
        self.calls += 1
        return LocationResult(lng=lng, lat=lat, address="测试地址")


@pytest.mark.asyncio
async def test_checkpoint_survives_new_repository_and_provider_and_keeps_original_budget(tmp_path):
    path = tmp_path / "resume.db"
    database = Database(path)
    database.migrate()
    repository = ExecutionRepository(database)
    ledger = repository.ensure("task-1", "analysis_task", {"map_adapter_calls": 1})
    provider = CountingProvider()
    with bind_execution(ledger):
        first = await LedgerMapProvider(provider, ledger).reverse_geocode(113.5, 23.1)
    fresh = ExecutionRepository(Database(path))
    next_ledger = fresh.ensure("task-1", "analysis_task", {"map_adapter_calls": 100})
    with bind_execution(next_ledger):
        replay = await LedgerMapProvider(provider, next_ledger).reverse_geocode(113.5, 23.1)
        with pytest.raises(MapProviderError, match="预算"):
            await LedgerMapProvider(provider, next_ledger).reverse_geocode(113.6, 23.1)
    assert first == replay
    assert provider.calls == 1
    assert fresh.get("task-1")["budget"]["map_adapter_calls"] == 1
    assert fresh.get("task-1")["usage"]["checkpoint_hits"] == 1


@pytest.mark.asyncio
async def test_inflight_paid_request_cannot_be_replayed_after_process_interruption(tmp_path):
    database = Database(tmp_path / "uncertain.db")
    database.migrate()
    ledger = ExecutionRepository(database).ensure("task-1", "analysis_task")

    class Interrupted(CountingProvider):
        async def reverse_geocode(self, lng, lat):
            raise asyncio.CancelledError()

    with bind_execution(ledger):
        with pytest.raises(asyncio.CancelledError):
            await LedgerMapProvider(Interrupted(), ledger).reverse_geocode(113.5, 23.1)
        replacement = CountingProvider()
        with pytest.raises(MapProviderError, match="计费状态未决"):
            await LedgerMapProvider(replacement, ledger).reverse_geocode(113.5, 23.1)
    assert replacement.calls == 0


def test_token_usage_unknown_prices_and_versions(tmp_path, monkeypatch):
    database = Database(tmp_path / "usage.db")
    database.migrate()
    ledger = ExecutionRepository(database).ensure("request-1", "interpret")
    monkeypatch.delenv("LLM_INPUT_PRICE_CNY_PER_MILLION", raising=False)
    monkeypatch.delenv("LLM_OUTPUT_PRICE_CNY_PER_MILLION", raising=False)
    with bind_execution(ledger):
        record_model_usage({"usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}, "test-model")
        charge_external("map_http_attempts", 2)
    summary = ledger.summary()
    assert summary["usage"]["total_tokens"] == 30
    assert summary["versions"]["model"] == "test-model"
    assert summary["cost"]["estimated_total"] is None
    assert summary["cost"]["settled_total"] is None


def test_cost_basis_is_exclusive_and_native_requests_not_double_charged(tmp_path, monkeypatch):
    database = Database(tmp_path / "price.db")
    database.migrate()
    ledger = ExecutionRepository(database).ensure("price", "pricing")
    monkeypatch.setenv("MAP_PRICING_UNIT", "request")
    monkeypatch.setenv("MAP_REQUEST_PRICE_CNY", "1")
    monkeypatch.setenv("ROUTE_PAIR_PRICE_CNY", "10")
    monkeypatch.setenv("NATIVE_ISOCHRONE_PRICE_CNY", "3")
    monkeypatch.setenv("EMBEDDING_PRICING_UNIT", "tokens")
    monkeypatch.setenv("EMBEDDING_PRICE_CNY_PER_MILLION", "1000000")
    monkeypatch.setenv("EMBEDDING_REQUEST_PRICE_CNY", "99")
    ledger.charge_many(
        {
            "map_http_attempts": 3,
            "native_http_attempts": 1,
            "route_pairs": 100,
            "embedding_http_attempts": 2,
            "embedding_input_tokens": 5,
        }
    )
    summary = ledger.summary()["cost"]
    assert summary["items"] == {"map_http_attempts": 2, "native_http_attempts": 3, "embedding_input_tokens": 5}
    assert summary["estimated_total"] == 10
    monkeypatch.delenv("MAP_PRICING_UNIT")
    assert ledger.summary()["cost"]["estimated_total"] is None


@pytest.mark.parametrize("usage", [{}, {"total_tokens": 50}, {"prompt_tokens": 10, "completion_tokens": -1}])
def test_missing_or_invalid_model_tokens_cannot_produce_known_total(tmp_path, monkeypatch, usage):
    database = Database(tmp_path / "tokens.db")
    database.migrate()
    ledger = ExecutionRepository(database).ensure("tokens", "pricing")
    monkeypatch.setenv("LLM_INPUT_PRICE_CNY_PER_MILLION", "1")
    monkeypatch.setenv("LLM_OUTPUT_PRICE_CNY_PER_MILLION", "1")
    with bind_execution(ledger):
        record_model_usage({"usage": usage}, "model")
    assert ledger.summary()["usage"]["model_responses_usage_unknown"] == 1
    assert ledger.summary()["cost"]["estimated_total"] is None


@pytest.mark.asyncio
async def test_budget_refusal_never_leaves_uncertain_checkpoint(tmp_path):
    database = Database(tmp_path / "refuse.db")
    database.migrate()
    repo = ExecutionRepository(database)
    ledger = repo.ensure("refuse", "analysis", {"map_adapter_calls": 0})
    provider = CountingProvider()
    with bind_execution(ledger):
        with pytest.raises(MapProviderError, match="预算"):
            await LedgerMapProvider(provider, ledger).reverse_geocode(113.5, 23.1)
    assert provider.calls == 0
    assert repo.uncertain("refuse") == []


@pytest.mark.asyncio
async def test_reconciliation_only_retries_uncertain_request_without_resetting_budget(tmp_path):
    database = Database(tmp_path / "review.db")
    database.migrate()
    repo = ExecutionRepository(database)
    ledger = repo.ensure("review", "analysis", {"map_adapter_calls": 2})

    class Interrupted(CountingProvider):
        async def reverse_geocode(self, lng, lat):
            raise asyncio.CancelledError()

    with bind_execution(ledger):
        with pytest.raises(asyncio.CancelledError):
            await LedgerMapProvider(Interrupted(), ledger).reverse_geocode(113.5, 23.1)
        item = repo.uncertain("review")[0]
        repo.authorize_retry("review", item["call_key"], "复核员", "已核对提供方日志，无返回记录，接受再次计费")
        provider = CountingProvider()
        await LedgerMapProvider(provider, ledger).reverse_geocode(113.5, 23.1)
        assert provider.calls == 1
        with pytest.raises(ValueError, match="未决"):
            repo.authorize_retry("review", item["call_key"], "复核员", "不能重放已完成结果")
    assert repo.get("review")["usage"]["map_adapter_calls"] == 2
    assert repo.get("review")["budget"]["map_adapter_calls"] == 2
