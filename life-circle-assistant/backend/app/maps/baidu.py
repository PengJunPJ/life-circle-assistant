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
        # 多坐标对走百度批量算路（/routematrix/v2/walking）一次取回矩阵；
        # 单坐标对仍走 directionlite 以保留 steps 折线供步行路线预览。
        return True

    # 百度批量算路单次请求的点对乘积上限：实测 10×10=100 可用、16×10=160 报
    # “点对数量超出限制”，故按 100 对分块并留原点分块余量。
    BATCH_PAIR_LIMIT = 100
    BATCH_ORIGIN_CHUNK = 10

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
        if len(origins) * len(destinations) <= 1:
            # 单坐标对走 directionlite：批量算路不返回 steps，而步行路线预览需要折线。
            return [
                list(await asyncio.gather(*(self._pair_result(origin, destination, semaphore) for destination in destinations)))
                for origin in origins
            ]
        matrix: list[list[WalkingResult | None]] = [[None] * len(destinations) for _ in origins]
        for origin_start in range(0, len(origins), self.BATCH_ORIGIN_CHUNK):
            origin_chunk = origins[origin_start : origin_start + self.BATCH_ORIGIN_CHUNK]
            chunk_size = max(1, self.BATCH_PAIR_LIMIT // len(origin_chunk))
            for dest_start in range(0, len(destinations), chunk_size):
                dest_chunk = destinations[dest_start : dest_start + chunk_size]
                await self._fill_batch_chunk(matrix, origin_start, dest_start, origin_chunk, dest_chunk, semaphore)
        return [
            [
                item
                if item is not None
                else WalkingResult(
                    origin=origin,
                    destination=destination,
                    success=False,
                    distance_m=None,
                    duration_s=None,
                    source="real_api",
                    method="baidu_walking_route_matrix",
                    error_code="format_error",
                    error_message="批量算路分块未填充结果",
                )
                for destination, item in zip(destinations, row)
            ]
            for origin, row in zip(origins, matrix)
        ]

    async def _fill_batch_chunk(
        self,
        matrix: list[list[WalkingResult | None]],
        origin_offset: int,
        dest_offset: int,
        origin_chunk: list[tuple[float, float]],
        dest_chunk: list[tuple[float, float]],
        semaphore: asyncio.Semaphore,
    ) -> None:
        try:
            flat = await self.client.batch_walking(origin_chunk, dest_chunk)
        except BaiduMapError:
            flat = None
        if flat is not None:
            for origin_index, origin in enumerate(origin_chunk):
                for dest_index, destination in enumerate(dest_chunk):
                    item = flat[origin_index * len(dest_chunk) + dest_index]
                    matrix[origin_offset + origin_index][dest_offset + dest_index] = WalkingResult(
                        origin=origin,
                        destination=destination,
                        success=True,
                        distance_m=item["distance_m"],
                        duration_s=item["duration_s"],
                        source="real_api",
                        method="baidu_walking_route_matrix",
                    )
            return
        # 分块批量失败：该块退化为逐对 directionlite，保证结果可审计而非整矩阵失败
        indexes = [(oi, di) for oi in range(len(origin_chunk)) for di in range(len(dest_chunk))]
        results = await asyncio.gather(
            *(self._pair_result(origin_chunk[oi], dest_chunk[di], semaphore) for oi, di in indexes)
        )
        for (oi, di), result in zip(indexes, results):
            matrix[origin_offset + oi][dest_offset + di] = result

    async def _pair_result(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        semaphore: asyncio.Semaphore,
    ) -> WalkingResult:
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
