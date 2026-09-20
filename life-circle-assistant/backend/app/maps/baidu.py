from __future__ import annotations

import asyncio

from ..baidu import BaiduMapClient, BaiduMapError
from .provider import (
    FacilityResult,
    LocationResult,
    MapProviderError,
    ProviderDescriptor,
    WalkingResult,
)


FACILITY_QUERIES = {
    "market": "菜市场,农贸市场,生鲜超市",
    "pharmacy": "药店",
    "school": "小学",
    "medical": "社区卫生服务中心,医院,诊所",
}


class BaiduMapProvider:
    def __init__(self, client: BaiduMapClient | None = None, concurrency: int = 6) -> None:
        self.client = client or BaiduMapClient()
        self.concurrency = concurrency

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
            raise MapProviderError(str(exc)) from exc
        return [LocationResult(lng=result["lng"], lat=result["lat"], address=result["address"])]

    async def reverse_geocode(self, lng: float, lat: float) -> LocationResult:
        try:
            result = await self.client.reverse_geocode(lng, lat)
        except BaiduMapError as exc:
            raise MapProviderError(str(exc)) from exc
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
            raise MapProviderError(str(exc)) from exc
        return [self._normalize_place(item, "unknown") for item in results if self._has_location(item)]

    async def search_facilities(
        self,
        category: str,
        center: tuple[float, float],
        radius_m: int = 1_000,
    ) -> list[FacilityResult]:
        query = FACILITY_QUERIES.get(category)
        if not query:
            raise MapProviderError(f"不支持的民生设施类别：{category}")
        try:
            results = await self.client.search_poi(query, center[0], center[1], radius_m)
        except BaiduMapError as exc:
            raise MapProviderError(str(exc)) from exc
        return [self._normalize_place(item, category) for item in results if self._has_location(item)]

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
                        error_code="walking_request_failed",
                        error_message=str(exc),
                    )

        rows: list[list[WalkingResult]] = []
        for origin in origins:
            rows.append(await asyncio.gather(*(calculate(origin, destination) for destination in destinations)))
        return rows

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
