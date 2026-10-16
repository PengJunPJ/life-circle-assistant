import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.execution_budget import BudgetLLMProvider
from app.llm import LLMSettings, OpenAICompatibleProvider
from app.model_budget import ModelAttemptBudget, ModelBudgetExceeded, bind_model_attempt_budget, charge_model_attempt


def provider():
    return OpenAICompatibleProvider(
        LLMSettings(
            enabled=True,
            provider="openai_compatible",
            base_url="https://example.test/v1",
            api_key="fake",
            model="test",
            timeout_seconds=3,
            max_tokens=256,
            max_concurrency=2,
            max_retries=5,
            retry_base_seconds=0.001,
        )
    )


def test_failed_http_retries_consume_physical_budget_and_stop_before_next_request():
    adapter = provider()
    response = MagicMock()
    response.raise_for_status.side_effect = RuntimeError("HTTP failure")
    budget = ModelAttemptBudget(2)

    async def run():
        with patch.object(adapter._client, "post", new_callable=AsyncMock, return_value=response) as post:
            with bind_model_attempt_budget(budget), pytest.raises(ModelBudgetExceeded):
                await adapter.generate(system="system", user="user")
            assert post.await_count == 2
        await adapter.close()

    asyncio.run(run())
    assert budget.used == 2


def test_conversation_wrapper_caps_http_retries_across_completion_methods():
    adapter = provider()
    bounded = BudgetLLMProvider(adapter, limit=2)
    failed = MagicMock()
    failed.raise_for_status.side_effect = RuntimeError("HTTP failure")

    async def run():
        with patch.object(adapter._client, "post", new_callable=AsyncMock, return_value=failed) as post:
            with pytest.raises(ModelBudgetExceeded):
                await bounded.generate_tools(messages=[], tools=[])
            assert post.await_count == bounded.used == 2
            # A fallback completion shares the spent budget and sends no HTTP request.
            with pytest.raises(ModelBudgetExceeded):
                await bounded.generate(system="fallback", user="question")
            assert post.await_count == bounded.used == 2
        await adapter.close()

    asyncio.run(run())


def test_multiple_logical_completions_share_one_physical_attempt_budget():
    adapter = provider()
    response = MagicMock()
    response.json.return_value = {"choices": [{"message": {"content": '{"ok":true}'}}]}
    budget = ModelAttemptBudget(1)

    async def run():
        with patch.object(adapter._client, "post", new_callable=AsyncMock, return_value=response) as post:
            with bind_model_attempt_budget(budget):
                assert await adapter.generate(system="system", user="user") == {"ok": True}
                with pytest.raises(ModelBudgetExceeded):
                    await adapter.generate_tools(messages=[], tools=[])
            assert post.await_count == 1
        await adapter.close()

    asyncio.run(run())


def test_concurrent_requests_keep_independent_attempt_budgets_and_reset_context():
    async def worker(limit):
        budget = ModelAttemptBudget(limit)
        with bind_model_attempt_budget(budget):
            for _ in range(limit):
                charge_model_attempt()
                await asyncio.sleep(0)
            with pytest.raises(ModelBudgetExceeded):
                charge_model_attempt()
        charge_model_attempt()  # no leaked request budget after leaving context
        return budget.used

    async def run():
        return await asyncio.gather(worker(2), worker(3))

    assert asyncio.run(run()) == [2, 3]


@pytest.mark.parametrize("limit", [0, -1, True, 1.0, "2"])
def test_attempt_budget_has_strict_positive_integer_limit(limit):
    with pytest.raises(ValueError):
        ModelAttemptBudget(limit)
