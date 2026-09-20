from __future__ import annotations

from ..baidu import haversine_meters
from ..mock_data import CATEGORIES, CENTER, POIS
from .provider import (
    FacilityResult,
    LocationResult,
    MapProviderError,
    ProviderDescriptor,
    WalkingResult,
)

SNAPSHOT_SUPPORTED_RADIUS_M = 1_000


class SnapshotMapProvider:
    def __init__(self, snapshot: dict | None = None) -> None:
        self.snapshot = snapshot or {}
        self.center = self.snapshot.get("center") or CENTER
        self.pois = self.snapshot.get("pois") or POIS

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            id="huangpu-local-snapshot",
            mode="snapshot",
            source="local_snapshot",
            label="黄埔区本地百度数据快照",
            is_latest_real_measurement=False,
        )

    async def geocode(self, address: str, city: str = "广州") -> list[LocationResult]:
        normalized = address.strip()
        known_address = str(self.center["address"])
        if not normalized or not any(token in normalized for token in ("红山", "海韵东路", "离线样例", known_address)):
            raise MapProviderError("本地快照只支持内置的红山街道海韵东路离线样例中心，不能解析任意地址")
        return [LocationResult(lng=float(self.center["lng"]), lat=float(self.center["lat"]), address=known_address)]

    async def reverse_geocode(self, lng: float, lat: float) -> LocationResult:
        distance = haversine_meters((lng, lat), (float(self.center["lng"]), float(self.center["lat"])))
        if distance > SNAPSHOT_SUPPORTED_RADIUS_M:
            raise MapProviderError("该位置超出本地快照支持范围；离线模式仅支持红山街道海韵东路离线样例中心周边 1 公里")
        address = str(self.center["address"])
        if distance > 30:
            address = f"{address}（样例范围内坐标选点）"
        return LocationResult(lng=lng, lat=lat, address=address)

    async def search_places(
        self,
        query: str,
        center: tuple[float, float],
        radius_m: int = 1_000,
    ) -> list[FacilityResult]:
        return [
            self._facility(item)
            for item in self.pois
            if query in item["name"]
            or query in item.get("category", "")
            or query in CATEGORIES.get(item.get("category", ""), {}).get("label", "")
        ]

    async def search_facilities(
        self,
        category: str,
        center: tuple[float, float],
        radius_m: int = 1_000,
    ) -> list[FacilityResult]:
        return [self._facility(item) for item in self.pois if item.get("category") == category]

    async def walking_matrix(
        self,
        origins: list[tuple[float, float]],
        destinations: list[tuple[float, float]],
    ) -> list[list[WalkingResult]]:
        known_minutes = {
            (round(float(item["lng"]), 6), round(float(item["lat"]), 6)): float(item["walk_minutes"])
            for item in self.pois
            if item.get("walk_minutes") is not None
        }
        rows: list[list[WalkingResult]] = []
        snapshot_center = (float(self.center["lng"]), float(self.center["lat"]))
        for origin in origins:
            row: list[WalkingResult] = []
            for destination in destinations:
                distance = haversine_meters(origin, destination)
                minutes = known_minutes.get((round(destination[0], 6), round(destination[1], 6)))
                if minutes is None or haversine_meters(origin, snapshot_center) > 100:
                    # 快照没有任意坐标对路线，使用明确标记的步行估算，不能冒充实时结果。
                    minutes = max(1.0, distance / 75)
                    source = "degraded_estimate"
                    method = "straight_line_walking_estimate"
                else:
                    source = "local_snapshot"
                    method = "snapshot_walking_result"
                row.append(
                    WalkingResult(
                        origin=origin,
                        destination=destination,
                        success=True,
                        distance_m=distance,
                        duration_s=minutes * 60,
                        source=source,
                        method=method,
                    )
                )
            rows.append(row)
        return rows

    @staticmethod
    def _facility(item: dict) -> FacilityResult:
        return FacilityResult(
            id=str(item["id"]),
            name=str(item["name"]),
            category=str(item["category"]),
            lng=float(item["lng"]),
            lat=float(item["lat"]),
            address=str(item.get("address", "")),
        )
