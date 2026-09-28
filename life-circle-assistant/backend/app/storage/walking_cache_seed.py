"""默认中心步行缓存种子的加载与启动导入。

评审方从干净环境启动时，步行缓存为空，首次真实分析需要现场调用百度
批量算路（冷缓存约两分钟量级）。为了让"快速跑通演示"不依赖现场配额
和网络，仓库随附一份默认演示中心的真实测算缓存种子；启动时若缓存表
为空则导入，并按启动时刻重盖 TTL。

种子只是历史真实测算的快照，导入后会通过报告既有的缓存命中披露和
``walking_cache_used`` 质量事件可见；设置
``LIFE_CIRCLE_SEED_WALKING_CACHE=0`` 可关闭导入，强制现场真实测算。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .walking_cache import WalkingCacheRepository

DEFAULT_SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "walking_cache_seed.json"
ENV_SEED_ENABLED = "LIFE_CIRCLE_SEED_WALKING_CACHE"


def seed_enabled() -> bool:
    return os.getenv(ENV_SEED_ENABLED, "1").strip().lower() not in {"0", "false", "no", "off"}


def load_seed_rows(path: Path | str | None = None) -> list[dict[str, Any]]:
    seed_path = Path(path) if path is not None else DEFAULT_SEED_PATH
    if not seed_path.exists():
        return []
    try:
        payload = json.loads(seed_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else None
    return [row for row in rows or [] if isinstance(row, dict)]


def seed_walking_cache_if_empty(
    cache: WalkingCacheRepository,
    rows: list[dict[str, Any]],
    ttl_seconds: int,
    *,
    now: datetime | None = None,
) -> int:
    """缓存表为空时导入种子；已有任何缓存行则完全跳过，不覆盖现场数据。"""

    if not rows or cache.count() > 0:
        return 0
    from ..maps.provider import WalkingResult

    created = now or datetime.now(timezone.utc)
    inserted = 0
    for row in rows:
        try:
            origin = (float(row["origin_lng"]), float(row["origin_lat"]))
            destination = (float(row["destination_lng"]), float(row["destination_lat"]))
            result = WalkingResult(
                origin=origin,
                destination=destination,
                success=True,
                distance_m=float(row["distance_m"]),
                duration_s=float(row["duration_s"]),
                source=row.get("result_source") or "real_api",
                method=row.get("result_method") or "baidu_walking_route",
                steps=row.get("steps") or None,
            )
        except (KeyError, TypeError, ValueError):
            continue
        cache.put(
            row.get("provider_id") or "baidu-web-service",
            result,
            row.get("travel_mode") or "walking",
            ttl_seconds=ttl_seconds,
            created_at=created,
        )
        inserted += 1
    return inserted


def seed_from_env(cache: WalkingCacheRepository, ttl_seconds: int) -> int:
    if not seed_enabled():
        return 0
    return seed_walking_cache_if_empty(cache, load_seed_rows(), ttl_seconds)
