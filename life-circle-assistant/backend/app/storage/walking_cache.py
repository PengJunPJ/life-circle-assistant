from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..maps.provider import DataSourceKind, WalkingResult
from .database import Database


COORDINATE_PRECISION = 6


@dataclass(frozen=True)
class CacheLookup:
    status: str
    result: WalkingResult | None = None


class WalkingCacheRepository:
    """按有方向坐标对、出行方式和提供方隔离的步行结果缓存。"""

    def __init__(self, database: Database) -> None:
        self.database = database

    def get(
        self,
        provider_id: str,
        origin: tuple[float, float],
        destination: tuple[float, float],
        travel_mode: str = "walking",
        *,
        at: datetime | None = None,
    ) -> CacheLookup:
        instant = at or datetime.now(timezone.utc)
        cache_key = self.make_key(provider_id, origin, destination, travel_mode)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM walking_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return CacheLookup("miss")
        expires_at = _parse_timestamp(row["expires_at"])
        if expires_at <= instant:
            return CacheLookup("expired")
        return CacheLookup(
            "hit",
            WalkingResult(
                origin=origin,
                destination=destination,
                success=True,
                distance_m=float(row["distance_m"]),
                duration_s=float(row["duration_s"]),
                source="cache",
                method="walking_cache",
                underlying_source=row["result_source"],
                cached_at=row["created_at"],
                expires_at=row["expires_at"],
                steps=_parse_steps(row["steps_json"] if "steps_json" in row.keys() else None),
            ),
        )

    def put(
        self,
        provider_id: str,
        result: WalkingResult,
        travel_mode: str = "walking",
        *,
        ttl_seconds: int,
        created_at: datetime | None = None,
    ) -> None:
        if not result.success or result.distance_m is None or result.duration_s is None:
            return
        created = created_at or datetime.now(timezone.utc)
        expires = created + timedelta(seconds=ttl_seconds)
        cache_key = self.make_key(provider_id, result.origin, result.destination, travel_mode)
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO walking_cache(
                    cache_key, provider_id, travel_mode,
                    origin_lng, origin_lat, destination_lng, destination_lat,
                    distance_m, duration_s, result_source, result_method,
                    created_at, expires_at, steps_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    distance_m = excluded.distance_m,
                    duration_s = excluded.duration_s,
                    result_source = excluded.result_source,
                    result_method = excluded.result_method,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at,
                    steps_json = COALESCE(excluded.steps_json, steps_json)
                """,
                (
                    cache_key,
                    provider_id,
                    travel_mode,
                    round(result.origin[0], COORDINATE_PRECISION),
                    round(result.origin[1], COORDINATE_PRECISION),
                    round(result.destination[0], COORDINATE_PRECISION),
                    round(result.destination[1], COORDINATE_PRECISION),
                    result.distance_m,
                    result.duration_s,
                    result.underlying_source or result.source,
                    result.method,
                    created.isoformat(),
                    expires.isoformat(),
                    json.dumps(result.steps) if result.steps else None,
                ),
            )
            connection.commit()

    @staticmethod
    def make_key(
        provider_id: str,
        origin: tuple[float, float],
        destination: tuple[float, float],
        travel_mode: str,
    ) -> str:
        normalized = "|".join(
            (
                provider_id,
                travel_mode,
                f"{origin[0]:.{COORDINATE_PRECISION}f}",
                f"{origin[1]:.{COORDINATE_PRECISION}f}",
                f"{destination[0]:.{COORDINATE_PRECISION}f}",
                f"{destination[1]:.{COORDINATE_PRECISION}f}",
            )
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_steps(value: str | None) -> list | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, list) else None
