import asyncio
import math
import os
import time
from typing import Any, Awaitable, Callable, Iterable

import httpx


Sleep = Callable[[float], Awaitable[None]]
Monotonic = Callable[[], float]


class BaiduMapError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_error",
        retryable: bool = False,
        rate_limited: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.rate_limited = rate_limited


class BaiduMapClient:
    """百度地图 Web 服务客户端，统一处理请求、限流重试和返回结构。"""

    base_url = "https://api.map.baidu.com"

    def __init__(self, *, sleep: Sleep = asyncio.sleep, monotonic: Monotonic = time.monotonic) -> None:
        self.ak = os.getenv("BAIDU_MAP_AK", "").strip()
        self.secret = os.getenv("BAIDU_MAP_SECRET", "").strip()
        configured_mode = os.getenv("BAIDU_MAP_MODE", "").strip().lower()
        self.mode = configured_mode or ("real" if self.ak else "mock")
        self.qps = max(0.0, float(os.getenv("BAIDU_MAP_QPS", "1.5")))
        self._http_client: httpx.AsyncClient | None = None
        self._sleep = sleep
        self._monotonic = monotonic
        self._rate_lock = asyncio.Lock()
        self._next_request_at = 0.0

    @property
    def real_available(self) -> bool:
        return self.mode == "real" and bool(self.ak)

    async def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.real_available:
            raise BaiduMapError("百度地图真实模式未启用或缺少 BAIDU_MAP_AK")
        params = {**params, "output": "json", "ak": self.ak}
        last_error: Exception | None = None
        for attempt in range(3):
            await self._wait_for_rate_limit()
            try:
                response = await self._client().get(f"{self.base_url}{path}", params=params)
                if response.status_code == 429:
                    raise BaiduMapError(
                        "百度地图接口触发 HTTP 限流",
                        code="rate_limited",
                        retryable=True,
                        rate_limited=True,
                    )
                response.raise_for_status()
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise BaiduMapError("百度地图接口返回非 JSON 数据", code="format_error") from exc
                if payload.get("status") not in (0, "0"):
                    status = str(payload.get("status"))
                    rate_limited = status in {"302", "429"}
                    raise BaiduMapError(
                        payload.get("message") or f"百度地图接口返回状态 {status}",
                        code="rate_limited" if rate_limited else f"provider_status_{status}",
                        retryable=rate_limited or status.startswith("5"),
                        rate_limited=rate_limited,
                    )
                return payload
            except httpx.TimeoutException as exc:
                last_error = BaiduMapError("百度地图请求超时", code="timeout", retryable=True)
                if attempt < 2:
                    await asyncio.sleep(0.4 * (2**attempt))
            except httpx.HTTPError as exc:
                last_error = BaiduMapError(f"百度地图 HTTP 请求失败：{exc}", code="http_error", retryable=True)
                if attempt < 2:
                    await asyncio.sleep(0.4 * (2**attempt))
            except BaiduMapError as exc:
                last_error = exc
                if attempt < 2 and exc.retryable:
                    await asyncio.sleep(0.4 * (2**attempt))
                    continue
                break
        if isinstance(last_error, BaiduMapError):
            raise last_error
        raise BaiduMapError(str(last_error or "百度地图请求失败")) from last_error

    async def _wait_for_rate_limit(self) -> None:
        """所有百度 Web 服务请求共享同一发送节奏。

        设施检索、地理编码和步行路线最终都经过该客户端，因此不会再各自
        抢占同一百度 AK 的并发配额。设为 0 可在明确知道配额足够时关闭。
        """
        if self.qps <= 0:
            return
        interval = 1 / self.qps
        async with self._rate_lock:
            current = self._monotonic()
            delay = self._next_request_at - current
            if delay > 0:
                await self._sleep(delay)
                current = self._monotonic()
            self._next_request_at = max(current, self._next_request_at) + interval

    def _client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=8)
        return self._http_client

    async def aclose(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def geocode(self, address: str, city: str = "广州") -> dict[str, Any]:
        payload = await self._request("/geocoding/v3/", {"address": address, "city": city})
        result = payload.get("result") or {}
        location = result.get("location") or {}
        if "lng" not in location or "lat" not in location:
            raise BaiduMapError("地址没有解析出有效坐标")
        return {"lng": float(location["lng"]), "lat": float(location["lat"]), "address": result.get("formatted_address") or address}

    async def reverse_geocode(self, lng: float, lat: float) -> dict[str, Any]:
        payload = await self._request("/reverse_geocoding/v3/", {"location": f"{lat},{lng}", "extensions_poi": 0})
        result = payload.get("result") or {}
        location = result.get("location") or {}
        if "lng" not in location or "lat" not in location:
            raise BaiduMapError("坐标没有解析出有效地址")
        return {
            "lng": float(location["lng"]),
            "lat": float(location["lat"]),
            "address": result.get("formatted_address") or f"{lng:.6f}, {lat:.6f}",
        }

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
