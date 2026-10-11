from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any

from ..baidu import haversine_meters

RULES_VERSION = "1.0"
HIGH_MATCH_DISTANCE_M = 50
REVIEW_MATCH_DISTANCE_M = 100
MATCH_SCORE_THRESHOLD = 0.65
HIGH_MATCH_SCORE = 0.85


@dataclass(frozen=True)
class FacilityReconciliationResult:
    facilities: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    summary: dict[str, Any]


def reconcile_facilities(
    records: list[dict[str, Any]],
    *,
    as_of: str | None = None,
) -> FacilityReconciliationResult:
    """对不同来源的设施候选做保守实体对齐。

    该 interface 只返回规范化设施、决策轨迹和计数摘要；调用方不需要了解
    名称相似度、地址相似度、距离阈值或时效性选择规则。默认不会被现有分析
    主流程调用，直到独立来源验证通过。
    """
    normalized = [_prepare(record, index, as_of) for index, record in enumerate(records)]
    decisions: list[dict[str, Any]] = []
    clusters: list[list[dict[str, Any]]] = []

    for record in normalized:
        matched_clusters: dict[int, tuple[float, dict[str, Any]]] = {}
        for cluster_index, cluster in enumerate(clusters):
            if any(item["source"] == record["source"] for item in cluster):
                continue
            for existing in cluster:
                candidate = _candidate_decision(existing, record)
                if candidate["decision"] in {"category_conflict", "coordinate_system_conflict", "needs_review"}:
                    if candidate["decision"] != "needs_review" or candidate["match_score"] >= MATCH_SCORE_THRESHOLD:
                        decisions.append(candidate)
                    continue
                score = float(candidate.get("match_score") or 0)
                if candidate["decision"] == "matched":
                    previous = matched_clusters.get(cluster_index)
                    if previous is None or score > previous[0]:
                        matched_clusters[cluster_index] = (score, candidate)
        if len(matched_clusters) == 1:
            cluster_index, (_, decision) = next(iter(matched_clusters.items()))
            clusters[cluster_index].append(record)
            decisions.append(decision)
        elif len(matched_clusters) > 1:
            decisions.append(
                {
                    "left": _source_record_id(record),
                    "decision": "multiple_cluster_candidates",
                    "candidate_group_count": len(matched_clusters),
                    "match_confidence": "none",
                }
            )
            clusters.append([record])
        else:
            clusters.append([record])

    facilities: list[dict[str, Any]] = []
    field_conflict_count = 0
    for cluster in clusters:
        if len(cluster) > 1:
            facility = _merge_cluster(cluster)
            field_conflict_count += len(facility["reconciliation"]["conflicts"])
            facilities.append(facility)
        else:
            record = cluster[0]
            facilities.append(
                {
                    **_public_record(record),
                    "reconciliation": {
                        "rules_version": RULES_VERSION,
                        "status": "unmatched",
                        "match_confidence": "none",
                        "source_record_ids": [_source_record_id(record)],
                        "selected_source": record["source"],
                        "freshness_status": record["freshness_status"],
                        "conflicts": [],
                    },
                }
            )

    conflict_count = (
        sum(
            item["decision"] in {"category_conflict", "coordinate_system_conflict", "multiple_cluster_candidates"}
            for item in decisions
        )
        + field_conflict_count
    )
    summary = {
        "rules_version": RULES_VERSION,
        "input_count": len(records),
        "output_count": len(facilities),
        "merged_count": len(records) - len(facilities),
        "matched_group_count": sum(len(cluster) > 1 for cluster in clusters),
        "unmatched_count": sum(item["reconciliation"]["status"] == "unmatched" for item in facilities),
        "review_count": sum(item["decision"] == "needs_review" for item in decisions),
        "conflict_count": conflict_count,
        "source_count": len({record["source"] for record in normalized}),
        "as_of": as_of,
    }
    return FacilityReconciliationResult(facilities=facilities, decisions=decisions, summary=summary)


def _prepare(record: dict[str, Any], index: int, as_of: str | None) -> dict[str, Any]:
    source = str(record.get("source") or "unknown").strip() or "unknown"
    prepared = {
        **record,
        "index": index,
        "source": source,
        "source_record_id": str(record.get("source_record_id") or record.get("id") or f"record-{index}"),
        "name": _display_name(record.get("name") or record.get("category") or "未命名设施"),
        "category": str(record.get("category") or "unknown"),
        "address": _display_name(record.get("address") or ""),
        "lng": float(record["lng"]),
        "lat": float(record["lat"]),
        "retrieved_at": str(record.get("retrieved_at") or ""),
        "source_updated_at": str(record.get("source_updated_at") or ""),
        "source_priority": int(record.get("source_priority") or 0),
    }
    observed_at = _timestamp(prepared["source_updated_at"])
    reference_time = _timestamp(as_of) if as_of else _timestamp(prepared["retrieved_at"])
    if not prepared["source_updated_at"] or observed_at == _minimum_timestamp():
        freshness_status = "unknown"
    else:
        freshness_status = "fresh" if (reference_time - observed_at).days <= 30 else "stale"
    prepared["freshness_status"] = freshness_status
    return prepared


def _candidate_decision(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    base = {
        "left": _source_record_id(left),
        "right": _source_record_id(right),
    }
    compatible_coordinates = bool(left.get("coordinate_system")) and (
        left.get("coordinate_system") == right.get("coordinate_system")
    )
    if not compatible_coordinates:
        return decide_candidate_features(
            distance_m=None,
            name_score=_name_score(left["name"], right["name"]),
            address_score=_text_score(left["address"], right["address"]),
            category_match=left["category"] == right["category"],
            coordinate_system_compatible=False,
            **base,
        )
    distance = haversine_meters((left["lng"], left["lat"]), (right["lng"], right["lat"]))
    return decide_candidate_features(
        distance_m=distance,
        name_score=_name_score(left["name"], right["name"]),
        address_score=_text_score(left["address"], right["address"]),
        category_match=left["category"] == right["category"],
        coordinate_system_compatible=True,
        **base,
    )


def decide_candidate_features(
    *,
    distance_m: float | None,
    name_score: float,
    address_score: float,
    category_match: bool,
    coordinate_system_compatible: bool = True,
    **trace: Any,
) -> dict[str, Any]:
    """Apply the documented candidate decision rule to minimal audit features.

    This lets a legally approved validation fixture retain feature scores and
    human labels without storing raw provider POI names, addresses or IDs.
    """
    base = {
        **trace,
        "distance_m": round(distance_m, 2) if distance_m is not None else None,
        "name_score": round(name_score, 4),
        "address_score": round(address_score, 4),
        "category_match": category_match,
    }
    if not coordinate_system_compatible:
        return {**base, "decision": "coordinate_system_conflict", "match_confidence": "none"}
    if not category_match:
        return {**base, "decision": "category_conflict", "match_confidence": "none"}
    if distance_m is None:
        return {**base, "decision": "unmatched", "match_confidence": "none"}
    if distance_m < 0 or not 0 <= name_score <= 1 or not 0 <= address_score <= 1:
        raise ValueError("distance_m 必须非负，name_score/address_score 必须位于 0 到 1 之间")
    name_score = float(name_score)
    address_score = float(address_score)
    distance_score = max(0.0, 1 - distance_m / REVIEW_MATCH_DISTANCE_M)
    score = 0.35 * name_score + 0.30 * address_score + 0.25 * distance_score + 0.10
    if distance_m > REVIEW_MATCH_DISTANCE_M:
        decision = "unmatched"
    elif distance_m > HIGH_MATCH_DISTANCE_M:
        decision = "needs_review" if score >= MATCH_SCORE_THRESHOLD else "unmatched"
    elif score >= HIGH_MATCH_SCORE or address_score >= 0.8:
        decision = "matched"
    elif score >= MATCH_SCORE_THRESHOLD:
        decision = "needs_review"
    else:
        decision = "unmatched"
    return {
        **base,
        "decision": decision,
        "match_score": round(score, 4),
        "match_confidence": "high" if decision == "matched" else "medium" if decision == "needs_review" else "none",
    }


def _merge_cluster(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    representative = max(
        cluster,
        key=lambda item: (_timestamp(item["retrieved_at"]), item["source_priority"], bool(item["address"])),
    )
    source_ids = sorted(_source_record_id(item) for item in cluster)
    aliases = sorted({item["name"] for item in cluster})
    address_values = sorted({item["address"] for item in cluster if item["address"]})
    coordinates = [(item["lng"], item["lat"]) for item in cluster]
    coordinate_spread = max(
        (haversine_meters(left, right) for index, left in enumerate(coordinates) for right in coordinates[index + 1 :]),
        default=0.0,
    )
    conflicts = []
    if (
        len(address_values) > 1
        and min(
            _text_score(left, right)
            for index, left in enumerate(address_values)
            for right in address_values[index + 1 :]
        )
        < 0.5
    ):
        conflicts.append("address")
    if coordinate_spread > 25:
        conflicts.append("coordinates")
    return {
        **_public_record(representative),
        "aliases": aliases,
        "reconciliation": {
            "rules_version": RULES_VERSION,
            "status": "matched",
            "match_confidence": "high",
            "source_record_ids": source_ids,
            "selected_source": representative["source"],
            "source_count": len(cluster),
            "freshness_status": representative["freshness_status"],
            "conflicts": conflicts,
            "coordinate_spread_m": round(coordinate_spread, 2),
            "address_values": address_values,
        },
    }


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "index"}


def _source_record_id(record: dict[str, Any]) -> str:
    return f"{record['source']}:{record['source_record_id']}"


def _display_name(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).strip()
    return re.sub(r"\s+", " ", normalized)


def _comparison_name(value: str) -> str:
    return re.sub(r"[\s\-_—·・,，.。/\\（）()\[\]]", "", unicodedata.normalize("NFKC", value)).casefold()


def _name_score(left: str, right: str) -> float:
    left_key = _comparison_name(left)
    right_key = _comparison_name(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    return SequenceMatcher(None, left_key, right_key).ratio()


def _text_score(left: str, right: str) -> float:
    left_key = _comparison_name(left)
    right_key = _comparison_name(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    return SequenceMatcher(None, left_key, right_key).ratio()


def _timestamp(value: str) -> datetime:
    if not value:
        return _minimum_timestamp()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except ValueError:
        return _minimum_timestamp()


def _minimum_timestamp() -> datetime:
    return datetime.min.replace(tzinfo=UTC)
