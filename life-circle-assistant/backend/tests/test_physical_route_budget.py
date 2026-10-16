import asyncio

import httpx
import pytest

from app.baidu import BaiduMapClient
from app.execution_budget import BudgetMapProvider, charge_physical_route_pairs
from app.maps.baidu import BaiduMapProvider
from app.maps.provider import MapProviderError


def client_with_transport(handler):
    client = BaiduMapClient()
    client.mode = "real"
    client.ak = "fake-test-key"
    client.qps = 0
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def test_failed_batch_fallback_cannot_send_more_physical_pairs_than_budget():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/routematrix/v2/walking":
            return httpx.Response(200, json={"status": 2, "message": "批量拒绝"})
        return httpx.Response(200, json={"status": 0, "result": {"routes": [{"distance": 500, "duration": 300}]}})

    client = client_with_transport(handler)
    bounded = BudgetMapProvider(BaiduMapProvider(client), limit=3)

    async def exercise():
        try:
            await bounded.walking_matrix([(113.4, 23.1)], [(113.5, 23.1), (113.6, 23.1)])
        finally:
            await client.aclose()

    with pytest.raises(MapProviderError, match="真实步行"):
        asyncio.run(exercise())
    assert calls == ["/routematrix/v2/walking", "/directionlite/v1/walking"]
    assert bounded.physical_route_pairs_used == 3
    assert client.walking_request_count == 2
    assert bounded.used == 2
    charge_physical_route_pairs(10)  # 上下文已恢复，不能泄漏当前预算至其他请求。


def test_retry_attempt_is_charged_before_http_and_stops_at_limit():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(429, json={"status": 429})

    client = client_with_transport(handler)
    bounded = BudgetMapProvider(BaiduMapProvider(client), limit=1)

    async def exercise():
        try:
            await bounded.walking_matrix([(113.4, 23.1)], [(113.5, 23.1)])
        finally:
            await client.aclose()

    with pytest.raises(MapProviderError, match="真实步行"):
        asyncio.run(exercise())
    assert calls == ["/directionlite/v1/walking"]
    assert bounded.physical_route_pairs_used == 1
    assert client.walking_request_count == 1


def test_parallel_requests_keep_isolated_budgets():
    def handler(request):
        return httpx.Response(200, json={"status": 0, "result": {"routes": [{"distance": 500, "duration": 300}]}})

    client = client_with_transport(handler)
    provider = BaiduMapProvider(client)
    first, second = BudgetMapProvider(provider, 1), BudgetMapProvider(provider, 1)

    async def exercise():
        try:
            return await asyncio.gather(
                first.walking_matrix([(113.4, 23.1)], [(113.5, 23.1)]),
                second.walking_matrix([(113.4, 23.1)], [(113.6, 23.1)]),
            )
        finally:
            await client.aclose()

    results = asyncio.run(exercise())
    assert all(matrix[0][0].success for matrix in results)
    assert first.physical_route_pairs_used == second.physical_route_pairs_used == 1


def test_empty_matrix_does_not_consume_budget_or_invoke_provider():
    class Provider:
        async def walking_matrix(self, *_args):
            raise AssertionError("空矩阵不得调用地图")

    bounded = BudgetMapProvider(Provider(), 0)
    assert asyncio.run(bounded.walking_matrix([(0, 0)], [])) == [[]]
    assert bounded.used == bounded.physical_route_pairs_used == 0
