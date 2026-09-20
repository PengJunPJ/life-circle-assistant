from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


DataSourceKind = Literal["real_api", "cache", "local_snapshot", "interpolation", "degraded_estimate"]


class MapProviderError(RuntimeError):
    """地图提供方无法完成请求时抛出的统一异常。"""


@dataclass(frozen=True)
class ProviderDescriptor:
    id: str
    mode: Literal["real", "snapshot", "fixture"]
    source: DataSourceKind
    label: str
    is_latest_real_measurement: bool


@dataclass(frozen=True)
class LocationResult:
    lng: float
    lat: float
    address: str


@dataclass(frozen=True)
class FacilityResult:
    id: str
    name: str
    category: str
    lng: float
    lat: float
    address: str = ""


@dataclass(frozen=True)
class WalkingResult:
    origin: tuple[float, float]
    destination: tuple[float, float]
    success: bool
    distance_m: float | None
    duration_s: float | None
    source: DataSourceKind
    method: str
    error_code: str | None = None
    error_message: str | None = None


class MapProvider(Protocol):
    @property
    def descriptor(self) -> ProviderDescriptor: ...

    async def geocode(self, address: str, city: str = "广州") -> list[LocationResult]: ...

    async def reverse_geocode(self, lng: float, lat: float) -> LocationResult: ...

    async def search_places(
        self,
        query: str,
        center: tuple[float, float],
        radius_m: int = 1_000,
    ) -> list[FacilityResult]: ...

    async def search_facilities(
        self,
        category: str,
        center: tuple[float, float],
        radius_m: int = 1_000,
    ) -> list[FacilityResult]: ...

    async def walking_matrix(
        self,
        origins: list[tuple[float, float]],
        destinations: list[tuple[float, float]],
    ) -> list[list[WalkingResult]]: ...
