CREATE TABLE planning_demand (
    report_id TEXT NOT NULL,
    grid_id TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(report_id,grid_id)
);
