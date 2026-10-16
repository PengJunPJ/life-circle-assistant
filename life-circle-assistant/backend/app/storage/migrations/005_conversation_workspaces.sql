CREATE TABLE conversation_workspaces (
    id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL DEFAULT 0,
    state_json TEXT NOT NULL,
    pending_json TEXT,
    inflight_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE conversation_turns (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES conversation_workspaces(id),
    request_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    result_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(workspace_id, request_id)
);
ALTER TABLE analysis_tasks ADD COLUMN cancelled_at TEXT;
ALTER TABLE analysis_tasks ADD COLUMN idempotency_key TEXT;
ALTER TABLE analysis_tasks ADD COLUMN retry_of_task_id TEXT;
CREATE UNIQUE INDEX idx_analysis_tasks_idempotency ON analysis_tasks(idempotency_key);
CREATE UNIQUE INDEX idx_analysis_tasks_retry ON analysis_tasks(retry_of_task_id);
