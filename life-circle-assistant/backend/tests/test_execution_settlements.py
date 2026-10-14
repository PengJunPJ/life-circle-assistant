import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.execution_ledger import ExecutionRepository, SettlementInput, execution_router
from app.storage import Database


@pytest.fixture
def settlement_client(tmp_path):
    database = Database(tmp_path / "settlements.db")
    database.migrate()
    repository = ExecutionRepository(database)
    ledger = repository.ensure("target", "analysis_task")
    ledger.charge("map_http_attempts", 2)
    repository.finish("target", "completed")
    app = FastAPI()
    app.state.execution_repository = repository
    app.include_router(execution_router())
    with TestClient(app) as client:
        yield client, repository, ledger


def receipt(client, **changes):
    cost = client.get("/api/executions/target").json()["cost"]
    payload = {
        "amount_cny": "12.34",
        "bill_reference": "提供方账单测试编号，非真实结算",
        "reviewer": "复核员",
        "evidence": "离线测试中已核对本次执行全部服务的费用，不是账户总账单",
        "expected_version": cost["settlement_version"],
        "expected_usage_sha256": cost["usage_sha256"],
        "scope": "execution_total",
    }
    return payload | changes


def test_receipt_persists_across_repository_restart_and_append_only_correction(settlement_client):
    client, repository, _ = settlement_client
    first_payload = receipt(client)
    response = client.post("/api/executions/target/settlements", json=first_payload)
    assert response.status_code == 200
    assert response.json()["version"] == 1
    assert client.get("/api/executions/target").json()["cost"]["settled_total"] == 12.34
    assert client.post("/api/executions/target/settlements", json=first_payload).status_code == 409
    correction = receipt(client, amount_cny="0", bill_reference="核验本次全部调用免费")
    assert client.post("/api/executions/target/settlements", json=correction).json()["version"] == 2
    summary = client.get("/api/executions/target").json()["cost"]
    assert summary["settled_total"] == 0
    assert summary["status"] == "manually_reconciled"
    fresh = ExecutionRepository(Database(repository.database.path))
    assert [item["amount_cny"] for item in fresh.settlements("target")] == [12.34, 0]
    assert len(client.get("/api/executions/target/settlements").json()["items"]) == 2
    with repository.database.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="不可修改"):
            connection.execute("UPDATE execution_settlements SET amount_cny='100' WHERE run_id='target'")
        with pytest.raises(sqlite3.IntegrityError, match="不可删除"):
            connection.execute("DELETE FROM execution_settlements WHERE run_id='target'")


def test_running_or_new_usage_never_keeps_a_known_settled_total(settlement_client):
    client, repository, ledger = settlement_client
    payload = receipt(client)
    repository.finish("target", "running")
    assert client.post("/api/executions/target/settlements", json=payload).status_code == 409
    repository.finish("target", "failed")
    assert client.post("/api/executions/target/settlements", json=payload).status_code == 200
    repository.finish("target", "running")
    assert client.get("/api/executions/target").json()["cost"]["settled_total"] is None
    ledger.charge("map_http_attempts")
    repository.finish("target", "completed")
    cost = client.get("/api/executions/target").json()["cost"]
    assert cost["settlement_stale"] is True
    assert cost["status"] == "settlement_stale"
    assert cost["settled_total"] is None
    assert len(repository.settlements("target")) == 1
    assert client.post("/api/executions/target/settlements", json=payload | {"expected_version": 1}).status_code == 409
    assert client.post("/api/executions/target/settlements", json=receipt(client, amount_cny="20")).status_code == 200


@pytest.mark.parametrize("amount", [-1, "NaN", "Infinity", "0.001", True, "1000000000000"])
def test_invalid_amounts_cannot_be_saved(settlement_client, amount):
    client, repository, _ = settlement_client
    assert client.post("/api/executions/target/settlements", json=receipt(client, amount_cny=amount)).status_code == 422
    assert repository.settlements("target") == []


@pytest.mark.parametrize("field", ["bill_reference", "reviewer", "evidence"])
def test_whitespace_is_not_billing_evidence(settlement_client, field):
    client, _, _ = settlement_client
    assert client.post("/api/executions/target/settlements", json=receipt(client, **{field: "   "})).status_code == 422


def test_concurrent_receipts_share_revision_guard_and_missing_run_is_404(settlement_client):
    client, repository, _ = settlement_client
    payload = SettlementInput(**receipt(client))

    def record():
        try:
            return repository.settle("target", payload)["version"]
        except ValueError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: record(), range(2)))
    assert outcomes.count(1) == 1
    assert outcomes.count("conflict") == 1
    assert client.get("/api/executions/missing/settlements").status_code == 404
    assert client.post("/api/executions/missing/settlements", json=receipt(client)).status_code == 404
