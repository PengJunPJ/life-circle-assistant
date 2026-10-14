import asyncio
import math
import os
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

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


class PoiSearchResults(list):
    """保持列表兼容性，同时携带本次查询的分页证据，避免共享 last_result 状态。"""

    def __init__(self, items: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
        super().__init__(items)
        self.metadata = metadata


class BaiduMapClient:
    """百度地图 Web 服务客户端，统一处理请求、限流重试和返回结构。"""

    base_url = "https://api.map.baidu.com"

    def __init__(self, *, sleep: Sleep = asyncio.sleep, monotonic: Monotonic = time.monotonic) -> None:
        self.ak = os.getenv("BAIDU_MAP_AK", "").strip()
        self.secret = os.getenv("BAIDU_MAP_SECRET", "").strip()
        configured_mode = os.getenv("BAIDU_MAP_MODE", "").strip().lower()
        self.mode = configured_mode or ("real" if self.ak else "mock")
        self.qps = max(0.0, float(os.getenv("BAIDU_MAP_QPS", "1.5")))
        # 步行类请求的真实发出次数（含批量分块），供报告披露真实 API 调用量
        self.walking_request_count = 0
        self.native_isochrone_request_count = 0
        self.native_isochrone_enabled = os.getenv("BAIDU_NATIVE_ISOCHRONE_ENABLED", "false").lower() == "true"
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
                from .execution_ledger import charge_external_many

                # 必须在每次真实 HTTP 尝试前扣费，包括内部重试及批量失败的逐对回退。
                if path == "/routematrix/v2/walking":
                    from .execution_budget import charge_physical_route_pairs

                    pairs = len(str(params["origins"]).split("|")) * len(str(params["destinations"]).split("|"))
                    charge_physical_route_pairs(pairs, {"map_http_attempts": 1, "route_http_attempts": 1})
                    self.walking_request_count += 1
                elif path == "/directionlite/v1/walking":
                    from .execution_budget import charge_physical_route_pairs

                    charge_physical_route_pairs(1, {"map_http_attempts": 1, "route_http_attempts": 1})
                    self.walking_request_count += 1
                elif path == "/logistics_truck/v1/isochrone":
                    charge_external_many({"map_http_attempts": 1, "native_http_attempts": 1})
                    self.native_isochrone_request_count += 1
                else:
                    charge_external_many({"map_http_attempts": 1})
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
                    retryable = rate_limited or status == "1" or status.startswith("5")
                    raise BaiduMapError(
                        payload.get("message") or f"百度地图接口返回状态 {status}",
                        code="rate_limited" if rate_limited else f"provider_status_{status}",
                        retryable=retryable,
                        rate_limited=rate_limited,
                    )
                return payload
            except httpx.TimeoutException:
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
        return {
            "lng": float(location["lng"]),
            "lat": float(location["lat"]),
            "address": result.get("formatted_address") or address,
        }

    async def native_isochrone(
        self, center: tuple[float, float], duration_s: int, strategy: str = "foot_fastest"
    ) -> dict[str, Any]:
        if not self.native_isochrone_enabled:
            raise BaiduMapError("原生等时圈未启用，账号权限与计费仍待核验", code="native_isochrone_disabled")
        if strategy not in {"foot_fastest", "foot_shortest"}:
            raise ValueError("仅支持原生步行最快或最短策略")
        if isinstance(duration_s, bool) or not isinstance(duration_s, int) or not 0 < duration_s < 43_200:
            raise ValueError("原生步行等时圈秒数必须介于0和43200之间")
        return await self._request(
            "/logistics_truck/v1/isochrone",
            {
                "profile": strategy,
                "point": f"{center[0]},{center[1]}",
                "timeLimit": duration_s,
                "inputCrs": "bd09ll",
                "outputCrs": "bd09ll",
            },
        )

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

    async def convert_coordinates(
        self,
        coordinates: list[tuple[float, float]],
        model: int,
    ) -> list[dict[str, float]]:
        """调用百度 Geoconv V2，并按官方每次 100 点上限分块。

        本项目使用的转换方向是 ``model=1``（GCJ-02 → BD-09）和
        ``model=2``（WGS84/GPS → BD-09）。输入和返回均保持经度、纬度顺序。
        """
        if model not in {1, 2}:
            raise ValueError("本项目只支持把 WGS84 或 GCJ-02 转换为 BD-09")
        if not coordinates:
            return []
        converted: list[dict[str, float]] = []
        for start in range(0, len(coordinates), 100):
            chunk = coordinates[start : start + 100]
            payload = await self._request(
                "/geoconv/v2/",
                {
                    "coords": ";".join(f"{lng:.12g},{lat:.12g}" for lng, lat in chunk),
                    "model": model,
                },
            )
            results = payload.get("result") or []
            if len(results) != len(chunk) or any(not isinstance(item, dict) for item in results):
                raise BaiduMapError(
                    f"坐标转换返回 {len(results)} 条结果，与请求的 {len(chunk)} 个坐标不一致",
                    code="format_error",
                )
            for result in results:
                if "x" not in result or "y" not in result:
                    raise BaiduMapError("坐标转换结果缺少 x/y 字段", code="format_error")
                try:
                    lng = float(result["x"])
                    lat = float(result["y"])
                except (TypeError, ValueError) as exc:
                    raise BaiduMapError("坐标转换结果不是有效数字", code="format_error") from exc
                if not math.isfinite(lng) or not math.isfinite(lat):
                    raise BaiduMapError("坐标转换结果不是有限数", code="format_error")
                converted.append({"lng": lng, "lat": lat})
        return converted

    async def convert_coordinate(self, lng: float, lat: float, model: int) -> dict[str, float]:
        return (await self.convert_coordinates([(lng, lat)], model))[0]

    async def search_poi(
        self, query: str, lng: float, lat: float, radius: int = 1000, *, max_pages: int = 3
    ) -> PoiSearchResults:
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or not 1 <= max_pages <= 20:
            raise ValueError("地点检索分页预算必须为 1 到 20 页")
        items: list[dict[str, Any]] = []
        total: int | None = None
        exhausted = False
        for page in range(max_pages):
            payload = await self._request(
                "/place/v2/search",
                {
                    "query": query,
                    "location": f"{lat},{lng}",
                    "radius": radius,
                    "scope": 2,
                    "page_size": 20,
                    "page_num": page,
                },
            )
            results = payload.get("results") or []
            if not isinstance(results, list) or any(not isinstance(item, dict) for item in results):
                raise BaiduMapError("地点检索返回结构不正确", code="format_error")
            raw_total = payload.get("total")
            if isinstance(raw_total, int) and not isinstance(raw_total, bool) and raw_total >= 0:
                total = raw_total
            items.extend(results)
            exhausted = len(results) < 20 or (total is not None and len(items) >= total)
            if exhausted:
                break
        return PoiSearchResults(
            items,
            {
                "query": query,
                "radius_m": radius,
                "pages_requested": page + 1,
                "page_budget": max_pages,
                "result_count": len(items),
                "total_reported": total,
                "query_exhausted": exhausted,
                "truncated": not exhausted,
                "truncation_reason": None if exhausted else "page_budget_exhausted",
                "scope": "provider_keyword_results",
                "is_full_inventory": False,
            },
        )

    async def search_poi_region(
        self,
        query: str,
        region: str = "广州",
        city_limit: bool = True,
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "/place/v2/search",
            {
                "query": query,
                "region": region,
                "city_limit": "true" if city_limit else "false",
                "scope": 2,
                "page_size": 20,
            },
        )
        return payload.get("results") or []

    async def walking_route(self, origin: tuple[float, float], destination: tuple[float, float]) -> dict[str, Any]:
        payload = await self._request(
            "/directionlite/v1/walking",
            {"origin": f"{origin[1]},{origin[0]}", "destination": f"{destination[1]},{destination[0]}"},
        )
        result = payload.get("result") or {}
        routes = result.get("routes") or []
        if not routes:
            raise BaiduMapError("两点之间没有可用步行路线")
        route = routes[0]
        distance_m, duration_s = self._route_numbers(route.get("distance"), route.get("duration"))
        if (distance_m == 0 or duration_s == 0) and origin != destination:
            raise BaiduMapError("非同点路线返回零值，不能证明步行可达", code="route_unavailable")
        return {
            "distance_m": distance_m,
            "duration_s": duration_s,
            "steps": route.get("steps") or [],
        }

    async def batch_walking(
        self,
        origins: list[tuple[float, float]],
        destinations: list[tuple[float, float]],
    ) -> list[dict[str, Any]]:
        """百度批量算路（步行），一次请求返回 origins×destinations 的距离/耗时矩阵。

        返回行优先扁平列表，元素为 ``{"distance_m": float, "duration_s": float}``。
        按官方步行矩阵每次最多 50 路线对约束，分块由调用方负责。
        """
        expected = len(origins) * len(destinations)
        if not 1 <= expected <= 50:
            raise ValueError("步行矩阵单次请求必须为 1 到 50 个路线对")
        payload = await self._request(
            "/routematrix/v2/walking",
            {
                "origins": "|".join(f"{lat},{lng}" for lng, lat in origins),
                "destinations": "|".join(f"{lat},{lng}" for lng, lat in destinations),
            },
        )
        rows = payload.get("result") or []
        if len(rows) != expected:
            raise BaiduMapError(
                f"批量算路返回 {len(rows)} 条结果，与请求的 {expected} 个点对不一致",
                code="format_error",
            )
        parsed: list[dict[str, Any]] = []
        for index, item in enumerate(rows):
            distance = (item or {}).get("distance") or {}
            duration = (item or {}).get("duration") or {}
            if "value" not in distance or "value" not in duration:
                raise BaiduMapError("批量算路结果缺少 distance/duration 字段", code="format_error")
            distance_m, duration_s = self._route_numbers(distance["value"], duration["value"])
            same_point = origins[index // len(destinations)] == destinations[index % len(destinations)]
            available = (distance_m > 0 and duration_s > 0) or (same_point and distance_m == duration_s == 0)
            parsed.append(
                {
                    "distance_m": distance_m if available else None,
                    "duration_s": duration_s if available else None,
                    "success": available,
                    "error_code": None if available else "route_unavailable",
                }
            )
        return parsed

    @staticmethod
    def _route_numbers(distance: Any, duration: Any) -> tuple[float, float]:
        try:
            if isinstance(distance, bool) or isinstance(duration, bool):
                raise ValueError
            numbers = (float(distance), float(duration))
        except (TypeError, ValueError) as exc:
            raise BaiduMapError("路线距离或时间不是有效数字", code="format_error") from exc
        if any(not math.isfinite(value) or value < 0 for value in numbers):
            raise BaiduMapError("路线距离或时间必须为非负有限数", code="format_error")
        return numbers

    async def walking_routes(
        self, origin: tuple[float, float], destinations: Iterable[tuple[float, float]], concurrency: int = 6
    ) -> list[dict[str, Any] | None]:
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
