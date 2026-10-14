import asyncio

import pytest

from app.analysis.service import AnalysisApplicationService
from app.baidu import BaiduMapClient
from app.maps.baidu import BaiduMapProvider
from app.maps.isochrone import geometry_area_sqm, parse_native_isochrone
from app.maps.provider import MapProviderError
from app.schemas import AnalyzeRequest


def test_official_native_parameters_are_bd09_lng_lat_and_raw_seconds(monkeypatch):
    monkeypatch.setenv("BAIDU_NATIVE_ISOCHRONE_ENABLED", "true")
    client = BaiduMapClient()
    calls = []

    async def request(path, params):
        calls.append((path, params))
        return {"result": {"path": "113.4,23.1;113.41,23.1;113.41,23.11;113.4,23.11"}}

    client._request = request
    provider = BaiduMapProvider(client)
    assert provider.isochrone_capability()["account_verified"] is False
    result = asyncio.run(provider.native_isochrone((113.4, 23.1), 900, "foot_shortest"))
    assert calls == [
        (
            "/logistics_truck/v1/isochrone",
            {
                "profile": "foot_shortest",
                "point": "113.4,23.1",
                "timeLimit": 900,
                "inputCrs": "bd09ll",
                "outputCrs": "bd09ll",
            },
        )
    ]
    assert result.geometry["coordinates"][0][0] == result.geometry["coordinates"][0][-1]
    assert provider.isochrone_capability()["account_verified"] is True
    assert provider.isochrone_capability()["pricing_verified"] is False


@pytest.mark.parametrize("path", ["113.4,23.1,bad", "113.4,23.1,113.4,23.1,113.4,23.1", "500,23,501,23,501,24"])
def test_invalid_native_geometry_cannot_become_success(path):
    with pytest.raises(MapProviderError):
        parse_native_isochrone({"result": {"path": path}})


def test_native_multipolygon_preserves_holes_and_area():
    outer = [[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01], [0, 0]]
    inner = [[0.002, 0.002], [0.008, 0.002], [0.008, 0.008], [0.002, 0.008], [0.002, 0.002]]
    geometry = {"type": "MultiPolygon", "coordinates": [[outer, inner]]}
    result = parse_native_isochrone({"result": {"geometry": geometry}})
    assert result == geometry
    assert geometry_area_sqm(result) < geometry_area_sqm({"type": "Polygon", "coordinates": [outer]})


def test_native_capability_keeps_historical_verification_but_is_unavailable_after_latest_failure(monkeypatch):
    monkeypatch.setenv("BAIDU_NATIVE_ISOCHRONE_ENABLED", "true")
    client = BaiduMapClient()
    client.mode, client.ak = "real", "fake-test-key"
    payloads = iter(
        [
            {"result": {"path": "113.4,23.1;113.41,23.1;113.41,23.11;113.4,23.11"}},
            {"result": {"path": "bad"}},
        ]
    )

    async def request(*_args):
        return next(payloads)

    client._request = request
    provider = BaiduMapProvider(client)
    asyncio.run(provider.native_isochrone((113.4, 23.1), 900))
    assert provider.isochrone_capability()["available"] is True
    with pytest.raises(MapProviderError):
        asyncio.run(provider.native_isochrone((113.4, 23.1), 900))
    capability = provider.isochrone_capability()
    assert capability["account_verified"] is True
    assert capability["verified_at"]
    assert capability["available"] is False
    assert capability["error_code"] == "native_geometry_invalid"


def test_native_feature_is_used_without_sending_radial_routes_when_available(monkeypatch):
    monkeypatch.setenv("BAIDU_NATIVE_ISOCHRONE_ENABLED", "true")
    client = BaiduMapClient()

    async def request(*_args):
        return {"result": {"path": "113.4,23.1;113.41,23.1;113.41,23.11;113.4,23.11"}}

    client._request = request
    provider = BaiduMapProvider(client)
    service = AnalysisApplicationService(provider)

    async def forbidden(*_args):
        raise AssertionError("原生成功后不重复径向测算")

    service.walking_service.walking_matrix = forbidden
    request_data = AnalyzeRequest(lng=113.4, lat=23.1, minutes=15, categories=["market"])
    feature = asyncio.run(service._build_isochrone((113.4, 23.1), request_data, [], []))
    assert feature["properties"]["method"] == "baidu_native_isochrone"
    assert feature["properties"]["field_accuracy_verified"] is False
