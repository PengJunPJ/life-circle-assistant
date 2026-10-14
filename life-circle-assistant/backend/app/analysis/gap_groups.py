"""三种缺口独立归组；已核验障碍阻断邻接，分组不产生新的可达事实。"""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from typing import Any

GAP_KINDS = ("scarcity", "walking_timeout", "critical")


def build_gap_groups(
    service_areas: dict[str, Any],
    *,
    blocked_edges: set[frozenset[str]] | None = None,
    adjacency_evidence: list[dict] | None = None,
    gap_kinds: tuple[str, ...] = GAP_KINDS,
) -> dict[str, Any]:
    if any(kind not in GAP_KINDS for kind in gap_kinds):
        raise ValueError("缺口类型不支持")
    blocked_edges = set(blocked_edges or ())
    verified = [
        item
        for item in adjacency_evidence or []
        if item.get("verified") is True
        and item.get("reviewer")
        and item.get("evidence_ref")
        and item.get("source") in {"field_verification", "official_inventory", "resident_reviewed", "real_api"}
    ]
    blocked_edges.update(
        frozenset((item["first_grid_id"], item["second_grid_id"])) for item in verified if item.get("blocked") is True
    )
    by_kind: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for feature in service_areas.get("features", []):
        props = feature.get("properties", {})
        if feature.get("geometry", {}).get("type") != "Polygon":
            continue
        source = props.get("underlying_source") or props.get("source")
        confirmed_walk = (
            props.get("classification_status") == "valid"
            and props.get("walk_threshold_exceeded") is True
            and props.get("failed_route_count", 0) == 0
            and source in {"real_api", "local_snapshot"}
        )
        confirmed_scarcity = props.get("nearby_scarcity") is True and (
            props.get("nearby_scarcity_status") == "observed_search_results"
            or props.get("classification_status") == "valid"
        )
        flags = {
            "scarcity": confirmed_scarcity,
            "walking_timeout": confirmed_walk,
            "critical": confirmed_scarcity and confirmed_walk,
        }
        for kind in gap_kinds:
            if flags[kind]:
                by_kind[(props["category"], kind)][props["grid_id"]] = feature

    groups: list[dict[str, Any]] = []
    for (category, kind), original in sorted(by_kind.items()):
        remaining = dict(original)
        while remaining:
            queue = [remaining.pop(min(remaining))]
            members: list[dict] = []
            while queue:
                current = queue.pop()
                members.append(current)
                current_id = current["properties"]["grid_id"]
                adjacent = [
                    key
                    for key in remaining
                    if _adjacent(_position(current_id), _position(key)) and not _blocked(current_id, key, blocked_edges)
                ]
                queue.extend(remaining.pop(key) for key in sorted(adjacent))
            members.sort(key=lambda item: item["properties"]["grid_id"])
            props = [item["properties"] for item in members]
            ids = [item["grid_id"] for item in props]
            times = [
                item["nearest_walk_minutes"]
                for item in props
                if isinstance(item.get("nearest_walk_minutes"), (int, float))
            ]
            nearby_counts = [
                item["nearby_facility_count"] for item in props if isinstance(item.get("nearby_facility_count"), int)
            ]
            relevant = [item for item in verified if _edge_relevant(item, ids)]
            groups.append(
                {
                    "type": "Feature",
                    "properties": {
                        "id": f"gap-{kind}-{category}-{ids[0]}",
                        "gap_kind": kind,
                        "category": category,
                        "category_label": props[0].get("category_label", category),
                        "grid_ids": ids,
                        "grid_count": len(ids),
                        "critical_grid_count": sum(item.get("kind") == "critical" for item in props),
                        "coordinate_system": "BD-09",
                        "method": "confirmed_gap_grid_four_neighbors",
                        "contains_unknown": any(item.get("walking_reachable") is None for item in props),
                        "unknown_walking_ratio": sum(item.get("walking_reachable") is None for item in props)
                        / len(props),
                        "worst_walk_minutes": max(times) if times else None,
                        "mean_walk_minutes": sum(times) / len(times) if times else None,
                        "mean_nearby_facility_count": sum(nearby_counts) / len(nearby_counts)
                        if nearby_counts
                        else None,
                        "scarcity_ratio": sum(item.get("nearby_scarcity") is True for item in props) / len(props),
                        "threshold_minutes": props[0].get("threshold_minutes"),
                        "source_modes": sorted(
                            {item.get("underlying_source") or item.get("source", "unknown") for item in props}
                        ),
                        "evidence_refs": [
                            {
                                "grid_id": item["grid_id"],
                                "source": item.get("source"),
                                "underlying_source": item.get("underlying_source"),
                                "calculation_method": item.get("calculation_method"),
                                "basis": item.get("basis"),
                                "failed_route_count": item.get("failed_route_count", 0),
                            }
                            for item in props
                        ],
                        "adjacency_evidence": copy.deepcopy(relevant),
                        "connectivity_status": "geometric_with_verified_barrier_constraints"
                        if relevant
                        else "geometric_only_unverified_walk_connectivity",
                        "boundary_method": "original_cell_polygons",
                        "disclosure": "稀缺、步行超时、双条件盲区分别归组，片区可互相重叠；已核验障碍不跨越。未核验邻接仅表示网格相邻，不保证道路连通。",
                    },
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [copy.deepcopy(item["geometry"]["coordinates"]) for item in members],
                    },
                }
            )
    return {
        "type": "FeatureCollection",
        "features": groups,
        "grouping_version": "three-gap-barrier-v2",
        "gap_kinds": list(gap_kinds),
        "verified_edge_count": len(verified),
    }


def _bare(grid_id: str) -> str:
    match = re.search(r"r\d+c\d+$", grid_id)
    return match[0] if match else grid_id


def _blocked(first, second, edges):
    return frozenset((first, second)) in edges or frozenset((_bare(first), _bare(second))) in edges


def _edge_relevant(edge, ids):
    bare_ids = {_bare(value) for value in ids}
    return _bare(edge["first_grid_id"]) in bare_ids or _bare(edge["second_grid_id"]) in bare_ids


def spatial_statistics(service_areas: dict[str, Any]) -> dict[str, Any]:
    by_category: dict[str, dict[str, int | str]] = {}
    for feature in service_areas.get("features", []):
        props = feature.get("properties", {})
        category = props["category"]
        counts = by_category.setdefault(
            category,
            {
                "category": category,
                "grid_count": 0,
                "nearby_scarcity_count": 0,
                "walking_gap_count": 0,
                "walking_reachable_count": 0,
                "unknown_walking_count": 0,
                "unknown_scarcity_count": 0,
            },
        )
        counts["grid_count"] += 1
        counts["nearby_scarcity_count"] += props.get("nearby_scarcity") is True
        counts["unknown_scarcity_count"] += props.get("nearby_scarcity") is None
        counts["walking_gap_count"] += props.get("walking_reachable") is False
        counts["walking_reachable_count"] += props.get("walking_reachable") is True
        counts["unknown_walking_count"] += props.get("walking_reachable") is None
    return {
        "nearby_radius_m": 1_000,
        "nearby_measure": "straight_line_from_each_grid_center",
        "walking_measure": "provider_route_duration_from_each_grid_center",
        "categories": [by_category[key] for key in sorted(by_category)],
        "disclosure": "设施稀缺与步行超时分别统计；计数为测算网格数，不代表人口或连续面积覆盖率。",
    }


def _position(grid_id: str) -> tuple[int, int] | None:
    match = re.search(r"-r(\d+)c(\d+)$", grid_id)
    return (int(match[1]), int(match[2])) if match else None


def _adjacent(first: tuple[int, int] | None, second: tuple[int, int] | None) -> bool:
    return first is not None and second is not None and abs(first[0] - second[0]) + abs(first[1] - second[1]) == 1
