import asyncio

from app.baidu import BaiduMapClient
from app.maps.baidu import BaiduMapProvider


class RecordingBaiduClient:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search_poi(self, query: str, lng: float, lat: float, radius: int):
        self.queries.append(query)
        shared = {
            "uid": "shared-market",
            "name": "红山菜市场",
            "location": {"lng": lng + 0.001, "lat": lat + 0.001},
            "address": "测试地址",
        }
        if query == "菜市场":
            return [shared]
        if query == "农贸市场":
            return [
                shared,
                {
                    "uid": "farmers-market",
                    "name": "红山农贸市场",
                    "location": {"lng": lng + 0.002, "lat": lat + 0.002},
                },
            ]
        return [
            {
                "uid": "different-provider-id",
                "name": "红山 农贸市场",
                "location": {"lng": lng + 0.002, "lat": lat + 0.002},
            }
        ]


def test_facility_search_splits_market_keywords_and_deduplicates_results():
    client = RecordingBaiduClient()
    provider = BaiduMapProvider(client=client)  # type: ignore[arg-type]

    facilities = asyncio.run(provider.search_facilities("market", (113.4872, 23.1068), 3_000))

    assert client.queries == ["菜市场", "农贸市场", "生鲜超市"]
    assert provider.facility_request_count == 3
    assert [facility.id for facility in facilities] == ["shared-market", "farmers-market"]
    assert all(facility.category == "market" for facility in facilities)


def test_all_baidu_requests_share_configured_qps_limit(monkeypatch):
    monkeypatch.setenv("BAIDU_MAP_QPS", "2")
    current = 0.0
    sleeps: list[float] = []

    def monotonic() -> float:
        return current

    async def sleep(delay: float) -> None:
        nonlocal current
        sleeps.append(delay)
        current += delay

    client = BaiduMapClient(sleep=sleep, monotonic=monotonic)

    async def exercise() -> None:
        await client._wait_for_rate_limit()
        await client._wait_for_rate_limit()
        await client._wait_for_rate_limit()

    asyncio.run(exercise())

    assert sleeps == [0.5, 0.5]
