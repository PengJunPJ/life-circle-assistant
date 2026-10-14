CREATE TABLE execution_settlements (
    run_id TEXT NOT NULL REFERENCES execution_runs(id),
    version INTEGER NOT NULL CHECK(version > 0),
    amount_cny TEXT NOT NULL,
    bill_reference TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    evidence TEXT NOT NULL,
    usage_sha256 TEXT NOT NULL,
    usage_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(run_id, version)
);

CREATE TRIGGER execution_settlements_no_update
BEFORE UPDATE ON execution_settlements
BEGIN
    SELECT RAISE(ABORT, '结算记录不可修改，请追加更正版本');
END;

CREATE TRIGGER execution_settlements_no_delete
BEFORE DELETE ON execution_settlements
BEGIN
    SELECT RAISE(ABORT, '结算记录不可删除');
END;
