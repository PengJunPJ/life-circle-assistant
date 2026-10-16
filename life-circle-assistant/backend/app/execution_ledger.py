"""所有入口共享预算与持久用量；任务按调用检查点恢复，计费不明调用禁止自动重放。"""

from __future__ import annotations

import hashlib
import json
import math
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .maps.provider import MapProviderError
from .storage.repositories import _dump, now

VERSIONS = {
    "rules": "fixed-scoring-v1",
    "tools": "workspace-tools-v3",
    "facts": "fact-slots-v1",
    "checkpoint": "provider-call-v1",
}
DEFAULT_BUDGET = {
    "route_pairs": 5000,
    "model_http_attempts": 7,
    "model_adapter_calls": 7,
    "map_adapter_calls": 300,
    "map_http_attempts": 1000,
    "native_http_attempts": 5,
    "embedding_http_attempts": 20,
    "ocr_http_attempts": 10,
}


def usage_fingerprint(usage):
    return hashlib.sha256(json.dumps(usage, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ExecutionRepository:
    def __init__(self, database):
        self.database = database

    def ensure(self, identifier, entrypoint, budget=None):
        with self.database.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO execution_runs(id,entrypoint,budget_json,versions_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (identifier, entrypoint, _dump(budget or DEFAULT_BUDGET), _dump(VERSIONS), now(), now()),
            )
            connection.commit()
        return ExecutionLedger(self, identifier)

    def get(self, identifier):
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM execution_runs WHERE id=?", (identifier,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "entrypoint": row["entrypoint"],
            "status": row["status"],
            "budget": json.loads(row["budget_json"]),
            "usage": json.loads(row["usage_json"]),
            "versions": json.loads(row["versions_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def finish(self, identifier, status):
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE execution_runs SET status=?,updated_at=? WHERE id=?", (status, now(), identifier)
            )
            connection.commit()

    def settlements(self, identifier):
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM execution_settlements WHERE run_id=? ORDER BY version", (identifier,)
            ).fetchall()
        return [
            {
                "version": row["version"],
                "amount_cny": float(Decimal(row["amount_cny"])),
                "bill_reference": row["bill_reference"],
                "reviewer": row["reviewer"],
                "evidence": row["evidence"],
                "usage_sha256": row["usage_sha256"],
                "usage": json.loads(row["usage_json"]),
                "created_at": row["created_at"],
                "scope": "execution_total",
                "currency": "CNY",
            }
            for row in rows
        ]

    def settle(self, identifier, payload):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute("SELECT * FROM execution_runs WHERE id=?", (identifier,)).fetchone()
            if not run:
                raise LookupError("执行账本不存在")
            if run["status"] not in {"completed", "failed", "cancelled", "interrupted"}:
                raise ValueError("执行尚未结束，不能核验本次执行的全部费用")
            usage = json.loads(run["usage_json"])
            fingerprint = usage_fingerprint(usage)
            if fingerprint != payload.expected_usage_sha256:
                raise ValueError("执行用量已变化，请重新核对账单")
            version = connection.execute(
                "SELECT COALESCE(MAX(version),0) FROM execution_settlements WHERE run_id=?", (identifier,)
            ).fetchone()[0]
            if version != payload.expected_version:
                raise ValueError("结算版本已变化，请刷新后复核")
            connection.execute(
                "INSERT INTO execution_settlements VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    version + 1,
                    str(payload.amount_cny),
                    payload.bill_reference,
                    payload.reviewer,
                    payload.evidence,
                    fingerprint,
                    run["usage_json"],
                    now(),
                ),
            )
            connection.commit()
        return next(item for item in self.settlements(identifier) if item["version"] == version + 1)

    def checkpoint(self, identifier, key):
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM execution_checkpoints WHERE run_id=? AND call_key=?", (identifier, key)
            ).fetchone()
        return dict(row) if row else None

    def reserve(self, identifier, key, operation, units):
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO execution_checkpoints VALUES(?,?,?,'inflight',NULL,?,?) "
                "ON CONFLICT(run_id,call_key) DO UPDATE SET status='inflight',updated_at=excluded.updated_at "
                "WHERE execution_checkpoints.status='retry_authorized'",
                (identifier, key, operation, units, now()),
            )
            connection.commit()

    def uncertain(self, identifier):
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT call_key,operation,updated_at FROM execution_checkpoints WHERE run_id=? AND status='inflight'",
                (identifier,),
            ).fetchall()
        return [dict(row) for row in rows]

    def authorize_retry(self, identifier, key, reviewer, evidence):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE execution_checkpoints SET status='retry_authorized',updated_at=? WHERE run_id=? AND call_key=? AND status='inflight'",
                (now(), identifier, key),
            )
            if cursor.rowcount != 1:
                raise ValueError("只允许核对未决检查点；已完成调用不得重放")
            connection.execute(
                "INSERT INTO execution_checkpoint_reviews(run_id,call_key,reviewer,evidence,created_at) VALUES(?,?,?,?,?)",
                (identifier, key, reviewer, evidence, now()),
            )
            connection.commit()

    def complete(self, identifier, key, value):
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE execution_checkpoints SET status='completed',result_json=?,updated_at=? WHERE run_id=? AND call_key=?",
                (_dump(value), now(), identifier, key),
            )
            connection.commit()


class ExecutionLedger:
    def __init__(self, repository, identifier):
        self.repository, self.id = repository, identifier

    def charge(self, kind, units=1):
        self.charge_many({kind: units})

    def charge_many(self, charges):
        if any(isinstance(units, bool) or not isinstance(units, int) or units < 0 for units in charges.values()):
            raise ValueError("账本用量必须为非负整数")
        with self.repository.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT budget_json,usage_json FROM execution_runs WHERE id=?", (self.id,)
            ).fetchone()
            budget, usage = json.loads(row["budget_json"]), json.loads(row["usage_json"])
            if any(kind in budget and usage.get(kind, 0) + units > budget[kind] for kind, units in charges.items()):
                raise MapProviderError("统一执行预算已用尽，未发送新请求", code="execution_budget_exhausted")
            for kind, units in charges.items():
                usage[kind] = usage.get(kind, 0) + units
            connection.execute(
                "UPDATE execution_runs SET usage_json=?,updated_at=? WHERE id=?", (_dump(usage), now(), self.id)
            )
            connection.commit()

    def version(self, key, value):
        with self.repository.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT versions_json FROM execution_runs WHERE id=?", (self.id,)).fetchone()
            versions = json.loads(row["versions_json"])
            versions[key] = value
            connection.execute(
                "UPDATE execution_runs SET versions_json=?,updated_at=? WHERE id=?", (_dump(versions), now(), self.id)
            )
            connection.commit()

    def summary(self):
        result = self.repository.get(self.id)
        usage = result["usage"]

        # 请求计价与路线对/token计价是替代口径，不能同时相加。
        def pricing_basis(setting, alternatives):
            configured = os.getenv(setting, "").strip()
            if configured:
                return configured if configured in alternatives else "unknown"
            provided = [unit for unit, env in alternatives.items() if os.getenv(env, "").strip()]
            return provided[0] if len(provided) == 1 else "unknown"

        map_basis = pricing_basis(
            "MAP_PRICING_UNIT", {"request": "MAP_REQUEST_PRICE_CNY", "route_pair": "ROUTE_PAIR_PRICE_CNY"}
        )
        embedding_basis = pricing_basis(
            "EMBEDDING_PRICING_UNIT",
            {"tokens": "EMBEDDING_PRICE_CNY_PER_MILLION", "request": "EMBEDDING_REQUEST_PRICE_CNY"},
        )
        prices = {
            "prompt_tokens": "LLM_INPUT_PRICE_CNY_PER_MILLION",
            "completion_tokens": "LLM_OUTPUT_PRICE_CNY_PER_MILLION",
            "native_http_attempts": "NATIVE_ISOCHRONE_PRICE_CNY",
            "ocr_http_attempts": "OCR_REQUEST_PRICE_CNY",
        }
        priced_usage = dict(usage)
        if map_basis == "request":
            prices["map_http_attempts"] = "MAP_REQUEST_PRICE_CNY"
            priced_usage["map_http_attempts"] = max(
                0, usage.get("map_http_attempts", 0) - usage.get("native_http_attempts", 0)
            )
        elif map_basis == "route_pair":
            prices["route_pairs"] = "ROUTE_PAIR_PRICE_CNY"
            # 路线对价格无法代表地理编码、POI检索等其他HTTP的价格。
        if embedding_basis == "tokens":
            prices["embedding_input_tokens"] = "EMBEDDING_PRICE_CNY_PER_MILLION"
        elif embedding_basis == "request":
            prices["embedding_http_attempts"] = "EMBEDDING_REQUEST_PRICE_CNY"
        costs = {}
        for kind, name in prices.items():
            if not priced_usage.get(kind):
                continue
            value = os.getenv(name, "").strip()
            try:
                price = float(value) if value else None
                if price is not None and (not math.isfinite(price) or price < 0):
                    price = None
            except ValueError:
                price = None
            costs[kind] = (
                priced_usage[kind] * price / (1000000 if kind.endswith("tokens") else 1) if price is not None else None
            )
        if map_basis == "unknown" and usage.get("map_http_attempts", 0) > usage.get("native_http_attempts", 0):
            costs["map_pricing_unknown"] = None
        if map_basis == "route_pair" and usage.get("map_http_attempts", 0) > usage.get(
            "route_http_attempts", 0
        ) + usage.get("native_http_attempts", 0):
            costs["non_route_map_pricing_unknown"] = None
        if embedding_basis == "unknown" and usage.get("embedding_http_attempts"):
            costs["embedding_pricing_unknown"] = None
        if embedding_basis == "tokens" and usage.get("embedding_usage_unknown"):
            costs["embedding_usage_unknown"] = None
        if usage.get("model_responses_usage_unknown"):
            costs["model_usage_unknown"] = None
        result["cost"] = {
            "currency": "CNY",
            "items": costs,
            "estimated_total": sum(costs.values()) if costs and all(v is not None for v in costs.values()) else None,
            "settled_total": None,
            "status": "estimate_only",
            "pricing_basis": {"map": map_basis, "embedding": embedding_basis},
            "disclosure": "请求与路线对/token计价互斥；价格或用量缺失保持未知，真实结算以提供方账单为准。",
        }
        settlements = self.repository.settlements(self.id)
        fingerprint = usage_fingerprint(usage)
        latest = settlements[-1] if settlements else None
        stale = bool(
            latest
            and (
                latest["usage_sha256"] != fingerprint
                or result["status"] not in {"completed", "failed", "cancelled", "interrupted"}
            )
        )
        result["cost"].update(
            {
                "settlement_version": latest["version"] if latest else 0,
                "usage_sha256": fingerprint,
                "settlement_stale": stale,
            }
        )
        if latest:
            result["cost"].update(
                {
                    "settled_total": None if stale else latest["amount_cny"],
                    "status": "settlement_stale" if stale else "manually_reconciled",
                    "disclosure": "人工核验记录仅对应提交时的本次执行用量；续算新增用量后旧结算失效。复核人是审计字段，并非已认证身份。",
                }
            )
        return result


_active: ContextVar[ExecutionLedger | None] = ContextVar("execution_ledger", default=None)


@contextmanager
def bind_execution(ledger):
    token = _active.set(ledger)
    try:
        yield ledger
    finally:
        _active.reset(token)


def charge_external(kind, units=1):
    ledger = _active.get()
    if ledger:
        ledger.charge(kind, units)


def charge_external_many(charges):
    ledger = _active.get()
    if ledger:
        ledger.charge_many(charges)


def record_version(key, value):
    ledger = _active.get()
    if ledger:
        ledger.version(key, value)


def record_model_usage(payload, model):
    record_version("model", model)
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        charge_external("model_responses_usage_unknown")
        return
    if any(type(usage.get(kind)) is not int or usage[kind] < 0 for kind in ("prompt_tokens", "completion_tokens")):
        charge_external("model_responses_usage_unknown")
    for kind in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(kind)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            charge_external(kind, value)


def _encode(value):
    if is_dataclass(value):
        return {"_dataclass": type(value).__name__, "value": asdict(value)}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, tuple):
        return {"_tuple": [_encode(item) for item in value]}
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    return value


def _decode(value):
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        if "_dataclass" in value:
            from .maps import provider

            cls = getattr(provider, value["_dataclass"])
            fields = value["value"]
            for field in ("origin", "destination", "center"):
                if field in fields:
                    fields[field] = tuple(fields[field])
            return cls(**fields)
        if "_tuple" in value:
            return tuple(_decode(item) for item in value["_tuple"])
        return {key: _decode(item) for key, item in value.items()}
    return value


class LedgerMapProvider:
    """全入口计数。启用 task ledger 时，每个成功外部调用成为持久检查点。"""

    OPERATIONS = frozenset(
        {
            "geocode",
            "reverse_geocode",
            "convert_coordinate",
            "search_places",
            "search_facilities",
            "walking_matrix",
            "native_isochrone",
        }
    )

    def __init__(self, provider, checkpoint_ledger=None):
        self.provider, self.checkpoint_ledger = provider, checkpoint_ledger
        self._search_metadata = {}

    def get_facility_search_metadata(self, category, center, radius_m):
        key = (category, tuple(center), radius_m)
        if key in self._search_metadata:
            return self._search_metadata[key]
        getter = getattr(self.provider, "get_facility_search_metadata", None)
        return (
            getter(category, center, radius_m)
            if getter
            else {
                "category": category,
                "scope": "provider_unreported",
                "is_full_inventory": False,
                "truncated": None,
            }
        )

    def __getattr__(self, name):
        attribute = getattr(self.provider, name)
        if name not in self.OPERATIONS or not callable(attribute):
            return attribute

        async def invoke(*args, **kwargs):
            ledger = self.checkpoint_ledger
            key = hashlib.sha256(
                _dump(
                    {
                        "version": VERSIONS["checkpoint"],
                        "provider": self.provider.descriptor.id,
                        "source": self.provider.descriptor.source,
                        "op": name,
                        "args": args,
                        "kwargs": kwargs,
                    }
                ).encode()
            ).hexdigest()
            if ledger:
                checkpoint = ledger.repository.checkpoint(ledger.id, key)
                if checkpoint:
                    if checkpoint["status"] == "completed":
                        ledger.charge("checkpoint_hits")
                        decoded = json.loads(checkpoint["result_json"])
                        if isinstance(decoded, dict) and "_error" in decoded:
                            raise MapProviderError(decoded["_error"], code=decoded["code"])
                        if isinstance(decoded, dict) and "_provider_result" in decoded:
                            if name == "search_facilities" and decoded.get("metadata") is not None:
                                category = args[0] if args else kwargs["category"]
                                center = args[1] if len(args) > 1 else kwargs["center"]
                                radius = kwargs.get("radius_m", args[2] if len(args) > 2 else 1000)
                                self._search_metadata[(category, tuple(center), radius)] = decoded["metadata"]
                            decoded = decoded["_provider_result"]
                        return _decode(decoded)
                    if checkpoint["status"] != "retry_authorized":
                        raise MapProviderError(
                            "检查点的请求计费状态未决，禁止自动重放；请先核对提供方记录", code="checkpoint_uncertain"
                        )
            # 预算拒绝不表示已发送收费请求，因此必须先扣预算再建立未决检查点。
            charge_external("map_adapter_calls")
            record_version("map_provider", f"{self.provider.descriptor.id}:{self.provider.descriptor.source}")
            if ledger:
                ledger.repository.reserve(ledger.id, key, name, 0)
            try:
                result = await attribute(*args, **kwargs)
            except MapProviderError as exc:
                if ledger and exc.code != "checkpoint_uncertain":
                    ledger.repository.complete(ledger.id, key, {"_error": str(exc), "code": exc.code})
                raise
            if ledger:
                metadata = None
                if name == "search_facilities":
                    category = args[0] if args else kwargs["category"]
                    center = args[1] if len(args) > 1 else kwargs["center"]
                    radius = kwargs.get("radius_m", args[2] if len(args) > 2 else 1000)
                    metadata = self.get_facility_search_metadata(category, center, radius)
                ledger.repository.complete(
                    ledger.id,
                    key,
                    {
                        "_provider_result": _encode(result),
                        "metadata": metadata,
                    },
                )
            return result

        return invoke


class LedgerLLMProvider:
    def __init__(self, provider):
        self.provider = provider

    def __getattr__(self, name):
        return getattr(self.provider, name)

    async def generate(self, **kwargs):
        charge_external("model_adapter_calls")
        record_version("model", self.provider.model)
        return await self.provider.generate(**kwargs)

    async def generate_tools(self, **kwargs):
        charge_external("model_adapter_calls")
        record_version("model", self.provider.model)
        return await self.provider.generate_tools(**kwargs)


def execution_router():
    router = APIRouter(tags=["execution-ledger"])

    @router.get("/api/executions/{identifier}")
    def execution(identifier: str, request: Request):
        repository = request.app.state.execution_repository
        if not repository.get(identifier):
            raise HTTPException(404, "执行账本不存在")
        return ExecutionLedger(repository, identifier).summary()

    @router.get("/api/executions/{identifier}/uncertain-checkpoints")
    def uncertain(identifier: str, request: Request):
        return {"items": request.app.state.execution_repository.uncertain(identifier)}

    @router.post("/api/executions/{identifier}/reconcile")
    def reconcile(identifier: str, payload: CheckpointReview, request: Request):
        repository = request.app.state.execution_repository
        if not repository.get(identifier):
            raise HTTPException(404, "执行账本不存在")
        try:
            repository.authorize_retry(identifier, payload.call_key, payload.reviewer, payload.evidence)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {
            "status": "retry_authorized",
            "budget_reset": False,
            "disclosure": "已记录人工计费核对；续算仍扣原预算，可能再次计费。",
        }

    @router.get("/api/executions/{identifier}/settlements")
    def settlements(identifier: str, request: Request):
        repository = request.app.state.execution_repository
        if not repository.get(identifier):
            raise HTTPException(404, "执行账本不存在")
        return {"items": repository.settlements(identifier)}

    @router.post("/api/executions/{identifier}/settlements")
    def settle(identifier: str, payload: SettlementInput, request: Request):
        try:
            return request.app.state.execution_repository.settle(identifier, payload)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    return router


class CheckpointReview(BaseModel):
    call_key: str = Field(min_length=64, max_length=64)
    reviewer: str = Field(min_length=1, max_length=120)
    evidence: str = Field(min_length=1, max_length=2000)


class SettlementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_cny: Decimal = Field(ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)
    bill_reference: str = Field(min_length=1, max_length=500)
    reviewer: str = Field(min_length=1, max_length=120)
    evidence: str = Field(min_length=1, max_length=2000)
    expected_version: int = Field(ge=0, strict=True)
    expected_usage_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope: Literal["execution_total"]

    @field_validator("amount_cny", mode="before")
    @classmethod
    def reject_boolean_amount(cls, value):
        if isinstance(value, bool):
            raise ValueError("结算金额必须是人民币数值")
        return value

    @field_validator("bill_reference", "reviewer", "evidence", mode="before")
    @classmethod
    def trim_required_text(cls, value):
        return value.strip() if isinstance(value, str) else value


def new_request_ledger(repository, entrypoint):
    return repository.ensure(str(uuid4()), entrypoint)
