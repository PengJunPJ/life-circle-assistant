from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any

from ..baidu import haversine_meters

RULES_VERSION = "1.0"
SAME_SITE_DISTANCE_M = 80

SEMANTIC_TYPE_LABELS = {
    "traditional_market": "传统菜市场",
    "farmers_market": "农贸市场",
    "fresh_food_store": "生鲜商店",
    "market_other": "其他市场设施",
    "pharmacy": "药店",
    "primary_school": "小学",
    "community_health_center": "社区卫生服务机构",
    "hospital": "医院",
    "clinic": "诊所",
    "outpatient_department": "门诊机构",
    "medical_other": "其他医疗服务",
    "unknown": "未细分",
}

_MEDICAL_SUBORDINATE_SUFFIX = re.compile(
    r"(?:[（(]?(?:发热门诊|急诊科|急诊|预防接种门诊|预防接种点|体检中心|住院部|"
    r"口腔科|中医科|儿科|妇科|内科|外科)[）)]?|门诊部|门诊)$"
)


@dataclass(frozen=True)
class FacilityNormalizationResult:
    facilities: list[dict[str, Any]]
    summary: dict[str, Any]


@dataclass(frozen=True)
class _Candidate:
    index: int
    facility: dict[str, Any]
    display_name: str
    comparison_name: str
    institution_name: str
    institution_key: str
    semantic_type: str
    is_subordinate: bool


def normalize_facilities(
    facilities: list[dict[str, Any]],
    *,
    same_site_distance_m: int = SAME_SITE_DISTANCE_M,
) -> FacilityNormalizationResult:
    """归一化设施语义并合并可证明为同一机构的同址记录。

    这是该模块唯一的对外 interface。调用方不需要了解名称清洗、语义类型、
    机构主体提取或聚类规则。
    """
    candidates = [_candidate(index, facility) for index, facility in enumerate(facilities)]
    clusters: list[list[_Candidate]] = []
    for candidate in candidates:
        matching_cluster = next(
            (
                cluster
                for cluster in clusters
                if any(_same_institution(candidate, member, same_site_distance_m) for member in cluster)
            ),
            None,
        )
        if matching_cluster is None:
            clusters.append([candidate])
        else:
            matching_cluster.append(candidate)

    normalized = [_merge_cluster(cluster) for cluster in clusters]
    by_category: dict[str, dict[str, Any]] = {}
    categories = list(dict.fromkeys(candidate.facility["category"] for candidate in candidates))
    for category in categories:
        category_inputs = [candidate for candidate in candidates if candidate.facility["category"] == category]
        category_outputs = [facility for facility in normalized if facility["category"] == category]
        by_category[category] = {
            "input_count": len(category_inputs),
            "output_count": len(category_outputs),
            "merged_count": len(category_inputs) - len(category_outputs),
            "semantic_types": dict(Counter(item["semantic_type"] for item in category_outputs)),
        }

    summary = {
        "rules_version": RULES_VERSION,
        "same_site_distance_m": same_site_distance_m,
        "input_count": len(facilities),
        "output_count": len(normalized),
        "merged_count": len(facilities) - len(normalized),
        "merged_group_count": sum(len(cluster) > 1 for cluster in clusters),
        "by_category": by_category,
    }
    return FacilityNormalizationResult(facilities=normalized, summary=summary)


def _candidate(index: int, facility: dict[str, Any]) -> _Candidate:
    display_name = _display_name(str(facility.get("name") or facility.get("category") or "未命名设施"))
    category = str(facility.get("category") or "unknown")
    institution_name = _institution_name(display_name, category)
    return _Candidate(
        index=index,
        facility={**facility, "name": display_name, "category": category},
        display_name=display_name,
        comparison_name=_comparison_name(display_name),
        institution_name=institution_name,
        institution_key=_comparison_name(institution_name),
        semantic_type=_semantic_type(category, display_name),
        is_subordinate=category == "medical" and institution_name != display_name,
    )


def _same_institution(left: _Candidate, right: _Candidate, distance_limit_m: int) -> bool:
    if left.facility["category"] != right.facility["category"]:
        return False
    left_provider_id = left.facility.get("id")
    right_provider_id = right.facility.get("id")
    if (
        left_provider_id is not None
        and right_provider_id is not None
        and str(left_provider_id).strip()
        and str(left_provider_id) == str(right_provider_id)
    ):
        return True
    if _distance(left, right) > distance_limit_m:
        return False
    if left.comparison_name == right.comparison_name:
        return True
    if left.facility["category"] != "medical":
        return False
    if left.institution_key == right.institution_key:
        return True
    shorter, longer = sorted((left.institution_key, right.institution_key), key=len)
    return len(shorter) >= 6 and (longer.startswith(shorter) or longer.endswith(shorter))


def _distance(left: _Candidate, right: _Candidate) -> float:
    return haversine_meters(
        (float(left.facility["lng"]), float(left.facility["lat"])),
        (float(right.facility["lng"]), float(right.facility["lat"])),
    )


def _merge_cluster(cluster: list[_Candidate]) -> dict[str, Any]:
    representative = min(
        cluster,
        key=lambda item: (
            item.is_subordinate,
            not bool(item.facility.get("address")),
            item.index,
        ),
    )
    canonical_name = representative.institution_name
    aliases = list(dict.fromkeys(item.display_name for item in cluster))
    provider_ids = [
        str(item.facility["id"])
        for item in cluster
        if item.facility.get("id") is not None and str(item.facility["id"]).strip()
    ]
    merged_ids = list(dict.fromkeys(provider_ids))
    exact_identity = len({item.comparison_name for item in cluster}) == 1
    duplicate_provider_id = len(merged_ids) < len(provider_ids)
    if len(cluster) == 1:
        method = "name_and_type_normalization"
        confidence = "high"
    elif duplicate_provider_id:
        method = "provider_id_merge"
        confidence = "high"
    elif exact_identity:
        method = "same_name_same_site_merge"
        confidence = "high"
    else:
        method = "same_institution_same_site_merge"
        confidence = "medium"

    semantic_type = _semantic_type(str(representative.facility["category"]), canonical_name)
    return {
        **representative.facility,
        "canonical_name": canonical_name,
        "semantic_type": semantic_type,
        "semantic_type_label": SEMANTIC_TYPE_LABELS[semantic_type],
        "normalization": {
            "rules_version": RULES_VERSION,
            "method": method,
            "confidence": confidence,
            "aliases": aliases,
            "merged_facility_ids": merged_ids,
            "source_record_count": len(cluster),
        },
    }


def _display_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized or "未命名设施"


def _comparison_name(value: str) -> str:
    return re.sub(r"[\s\-_—·・,，.。/\\（()）]", "", unicodedata.normalize("NFKC", value)).casefold()


def _institution_name(name: str, category: str) -> str:
    if category != "medical":
        return name
    root = _MEDICAL_SUBORDINATE_SUFFIX.sub("", name).rstrip(" -—·・（(")
    return root or name


def _semantic_type(category: str, name: str) -> str:
    comparison = _comparison_name(name)
    if category == "market":
        if "农贸市场" in comparison:
            return "farmers_market"
        if "菜市场" in comparison:
            return "traditional_market"
        if any(token in comparison for token in ("生鲜超市", "生鲜店", "生鲜商店")):
            return "fresh_food_store"
        return "market_other"
    if category == "pharmacy":
        return "pharmacy"
    if category == "school":
        return "primary_school"
    if category == "medical":
        if any(token in comparison for token in ("社区卫生服务中心", "社区卫生服务站")):
            return "community_health_center"
        if "医院" in comparison:
            return "hospital"
        if "诊所" in comparison:
            return "clinic"
        if "门诊" in comparison:
            return "outpatient_department"
        return "medical_other"
    return "unknown"
