CREATE TABLE IF NOT EXISTS verified_spatial_edges (
    id TEXT PRIMARY KEY,
    center_key TEXT NOT NULL,
    grid_schema TEXT NOT NULL,
    first_grid_id TEXT NOT NULL,
    second_grid_id TEXT NOT NULL,
    blocked INTEGER NOT NULL CHECK (blocked IN (0, 1)),
    source TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    UNIQUE(center_key, grid_schema, first_grid_id, second_grid_id)
);
CREATE INDEX IF NOT EXISTS verified_spatial_edges_scope ON verified_spatial_edges(center_key, grid_schema);
