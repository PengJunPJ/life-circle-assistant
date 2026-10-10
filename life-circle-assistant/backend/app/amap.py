from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx


class AmapError(RuntimeError):
    """高德 Web 服务请求失败。"""

    def __init__(self, message: str, *, code: str = "provider_error", retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class AmapPoi:
    source_record_id: str
    name: str
    category: str
    lng: float
    lat: float
    address: str
    coordinate_system: str = "gcj02"


class AmapPoiClient:
    """按需调用高德 POI 和坐标转换接口，不保存响应。"""

    base_url = "https://restapi.amap.com"
    MAX_PAGES = 8
    MAX_OFFSET = 25

    def __init__(self, *, sleep=asyncio.sleep, monotonic=time.monotonic) -> None:
        self.key = os.getenv("AMAP_WEB_SERVICE_KEY", "").strip()
        self.qps = self._qps_from_env()
        self.request_count = 0
        self._client: httpx.AsyncClient | None = None
        self._sleep = sleep
        self._monotonic = monotonic
        self._rate_lock = asyncio.Lock()
        self._next_request_at = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.key)

    async def search_around(
        self,
        *,
        location_gcj02: tuple[float, float],
        keyword: str,
        radius_m: int,
    ) -> tuple[list[AmapPoi], dict[str, Any]]:
        if not self.configured:
            raise AmapError("缺少 AMAP_WEB_SERVICE_KEY", code="not_configured")
        pois: list[AmapPoi] = []
        truncated = False
        pages = 0
        for page in range(1, self.MAX_PAGES + 1):
            payload = await self._request(
                "/v3/place/around",
                {
                    "location": f"{location_gcj02[0]:.12g},{location_gcj02[1]:.12g}",
                    "keywords": keyword,
                    "radius": max(1, min(int(radius_m), 50_000)),
                    "offset": self.MAX_OFFSET,
                    "page": page,
                    "extensions": "base",
                    "sortrule": "distance",
                },
            )
            raw_items = payload.get("pois") or []
            page_items = [self._parse_poi(item, keyword) for item in raw_items]
            pois.extend(item for item in page_items if item is not None)
            pages = page
            if len(raw_items) < self.MAX_OFFSET:
                break
        else:
            truncated = True
        return pois, {"keyword": keyword, "pages": pages, "truncated": truncated, "returned_count": len(pois)}

    async def convert_from_baidu(self, coordinates: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if not coordinates:
            return []
        payload = await self._request(
            "/v3/assistant/coordinate/convert",
            {
                "locations": "|".join(f"{lng:.12g},{lat:.12g}" for lng, lat in coordinates),
                "coordsys": "baidu",
            },
        )
        converted = []
        for item in str(payload.get("locations") or "").split(";"):
            try:
                lng, lat = item.split(",", 1)
                converted.append((float(lng), float(lat)))
            except (TypeError, ValueError):
                raise AmapError("高德坐标转换返回格式错误", code="format_error") from None
        if len(converted) != len(coordinates):
            raise AmapError("高德坐标转换返回数量与请求不一致", code="format_error")
        return converted

    async def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self.request_count += 1
        last_error: AmapError | None = None
        for attempt in range(3):
            await self._wait_for_rate_limit()
            try:
                response = await self._client_instance().get(
                    f"{self.base_url}{path}", params={**params, "key": self.key}
                )
                response.raise_for_status()
                payload = response.json()
                if str(payload.get("status")) != "1":
                    info = str(payload.get("info") or "高德接口返回失败")
                    info_code = str(payload.get("infocode") or "provider_status")
                    retryable = info_code in {"10021", "10029", "10044", "10045"} or "QPS" in info.upper()
                    raise AmapError(info, code=info_code, retryable=retryable)
                return payload
            except AmapError as exc:
                last_error = exc
                if not exc.retryable or attempt == 2:
                    break
                await self._sleep(0.4 * (2**attempt))
            except (httpx.HTTPError, ValueError) as exc:
                last_error = AmapError(f"高德 HTTP/JSON 请求失败：{exc}", code="http_error", retryable=True)
                if attempt < 2:
                    await self._sleep(0.4 * (2**attempt))
        raise last_error or AmapError("高德请求失败")

    async def _wait_for_rate_limit(self) -> None:
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

    def _client_instance(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=8)
        return self._client

    @staticmethod
    def _parse_poi(item: Any, category: str) -> AmapPoi | None:
        if not isinstance(item, dict):
            return None
        location = str(item.get("location") or "")
        try:
            lng, lat = location.split(",", 1)
            return AmapPoi(
                source_record_id=str(item.get("id") or f"{category}:{location}:{item.get('name', '')}"),
                name=str(item.get("name") or category),
                category=category,
                lng=float(lng),
                lat=float(lat),
                address=str(item.get("address") or ""),
            )
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _qps_from_env() -> float:
        try:
            return max(0.0, float(os.getenv("AMAP_QPS", "1")))
        except ValueError:
            return 1.0

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
