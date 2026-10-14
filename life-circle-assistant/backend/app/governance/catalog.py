from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import fields

from ..maps.provider import FacilityResult
from ..maps.support import require_supported_huangpu_area
from ..mock_data import CATEGORIES


def _active(catalog: dict, record_id: str) -> dict | None:
    return next(
        (item for item in catalog["records"] if record_id == item["id"] or record_id in item.get("member_ids", [])),
        None,
    )


def apply_semantic_decision(catalog: dict, review: dict, payload: dict):
    kind, decision = payload["kind"], payload["decision"]
    if kind == "category":
        proposal = next((p for p in review["category_proposals"] if p["record_id"] == payload.get("record_id")), None)
    else:
        pair = {payload.get("left_id"), payload.get("right_id")}
        proposal = next((p for p in review["entity_proposals"] if {p["left_id"], p["right_id"]} == pair), None)
    if proposal is None:
        raise ValueError("审核对象不属于已保存的建议")
    if proposal["status"] != "pending_human_review":
        raise ValueError("该建议已经审核")
    if decision != "reject":
        if kind == "category":
            category = payload.get("category") if decision == "correct" else proposal.get("proposed_category")
            if category is None and len(proposal.get("candidate_categories", [])) == 1:
                category = proposal["candidate_categories"][0]
            if category not in CATEGORIES:
                raise ValueError("候选类别不明确，请提供人工修正类别")
            active = _active(catalog, proposal["record_id"])
            if active is None:
                if proposal["record_id"] in catalog.get("excluded_source_ids", []):
                    raise ValueError("该来源已核验关闭，旧分类建议不能重新纳入正式目录")
                if any(proposal["record_id"] in item.get("related_source_ids", []) for item in catalog["records"]):
                    raise ValueError("已审核入口或科室不能重新计为独立服务设施")
                source = next((r for r in catalog["source_records"] if r["id"] == proposal["record_id"]), None)
                if source is None or source.get("coordinate_system") != "BD09":
                    raise ValueError("辅助设施需先核验坐标系后才能纳入正式目录")
                require_supported_huangpu_area(source["lng"], source["lat"])
                active = deepcopy(source)
                active["member_ids"] = [active["id"]]
                catalog["records"].append(active)
            active["category"] = category
            active["category_review"] = {"review_id": review["review_id"], "reviewer": payload["reviewer"]}
            proposal["reviewed_category"] = category
        else:
            relation = payload.get("relation") if decision == "correct" else proposal["relation"]
            if relation not in {"same_entity", "different_entity", "department", "entrance"}:
                raise ValueError("实体关系尚未确定，请提供人工修正关系")
            left, right = _active(catalog, proposal["left_id"]), _active(catalog, proposal["right_id"])
            if left is None or right is None:
                raise ValueError("实体审核对象未纳入正式目录，请先核验类别与坐标")
            if relation == "same_entity":
                blocking_flags = [flag for flag in proposal["flags"] if flag != "category_conflict"]
                if blocking_flags or left["category"] != right["category"]:
                    raise ValueError("存在分店、入口、科室或类别冲突，不能合并为同一服务设施")
                if left is not right:
                    left["member_ids"] = list(dict.fromkeys(left["member_ids"] + right["member_ids"]))
                    left["reviewed_aliases"] = list(dict.fromkeys(left.get("reviewed_aliases", []) + [right["name"]]))
                    catalog["records"].remove(right)
            elif relation == "different_entity" and left is right:
                separate_id = proposal["left_id"] if left["id"] == proposal["right_id"] else proposal["right_id"]
                source = next((r for r in catalog["source_records"] if r["id"] == separate_id), None)
                if source is None:
                    raise ValueError("原始记录缺失，无法恢复独立设施")
                left["member_ids"].remove(separate_id)
                separated = deepcopy(source)
                separated["category"] = left["category"]
                separated["member_ids"] = [separate_id]
                catalog["records"].append(separated)
            elif relation in {"department", "entrance"} and left is not right:
                pattern = (
                    r"入口|出口|东门|西门|南门|北门|正门|侧门"
                    if relation == "entrance"
                    else r"科室|急诊科|口腔科|内科|外科|儿科|住院部|接种门诊"
                )
                subordinate_matches = [item for item in (left, right) if re.search(pattern, item["name"])]
                if len(subordinate_matches) != 1:
                    raise ValueError("从属关系需要明确识别入口或科室记录，不能任意减少设施数量")
                subordinate = subordinate_matches[0]
                parent = right if subordinate is left else left
                catalog["records"].remove(subordinate)
                parent["related_source_ids"] = list(
                    dict.fromkeys(parent.get("related_source_ids", []) + subordinate["member_ids"])
                )
            catalog["relationships"].append(
                {
                    "left_id": proposal["left_id"],
                    "right_id": proposal["right_id"],
                    "relation": relation,
                    "reviewer": payload["reviewer"],
                }
            )
            proposal["reviewed_relation"] = relation
    proposal.update(
        status={"accept": "accepted", "reject": "rejected", "correct": "corrected"}[decision],
        reviewer=payload["reviewer"],
        reason=payload["reason"],
    )


def infer_observation_kind(text: str) -> str:
    if any(word in text for word in ("围挡", "围栏", "封路", "阻断")):
        return "barrier"
    if any(word in text for word in ("关闭", "停业", "关门")):
        return "closure"
    if any(word in text for word in ("入口", "大门", "门口")):
        return "entrance_change"
    if any(word in text for word in ("新开", "新增", "漏了", "漏掉")):
        return "facility_missing"
    return "other"


def apply_observation_decision(catalog: dict, observation: dict, payload: dict):
    if observation["status"] != "pending_human_review":
        raise ValueError("该观察已经审核")
    if payload["decision"] != "reject":
        kind = payload.get("kind") or observation["kind"]
        facility_id = payload.get("facility_id")
        if kind == "closure":
            active = _active(catalog, facility_id or "")
            if active is None:
                raise ValueError("关闭观察需要核验正式设施标识")
            retired = active.get("member_ids", [active["id"]]) + active.get("related_source_ids", [])
            catalog["excluded_source_ids"] = list(dict.fromkeys(catalog.get("excluded_source_ids", []) + retired))
            catalog["records"].remove(active)
        elif kind == "entrance_change":
            active = _active(catalog, facility_id or "")
            if active is None or payload.get("lng") is None or payload.get("lat") is None:
                raise ValueError("入口变更需要核验设施标识与BD-09入口坐标")
            require_supported_huangpu_area(payload["lng"], payload["lat"])
            active.update(lng=payload["lng"], lat=payload["lat"], entrance_observation_id=observation["id"])
        elif kind == "facility_missing":
            if (
                not payload.get("name", "").strip()
                or payload.get("category") not in CATEGORIES
                or payload.get("lng") is None
                or payload.get("lat") is None
            ):
                raise ValueError("新增设施需要核验名称、类别和BD-09坐标")
            require_supported_huangpu_area(payload["lng"], payload["lat"])
            record = {
                "id": f"reviewed-{observation['id']}",
                "name": payload["name"],
                "category": payload["category"],
                "lng": payload["lng"],
                "lat": payload["lat"],
                "address": observation["text"],
                "source": "human_verified",
                "coordinate_system": "BD09",
                "observation_id": observation["id"],
            }
            record["member_ids"] = [record["id"]]
            catalog["records"].append(record)
            catalog["source_records"].append(deepcopy(record))
        elif kind == "barrier":
            if (
                not payload.get("first_grid_id")
                or not payload.get("second_grid_id")
                or payload["first_grid_id"] == payload["second_grid_id"]
            ):
                raise ValueError("围挡观察需明确被阻断的两个相邻网格标识")
        observation.update(
            kind=kind,
            verified_fields={
                key: value
                for key, value in payload.items()
                if key not in {"expected_version", "reviewer", "reason", "decision"} and value is not None
            },
        )
    observation.update(
        status={"accept": "accepted", "reject": "rejected", "correct": "corrected"}[payload["decision"]],
        reviewer=payload["reviewer"],
        reason=payload["reason"],
    )
    if payload["decision"] != "reject":
        catalog["verified_observations"].append(deepcopy(observation))


class CatalogMapProvider:
    """Reviewed facilities; route/geocode calls still use the real selected provider."""

    def __init__(self, provider, catalog: dict):
        self.provider = provider
        self.catalog = catalog
        self.facility_catalog_version = catalog["version"]
        count = len(catalog["records"])
        self.facility_catalog_summary = {
            "rules_version": "human-reviewed-catalog-v1",
            "input_count": count,
            "output_count": count,
            "merged_count": 0,
            "merged_group_count": 0,
            "same_site_distance_m": 0,
            "by_category": {},
        }

    def __getattr__(self, name):
        return getattr(self.provider, name)

    async def search_facilities(self, category, center, radius_m=3000):
        allowed = {field.name for field in fields(FacilityResult)}
        return [
            FacilityResult(**{key: value for key, value in item.items() if key in allowed})
            for item in self.catalog["records"]
            if item["category"] == category
        ]

    def get_facility_search_metadata(self, category, center, radius_m):
        return {
            "category": category,
            "scope": "reviewed_source_inventory",
            "is_full_inventory": False,
            "truncated": False,
            "catalog_version": self.facility_catalog_version,
            "source_report_id": self.catalog["report_id"],
        }
