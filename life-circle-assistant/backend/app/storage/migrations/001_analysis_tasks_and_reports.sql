CREATE TABLE IF NOT EXISTS analysis_tasks (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    stage TEXT NOT NULL,
    stage_label TEXT NOT NULL,
    progress INTEGER NOT NULL CHECK (progress BETWEEN 0 AND 100),
    request_json TEXT NOT NULL,
    report_id TEXT,
    rerun_of_report_id TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS analysis_reports (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE,
    schema_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    center_address TEXT NOT NULL,
    center_lng REAL NOT NULL,
    center_lat REAL NOT NULL,
    minutes INTEGER NOT NULL,
    mode TEXT NOT NULL,
    categories_json TEXT NOT NULL,
    report_json TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES analysis_tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_analysis_tasks_created_at
    ON analysis_tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_tasks_status
    ON analysis_tasks(status);
CREATE INDEX IF NOT EXISTS idx_analysis_reports_completed_at
    ON analysis_reports(completed_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_reports_center
    ON analysis_reports(center_address, completed_at DESC);

CREATE TRIGGER IF NOT EXISTS analysis_reports_immutable_update
BEFORE UPDATE ON analysis_reports
BEGIN
    SELECT RAISE(ABORT, 'analysis reports are immutable');
END;

CREATE TRIGGER IF NOT EXISTS analysis_reports_immutable_delete
BEFORE DELETE ON analysis_reports
BEGIN
    SELECT RAISE(ABORT, 'analysis reports are immutable');
END;
