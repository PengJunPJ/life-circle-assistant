import asyncio
import math
import os
from typing import Any, Iterable

import httpx


class BaiduMapError(RuntimeError):
    pass


class BaiduMapClient:
    """百度地图 Web 服务客户端，统一处理请求、限流重试和返回结构。"""

    base_url = "https://api.map.baidu.com"

    def __init__(self) -> None:
        self.ak = os.getenv("BAIDU_MAP_AK", "").strip()
        self.secret = os.getenv("BAIDU_MAP_SECRET", "").strip()
        configured_mode = os.getenv("BAIDU_MAP_MODE", "").strip().lower()
        self.mode = configured_mode or ("real" if self.ak else "mock")

    @property
    def real_available(self) -> bool:
        return self.mode == "real" and bool(self.ak)

    async def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.real_available:
            raise BaiduMapError("百度地图真实模式未启用或缺少 BAIDU_MAP_AK")
        params = {**params, "output": "json", "ak": self.ak}
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    response = await client.get(f"{self.base_url}{path}", params=params)
                    response.raise_for_status()
                    payload = response.json()
                if payload.get("status") not in (0, "0"):
                    raise BaiduMapError(payload.get("message") or f"百度地图接口返回状态 {payload.get('status')}")
                return payload
            except (httpx.HTTPError, ValueError, BaiduMapError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.4 * (2**attempt))
        raise BaiduMapError(str(last_error or "百度地图请求失败")) from last_error

    async def geocode(self, address: str, city: str = "广州") -> dict[str, Any]:
        payload = await self._request("/geocoding/v3/", {"address": address, "city": city})
        result = payload.get("result") or {}
        location = result.get("location") or {}
        if "lng" not in location or "lat" not in location:
            raise BaiduMapError("地址没有解析出有效坐标")
        return {"lng": float(location["lng"]), "lat": float(location["lat"]), "address": result.get("formatted_address") or address}

    async def search_poi(self, query: str, lng: float, lat: float, radius: int = 1000) -> list[dict[str, Any]]:
        payload = await self._request("/place/v2/search", {"query": query, "location": f"{lat},{lng}", "radius": radius, "scope": 2, "page_size": 20})
        return payload.get("results") or []

    async def walking_route(self, origin: tuple[float, float], destination: tuple[float, float]) -> dict[str, Any]:
        payload = await self._request("/directionlite/v1/walking", {"origin": f"{origin[1]},{origin[0]}", "destination": f"{destination[1]},{destination[0]}"})
        result = payload.get("result") or {}
        routes = result.get("routes") or []
        if not routes:
            raise BaiduMapError("两点之间没有可用步行路线")
        route = routes[0]
        return {"distance_m": float(route.get("distance", 0)), "duration_s": float(route.get("duration", 0)), "steps": route.get("steps") or []}

    async def walking_routes(self, origin: tuple[float, float], destinations: Iterable[tuple[float, float]], concurrency: int = 6) -> list[dict[str, Any] | None]:
        semaphore = asyncio.Semaphore(concurrency)

        async def request(destination: tuple[float, float]) -> dict[str, Any] | None:
            async with semaphore:
                try:
                    return await self.walking_route(origin, destination)
                except BaiduMapError:
                    return None

        return await asyncio.gather(*(request(destination) for destination in destinations))


def haversine_meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    lng1, lat1 = a
    lng2, lat2 = b
    lat_scale = 111_320
    lng_scale = 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot((lng2 - lng1) * lng_scale, (lat2 - lat1) * lat_scale)
