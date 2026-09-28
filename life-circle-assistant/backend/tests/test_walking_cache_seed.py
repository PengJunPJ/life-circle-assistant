import json
from datetime import UTC, datetime, timedelta

from app.maps.provider import WalkingResult
from app.storage import Database, WalkingCacheRepository
from app.storage.walking_cache_seed import seed_from_env, seed_walking_cache_if_empty


def _seed_file(tmp_path, rows):
    path = tmp_path / "walking_cache_seed.json"
    path.write_text(json.dumps({"schema_version": 1, "rows": rows}), encoding="utf-8")
    return path


def _rows():
    return [
        {
            "provider_id": "baidu-web-service",
            "travel_mode": "walking",
            "origin_lng": 113.4872,
            "origin_lat": 23.1068,
            "destination_lng": 113.4887,
            "destination_lat": 23.1053,
            "distance_m": 1016,
            "duration_s": 868,
            "result_source": "real_api",
            "result_method": "baidu_walking_route_matrix",
        },
        {
            "provider_id": "baidu-web-service",
            "travel_mode": "walking",
            "origin_lng": 113.4872,
            "origin_lat": 23.1068,
            "destination_lng": 113.4904,
            "destination_lat": 23.1078,
            "distance_m": 633,
            "duration_s": 541,
            "result_source": "real_api",
            "result_method": "baidu_walking_route",
            "steps": [[113.4872, 23.1068], [113.4904, 23.1078]],
        },
        {"broken": True},
    ]


def test_seed_imports_into_empty_cache_and_restamps_ttl(tmp_path):
    database = Database(tmp_path / "seed-empty.db")
    database.migrate()
    cache = WalkingCacheRepository(database)
    now = datetime(2026, 9, 28, 4, 0, 0, tzinfo=UTC)

    inserted = seed_walking_cache_if_empty(cache, _rows(), ttl_seconds=3600, now=now)

    assert inserted == 2
    assert cache.count() == 2
    lookup = cache.get(
        "baidu-web-service",
        (113.4872, 23.1068),
        (113.4887, 23.1053),
        at=now + timedelta(minutes=1),
    )
    assert lookup.status == "hit"
    assert lookup.result is not None and lookup.result.distance_m == 1016
    # TTL 按导入时刻重盖，而不是沿用种子采集时间
    assert lookup.result.expires_at is not None
    assert datetime.fromisoformat(lookup.result.expires_at) > now + timedelta(minutes=30)
    with_steps = cache.get("baidu-web-service", (113.4872, 23.1068), (113.4904, 23.1078), at=now)
    assert with_steps.result is not None and with_steps.result.steps == [
        [113.4872, 23.1068],
        [113.4904, 23.1078],
    ]


def test_seed_never_overwrites_existing_cache(tmp_path):
    database = Database(tmp_path / "seed-warm.db")
    database.migrate()
    cache = WalkingCacheRepository(database)
    cache.put(
        "baidu-web-service",
        WalkingResult(
            origin=(113.4872, 23.1068),
            destination=(113.4887, 23.1053),
            success=True,
            distance_m=1,
            duration_s=1,
            source="real_api",
            method="baidu_walking_route",
        ),
        ttl_seconds=3600,
    )

    assert seed_walking_cache_if_empty(cache, _rows(), ttl_seconds=3600) == 0
    assert cache.count() == 1
    lookup = cache.get("baidu-web-service", (113.4872, 23.1068), (113.4887, 23.1053))
    assert lookup.result is not None and lookup.result.distance_m == 1


def test_seed_from_env_respects_disable_flag(tmp_path, monkeypatch):
    path = _seed_file(tmp_path, _rows())
    database = Database(tmp_path / "seed-disabled.db")
    database.migrate()
    cache = WalkingCacheRepository(database)
    monkeypatch.setenv("LIFE_CIRCLE_SEED_WALKING_CACHE", "0")
    monkeypatch.setattr("app.storage.walking_cache_seed.DEFAULT_SEED_PATH", path)

    assert seed_from_env(cache, ttl_seconds=3600) == 0
    assert cache.count() == 0


def test_seed_from_env_loads_default_path(tmp_path, monkeypatch):
    path = _seed_file(tmp_path, _rows())
    database = Database(tmp_path / "seed-enabled.db")
    database.migrate()
    cache = WalkingCacheRepository(database)
    monkeypatch.delenv("LIFE_CIRCLE_SEED_WALKING_CACHE", raising=False)
    monkeypatch.setattr("app.storage.walking_cache_seed.DEFAULT_SEED_PATH", path)

    assert seed_from_env(cache, ttl_seconds=3600) == 2
    assert cache.count() == 2
