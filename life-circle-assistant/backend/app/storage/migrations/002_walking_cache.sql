CREATE TABLE IF NOT EXISTS walking_cache (
    cache_key TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    travel_mode TEXT NOT NULL,
    origin_lng REAL NOT NULL,
    origin_lat REAL NOT NULL,
    destination_lng REAL NOT NULL,
    destination_lat REAL NOT NULL,
    distance_m REAL NOT NULL,
    duration_s REAL NOT NULL,
    result_source TEXT NOT NULL,
    result_method TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_walking_cache_expires_at
    ON walking_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_walking_cache_provider_mode
    ON walking_cache(provider_id, travel_mode);
