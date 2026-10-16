import asyncio

import pytest

from app.baidu import BaiduMapClient, BaiduMapError
from app.maps.baidu import BaiduMapProvider


def test_baidu_matrix_nonidentical_zero_route_is_unknown_but_identical_zero_is_valid(monkeypatch):
    client = BaiduMapClient()

    async def request(_path, _params):
        return {"result": [{"distance": {"value": 0}, "duration": {"value": 0}}] * 2}

    monkeypatch.setattr(client, "_request", request)
    results = asyncio.run(client.batch_walking([(113.4, 23.1)], [(113.4, 23.1), (113.5, 23.1)]))
    assert results[0]["success"] is True
    assert results[1]["success"] is False
    assert results[1]["duration_s"] is None


@pytest.mark.parametrize("value", [None, -1, float("nan"), float("inf"), True, "bad"])
def test_invalid_route_numbers_never_become_success(value, monkeypatch):
    client = BaiduMapClient()

    async def request(_path, _params):
        return {"result": [{"distance": {"value": value}, "duration": {"value": 12}}]}

    monkeypatch.setattr(client, "_request", request)
    with pytest.raises(BaiduMapError):
        asyncio.run(client.batch_walking([(113.4, 23.1)], [(113.5, 23.1)]))


def test_client_rejects_over_budget_before_request(monkeypatch):
    client = BaiduMapClient()

    async def forbidden(*_args):
        raise AssertionError("超额矩阵不得外发")

    monkeypatch.setattr(client, "_request", forbidden)
    with pytest.raises(ValueError, match="50"):
        asyncio.run(client.batch_walking([(113.4, 23.1)], [(113.5, 23.1)] * 51))


def test_provider_chunks_both_dimensions_and_preserves_every_pair():
    class Client:
        def __init__(self):
            self.calls = []

        async def batch_walking(self, origins, destinations):
            self.calls.append((origins, destinations))
            return [{"distance_m": 500, "duration_s": 300} for _ in origins for _ in destinations]

    client = Client()
    origins = [(113 + i * 0.001, 23) for i in range(23)]
    destinations = [(114 + i * 0.001, 23) for i in range(17)]
    matrix = asyncio.run(BaiduMapProvider(client).walking_matrix(origins, destinations))
    assert all(len(a) * len(b) <= 50 for a, b in client.calls)
    assert sum(len(a) * len(b) for a, b in client.calls) == 23 * 17
    assert len(matrix) == 23
    assert all(len(row) == 17 for row in matrix)
    assert all(
        item.origin == origins[i] and item.destination == destinations[j] and item.success
        for i, row in enumerate(matrix)
        for j, item in enumerate(row)
    )


def test_poi_pagination_records_exhaustion_separately_from_complete_inventory(monkeypatch):
    client = BaiduMapClient()
    pages = []

    async def request(_path, params):
        pages.append(params["page_num"])
        return {"total": 23, "results": [{"uid": str(i)} for i in range(20 if params["page_num"] == 0 else 3)]}

    monkeypatch.setattr(client, "_request", request)
    results = asyncio.run(client.search_poi("药店", 113.4, 23.1))
    assert pages == [0, 1]
    assert len(results) == 23
    assert results.metadata["query_exhausted"] is True
    assert results.metadata["truncated"] is False
    assert results.metadata["is_full_inventory"] is False


def test_poi_page_budget_discloses_truncation(monkeypatch):
    client = BaiduMapClient()

    async def request(_path, _params):
        return {"total": 88, "results": [{"uid": str(i)} for i in range(20)]}

    monkeypatch.setattr(client, "_request", request)
    results = asyncio.run(client.search_poi("药店", 113.4, 23.1, max_pages=2))
    assert results.metadata["pages_requested"] == 2
    assert results.metadata["truncated"] is True
    assert results.metadata["truncation_reason"] == "page_budget_exhausted"


def test_navigation_location_is_preserved_but_not_promoted_to_verified_entrance():
    place = BaiduMapProvider._normalize_place(
        {
            "uid": "a",
            "name": "测试小学",
            "location": {"lng": 113.4, "lat": 23.1},
            "detail_info": {"navi_location": {"lng": 113.401, "lat": 23.101}},
        },
        "school",
    )
    assert (place.lng, place.lat) == (113.4, 23.1)
    assert place.evidence["navigation_location"] == {"lng": 113.401, "lat": 23.101}
    assert place.evidence["entrance_verified"] is False


def test_nonidentical_zero_direction_route_does_not_claim_success(monkeypatch):
    client = BaiduMapClient()

    async def request(_path, _params):
        return {"result": {"routes": [{"distance": 0, "duration": 0}]}}

    monkeypatch.setattr(client, "_request", request)
    with pytest.raises(BaiduMapError, match="零值"):
        asyncio.run(client.walking_route((113.4, 23.1), (113.5, 23.1)))


def test_provider_single_pair_defends_against_zero_custom_client_results():
    class Client:
        async def walking_route(self, *_args):
            return {"distance_m": 0, "duration_s": 0}

    result = asyncio.run(BaiduMapProvider(Client()).walking_matrix([(113.4, 23.1)], [(113.5, 23.1)]))[0][0]
    assert result.success is False
    assert result.duration_s is None
    assert result.error_code == "route_unavailable"
