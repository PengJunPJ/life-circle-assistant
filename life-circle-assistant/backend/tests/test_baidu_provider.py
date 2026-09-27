import asyncio

from app.baidu import BaiduMapClient, BaiduMapError
from app.maps.baidu import BaiduMapProvider


class BatchStubClient:
    """记录批量算路与逐对步行调用，用于验证分块与退化策略。"""

    def __init__(self, *, fail_batch: bool = False) -> None:
        self.batch_calls: list[tuple[int, int]] = []
        self.pair_calls: list[tuple[tuple[float, float], tuple[float, float]]] = []
        self.fail_batch = fail_batch

    async def batch_walking(self, origins, destinations):
        self.batch_calls.append((len(origins), len(destinations)))
        if self.fail_batch:
            raise BaiduMapError("批量算路不可用", code="provider_status_2")
        return [
            {
                "distance_m": 100.0 * (oi * len(destinations) + di + 1),
                "duration_s": 60.0 * (oi * len(destinations) + di + 1),
            }
            for oi in range(len(origins))
            for di in range(len(destinations))
        ]

    async def walking_route(self, origin, destination):
        self.pair_calls.append((origin, destination))
        return {
            "distance_m": 500.0,
            "duration_s": 300.0,
            "steps": [{"path": "113.1,23.1;113.2,23.2"}],
        }


def test_provider_declares_batch_walking_support():
    provider = BaiduMapProvider(client=BatchStubClient())  # type: ignore[arg-type]
    assert provider.supports_batch_walking is True


def test_walking_matrix_chunks_by_pair_limit():
    client = BatchStubClient()
    provider = BaiduMapProvider(client=client)  # type: ignore[arg-type]
    destinations = [(113.48 + i * 0.001, 23.10) for i in range(250)]

    matrix = asyncio.run(provider.walking_matrix([(113.4872, 23.1068)], destinations))

    # 点对乘积上限 100：1×250 应拆成 100/100/50 三次批量请求
    assert client.batch_calls == [(1, 100), (1, 100), (1, 50)]
    assert client.pair_calls == []
    assert len(matrix) == 1 and len(matrix[0]) == 250
    # stub 按块内行优先下标赋值：首块第 1/100 对、次块首对、末块第 50 对
    assert matrix[0][0].success and matrix[0][0].distance_m == 100.0
    assert matrix[0][0].duration_s == 60.0
    assert matrix[0][99].distance_m == 100.0 * 100
    assert matrix[0][100].distance_m == 100.0
    assert matrix[0][249].distance_m == 100.0 * 50
    assert all(item.method == "baidu_walking_route_matrix" for item in matrix[0])


def test_walking_matrix_keeps_directionlite_for_single_pair():
    client = BatchStubClient()
    provider = BaiduMapProvider(client=client)  # type: ignore[arg-type]

    matrix = asyncio.run(provider.walking_matrix([(113.4872, 23.1068)], [(113.4887, 23.1053)]))

    # 单坐标对不走批量算路，保留 steps 折线供步行路线预览
    assert client.batch_calls == []
    assert len(client.pair_calls) == 1
    assert matrix[0][0].success
    assert matrix[0][0].method == "baidu_walking_route"
    assert matrix[0][0].steps == [[113.1, 23.1], [113.2, 23.2]]


def test_walking_matrix_falls_back_to_pairs_when_batch_fails():
    client = BatchStubClient(fail_batch=True)
    provider = BaiduMapProvider(client=client)  # type: ignore[arg-type]
    destinations = [(113.48 + i * 0.001, 23.10) for i in range(3)]

    matrix = asyncio.run(provider.walking_matrix([(113.4872, 23.1068)], destinations))

    assert client.batch_calls == [(1, 3)]
    assert len(client.pair_calls) == 3
    assert all(item.success and item.distance_m == 500.0 for item in matrix[0])


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


def test_steps_to_polyline_parses_string_and_object_paths():
    from app.maps.baidu import steps_to_polyline

    string_form = [
        {"path": "113.1,23.1;113.2,23.2;113.2,23.2"},
        {"path": "113.3,23.3"},
    ]
    assert steps_to_polyline(string_form) == [[113.1, 23.1], [113.2, 23.2], [113.3, 23.3]]

    object_form = [{"path": [{"lng": 113.4, "lat": 23.4}, {"x": 113.5, "y": 23.5}]}]
    assert steps_to_polyline(object_form) == [[113.4, 23.4], [113.5, 23.5]]

    assert steps_to_polyline([{"path": "bad"}, {"nope": 1}, None]) == []
