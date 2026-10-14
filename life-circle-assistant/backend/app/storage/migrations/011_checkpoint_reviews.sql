CREATE TABLE execution_checkpoint_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES execution_runs(id),
    call_key TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    evidence TEXT NOT NULL,
    created_at TEXT NOT NULL
);
