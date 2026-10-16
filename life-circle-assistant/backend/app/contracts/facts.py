"""Report-scoped fact references. Models select slots; the server supplies values.

An existing entity ID is not proof for arbitrary prose. A claim contains only a
report scope, entity and slot, and must resolve against a server-built catalog.
Never populate a catalog with model-authored text or client-provided evidence.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

EvidenceType = Literal[
    "report", "category_score", "service_area", "simulation", "facility", "data_quality_event", "comparison"
]
FACT_CONTRACT_VERSION = "report-facts-v1"


class FactClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    report_id: str = Field(min_length=1, max_length=200)
    type: EvidenceType
    id: str = Field(min_length=1, max_length=200)
    slot: str = Field(min_length=1, max_length=100)


class FactValidationError(ValueError):
    """A claim cannot be grounded in the current server-owned snapshot."""


@dataclass(frozen=True)
class _Fact:
    claim: FactClaim
    value: Any
    text: str
    evidence: dict[str, str]
    source: str
    calculation_method: str | None = None


class FactCatalog:
    def __init__(self, report_id: str) -> None:
        if not isinstance(report_id, str) or not report_id:
            raise FactValidationError("事实契约必须绑定当前报告")
        self.report_id = report_id
        self._facts: dict[tuple[str, str, str], _Fact] = {}

    def add(
        self,
        *,
        ref: dict[str, str],
        slot: str,
        value: Any,
        text: str,
        source: str = "report_snapshot",
        calculation_method: str | None = None,
    ) -> None:
        """Register one trusted application result, never a model output."""
        claim = FactClaim(report_id=self.report_id, type=ref["type"], id=ref["id"], slot=slot)
        if claim.type == "report" and claim.id != self.report_id:
            raise FactValidationError("报告证据不属于当前报告")
        self._facts[(claim.type, claim.id, claim.slot)] = _Fact(
            claim, deepcopy(value), text, deepcopy(ref), source, calculation_method
        )

    def allowed_claims(self) -> list[dict[str, Any]]:
        return [self._render(fact) for fact in self._facts.values()]

    def validate_claims(self, claims: Any, *, max_claims: int = 20) -> list[dict[str, Any]]:
        if not isinstance(claims, list) or len(claims) > max_claims:
            raise FactValidationError("事实引用必须为有界列表")
        validated: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for raw in claims:
            try:
                claim = FactClaim.model_validate(raw)
            except ValidationError as exc:
                raise FactValidationError("事实引用含有未知字段或无效类型") from exc
            key = (claim.type, claim.id, claim.slot)
            if claim.report_id != self.report_id or key not in self._facts:
                raise FactValidationError("事实引用的报告、实体或槽位不匹配")
            if key not in seen:
                validated.append(self._render(self._facts[key]))
                seen.add(key)
        return validated

    @staticmethod
    def _render(fact: _Fact) -> dict[str, Any]:
        return {
            **fact.claim.model_dump(),
            "value": deepcopy(fact.value),
            "text": fact.text,
            "status": "unknown" if fact.value is None else "available",
            "source": fact.source,
            "calculation_method": fact.calculation_method,
            "evidence_refs": [deepcopy(fact.evidence)],
        }


def claim_reference(claim: dict[str, Any]) -> dict[str, str]:
    """Strip a rendered fact to the only fields a model may request."""
    return {key: claim[key] for key in ("report_id", "type", "id", "slot")}


def build_evidence_catalog(report_id: str, refs: list[dict[str, str]]) -> FactCatalog:
    """Adapt trusted tool evidence to the same claim contract as report facts."""
    catalog = FactCatalog(report_id)
    for ref in refs:
        catalog.add(
            ref=ref,
            slot="detail",
            value=ref.get("detail") or None,
            text=str(ref.get("detail") or "该项证据暂不可用。"),
            source="server_tool_result",
        )
    return catalog


def build_fact_catalog(report: dict[str, Any]) -> FactCatalog:
    report_id = str(report.get("report_id") or report.get("id") or "")
    catalog = FactCatalog(report_id)
    source = str(report.get("source") or "report_snapshot")

    def add(
        kind: str, identifier: str, slot: str, label: str, value: Any, unit: str = "", method: str | None = None
    ) -> None:
        formatted = "暂不可用" if value is None else f"{value}{unit}"
        text = f"{label}：{formatted}。"
        catalog.add(
            ref={"type": kind, "id": identifier, "label": label, "detail": text},
            slot=slot,
            value=value,
            text=text,
            source=source,
            calculation_method=method,
        )

    for slot, label, unit in (
        ("score", "综合指数", ""),
        ("critical_zone_count", "重点服务盲区网格数", "个"),
        ("sparse_zone_count", "设施稀疏网格数", "个"),
    ):
        add("report", report_id, slot, label, (report.get("summary") or {}).get(slot), unit)
    for item in report.get("category_scores") or []:
        identifier, label = str(item["category"]), str(item.get("label") or item["category"])
        for slot, suffix, unit in (
            ("score", "评分", ""),
            ("count", "报告设施数", "处"),
            ("nearest_walk_minutes", "最近设施步行时间", "分钟"),
        ):
            if slot in item:
                add("category_score", identifier, slot, label + suffix, item[slot], unit)
    for item in (report.get("service_areas") or report.get("zones") or {}).get("features", []):
        props = item.get("properties") or {}
        if props.get("grid_id"):
            add("service_area", str(props["grid_id"]), "basis", "网格判定依据", props.get("basis"))
            for slot, suffix, unit in (
                ("walk_minutes", "最近同类设施步行时间", "分钟"),
                ("nearby_facility_count", "附近同类设施数", "处"),
            ):
                if slot in props:
                    add("service_area", str(props["grid_id"]), slot, suffix, props[slot], unit)
    for item in report.get("facilities") or report.get("pois") or []:
        if not item.get("id"):
            continue
        add("facility", str(item["id"]), "name", "报告设施名称", item.get("name"))
        add(
            "facility",
            str(item["id"]),
            "walk_minutes",
            "从分析中心步行时间",
            item.get("walk_minutes"),
            "分钟",
            item.get("calculation_method"),
        )
    for item in report.get("simulations") or []:
        if not item.get("id") or item.get("report_id", report_id) != report_id:
            continue
        for slot, value in (item.get("delta") or {}).items():
            add("simulation", str(item["id"]), "delta." + slot, "假设模拟变化 " + slot, value)
    return catalog
