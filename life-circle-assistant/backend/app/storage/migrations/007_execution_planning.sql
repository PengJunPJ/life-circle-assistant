CREATE TABLE execution_runs (
    id TEXT PRIMARY KEY,
    entrypoint TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    budget_json TEXT NOT NULL,
    usage_json TEXT NOT NULL DEFAULT '{}',
    versions_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE execution_checkpoints (
    run_id TEXT NOT NULL REFERENCES execution_runs(id),
    call_key TEXT NOT NULL,
    operation TEXT NOT NULL,
    status TEXT NOT NULL,
    result_json TEXT,
    units INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(run_id,call_key)
);
CREATE TABLE planning_candidates (
    report_id TEXT NOT NULL,
    id TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(report_id,id)
);
