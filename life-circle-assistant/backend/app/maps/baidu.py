from __future__ import annotations

import asyncio
import re
import unicodedata

from ..baidu import BaiduMapClient, BaiduMapError
from .provider import (
    FacilityResult,
    LocationResult,
    MapProviderError,
    ProviderDescriptor,
    WalkingResult,
)


FACILITY_QUERIES = {
    "market": ("菜市场", "农贸市场", "生鲜超市"),
    "pharmacy": ("药店",),
    "school": ("小学",),
    "medical": ("社区卫生服务中心", "医院", "诊所"),
    "elderly": ("养老院", "敬老院", "日间照料中心", "养老服务中心"),
    "park": ("公园", "口袋公园", "社区花园"),
    "convenience": ("便利店", "超市", "综合超市"),
}


def steps_to_polyline(steps: list) -> list:
    """把百度 directionlite 的 steps 归一化为 [[lng, lat], ...] 折线。

    兼容 ``path`` 为 ``"lng,lat;lng,lat"`` 字符串或坐标对象列表两种形态。
    """
    polyline: list = []
    for step in steps or []:
        path = step.get("path") if isinstance(step, dict) else None
        points = []
        if isinstance(path, str):
            for pair in path.split(";"):
                if "," not in pair:
                    continue
                lng, _, lat = pair.partition(",")
                points.append((lng, lat))
        elif isinstance(path, list):
            for item in path:
                if isinstance(item, dict):
                    lng = item.get("lng", item.get("x"))
                    lat = item.get("lat", item.get("y"))
                    points.append((lng, lat))
        for lng, lat in points:
            try:
                coordinate = [round(float(lng), 6), round(float(lat), 6)]
            except (TypeError, ValueError):
                continue
            if not polyline or polyline[-1] != coordinate:
                polyline.append(coordinate)
    return polyline


class BaiduMapProvider:
    def __init__(self, client: BaiduMapClient | None = None, concurrency: int = 6) -> None:
        self.client = client or BaiduMapClient()
        self.concurrency = concurrency
        self.facility_request_count = 0

    @property
    def supports_batch_walking(self) -> bool:
        # 百度轻量步行路线接口一次只接受一个坐标对，由可靠调用层控制并发和 QPS。
        return False

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            id="baidu-web-service",
            mode="real",
            source="real_api",
            label="百度地图 Web 服务实时测算",
            is_latest_real_measurement=True,
        )

    async def geocode(self, address: str, city: str = "广州") -> list[LocationResult]:
        try:
            result = await self.client.geocode(address, city)
        except BaiduMapError as exc:
            raise self._provider_error(exc) from exc
        return [LocationResult(lng=result["lng"], lat=result["lat"], address=result["address"])]

    async def reverse_geocode(self, lng: float, lat: float) -> LocationResult:
        try:
            result = await self.client.reverse_geocode(lng, lat)
        except BaiduMapError as exc:
            raise self._provider_error(exc) from exc
        return LocationResult(lng=result["lng"], lat=result["lat"], address=result["address"])

    async def search_places(
        self,
        query: str,
        center: tuple[float, float],
        radius_m: int = 1_000,
    ) -> list[FacilityResult]:
        try:
            results = await self.client.search_poi(query, center[0], center[1], radius_m)
        except BaiduMapError as exc:
            raise self._provider_error(exc) from exc
        return [self._normalize_place(item, "unknown") for item in results if self._has_location(item)]

    async def search_facilities(
        self,
        category: str,
        center: tuple[float, float],
        radius_m: int = 1_000,
    ) -> list[FacilityResult]:
        queries = FACILITY_QUERIES.get(category)
        if not queries:
            raise MapProviderError(f"不支持的民生设施类别：{category}")
        normalized: list[FacilityResult] = []
        for query in queries:
            try:
                self.facility_request_count += 1
                results = await self.client.search_poi(query, center[0], center[1], radius_m)
            except BaiduMapError as exc:
                # 任一分词失败都会使该类别召回不完整；显式失败比静默返回部分结果更可审计。
                raise self._provider_error(exc) from exc
            normalized.extend(
                self._normalize_place(item, category)
                for item in results
                if self._has_location(item)
            )
        return self._deduplicate_places(normalized)

    async def walking_matrix(
        self,
        origins: list[tuple[float, float]],
        destinations: list[tuple[float, float]],
    ) -> list[list[WalkingResult]]:
        semaphore = asyncio.Semaphore(self.concurrency)

        async def calculate(origin: tuple[float, float], destination: tuple[float, float]) -> WalkingResult:
            async with semaphore:
                try:
                    route = await self.client.walking_route(origin, destination)
                    return WalkingResult(
                        origin=origin,
                        destination=destination,
                        success=True,
                        distance_m=route["distance_m"],
                        duration_s=route["duration_s"],
                        source="real_api",
                        method="baidu_walking_route",
                        steps=steps_to_polyline(route.get("steps") or []),
                    )
                except BaiduMapError as exc:
                    return WalkingResult(
                        origin=origin,
                        destination=destination,
                        success=False,
                        distance_m=None,
                        duration_s=None,
                        source="real_api",
                        method="baidu_walking_route",
                        error_code=exc.code,
                        error_message=str(exc),
                    )

        rows: list[list[WalkingResult]] = []
        for origin in origins:
            rows.append(await asyncio.gather(*(calculate(origin, destination) for destination in destinations)))
        return rows

    @staticmethod
    def _provider_error(exc: BaiduMapError) -> MapProviderError:
        return MapProviderError(
            str(exc),
            code=exc.code,
            retryable=exc.retryable,
            rate_limited=exc.rate_limited,
        )

    @staticmethod
    def _has_location(item: dict) -> bool:
        location = item.get("location") or {}
        return "lng" in location and "lat" in location

    @staticmethod
    def _normalize_place(item: dict, category: str) -> FacilityResult:
        location = item["location"]
        return FacilityResult(
            id=str(item.get("uid") or f"{category}-{location['lng']}-{location['lat']}"),
            name=item.get("name") or category,
            category=category,
            lng=float(location["lng"]),
            lat=float(location["lat"]),
            address=item.get("address", ""),
        )

    @staticmethod
    def _deduplicate_places(places: list[FacilityResult]) -> list[FacilityResult]:
        """优先按百度 uid 去重，再用规范化名称与六位坐标防止多分词返回语义重复项。"""
        unique: list[FacilityResult] = []
        seen_ids: set[str] = set()
        seen_signatures: set[tuple[str, float, float]] = set()
        for place in places:
            normalized_name = re.sub(
                r"[\s\-_—·・（）()]",
                "",
                unicodedata.normalize("NFKC", place.name),
            ).casefold()
            signature = (normalized_name, round(place.lng, 6), round(place.lat, 6))
            if place.id in seen_ids or signature in seen_signatures:
                continue
            seen_ids.add(place.id)
            seen_signatures.add(signature)
            unique.append(place)
        return unique
