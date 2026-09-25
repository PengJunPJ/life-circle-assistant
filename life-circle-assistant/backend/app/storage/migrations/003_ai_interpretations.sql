CREATE TABLE IF NOT EXISTS ai_interpretations (
    id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    intent TEXT NOT NULL,
    question TEXT,
    result_json TEXT NOT NULL,
    mode TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    FOREIGN KEY(report_id) REFERENCES analysis_reports(id)
);

CREATE INDEX IF NOT EXISTS idx_ai_interpretations_report
    ON ai_interpretations(report_id, generated_at DESC);
