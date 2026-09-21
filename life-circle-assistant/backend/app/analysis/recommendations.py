from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any


PRIORITY_LABELS = {"high": "高", "medium": "中"}


def build_planning_recommendations(
    category_scores: list[dict[str, Any]],
    service_areas: dict[str, Any],
) -> dict[str, Any]:
    """只消费评分与类别级服务区域，生成可追溯且稳定的规划建议。"""

    scores_by_category = {item["category"]: item for item in category_scores}
    critical_by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for feature in service_areas.get("features", []):
        properties = feature.get("properties", {})
        if properties.get("kind") != "critical":
            continue
        category = properties.get("category")
        if category in scores_by_category:
            critical_by_category[category].append(feature)

    recommendations = [
        _build_category_recommendation(scores_by_category[category], features)
        for category, features in critical_by_category.items()
        if features
    ]
    recommendations.sort(key=lambda item: (item["priority_rank"], item["category"]))

    if recommendations:
        category_labels = "、".join(item["category_label"] for item in recommendations)
        summary = {
            "status": "needs_action",
            "message": f"发现 {len(recommendations)} 类服务短板，建议优先改善{category_labels}。",
            "recommendation_count": len(recommendations),
            "target_region_count": sum(len(item["target_region_ids"]) for item in recommendations),
        }
    elif any(score.get("valid_for_overall") is False for score in category_scores):
        summary = {
            "status": "calculation_incomplete",
            "message": "部分所选类别缺少可核验的服务区域证据，暂不据此生成补充设施建议。",
            "recommendation_count": 0,
            "target_region_count": 0,
        }
    else:
        summary = {
            "status": "no_shortage",
            "message": "所选类别未发现重点服务盲区，当前无需生成补充设施建议。",
            "recommendation_count": 0,
            "target_region_count": 0,
        }
    return {"summary": summary, "recommendations": recommendations}


def _build_category_recommendation(
    score: dict[str, Any],
    features: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered_features = sorted(features, key=lambda item: item["properties"]["grid_id"])
    region_ids = [item["properties"]["grid_id"] for item in ordered_features]
    clusters = _connected_clusters(ordered_features)
    candidates = [
        _candidate_for_cluster(score, cluster, index)
        for index, cluster in enumerate(clusters, start=1)
    ]
    area_sqm = round(sum(_polygon_area_sqm(item["geometry"]["coordinates"][0]) for item in ordered_features))
    nearest = _nearest_facility_evidence(ordered_features)
    priority_level = _priority_level(score, ordered_features)
    example_basis = ordered_features[0]["properties"]["basis"]
    score_text = "暂无有效类别分" if score.get("score") is None else f"类别评分为 {score['score']} 分"
    nearest_text = (
        f"最近可核验同类设施为“{nearest['name']}”，步行约 {nearest['walk_minutes']} 分钟、"
        f"{nearest['walk_distance_m']} 米。"
        if nearest["status"] == "available"
        else "候选预筛选范围内没有可核验的同类设施。"
    )
    target_description = (
        f"以 {len(region_ids)} 个重点服务盲区为目标，预计改善约 {area_sqm:,} 平方米分析网格；"
        "实际改善效果需在规划模拟中复算。"
    )
    return {
        "id": f"recommendation-{score['category']}-critical",
        "category": score["category"],
        "category_label": score["label"],
        "priority": PRIORITY_LABELS[priority_level],
        "priority_level": priority_level,
        "priority_rank": 1 if priority_level == "high" else 2,
        "title": f"补充{score['label']}服务点",
        "body": f"{score_text}，共识别 {len(region_ids)} 个重点服务盲区。{nearest_text}",
        "problem_basis": (
            f"{score.get('status_explanation', '')} 区域判定示例：{example_basis}"
        ).strip(),
        "nearest_facility": nearest,
        "target_region_ids": region_ids,
        "target_improvement": {
            "region_count": len(region_ids),
            "estimated_area_sqm": area_sqm,
            "estimated_critical_regions_reduced": len(region_ids),
            "description": target_description,
            "method": "critical_service_area_grid_sum",
        },
        "candidate_locations": candidates,
    }


def _priority_level(score: dict[str, Any], features: list[dict[str, Any]]) -> str:
    has_no_candidate = any(item["properties"].get("candidate_facility_count") == 0 for item in features)
    numeric_score = score.get("score")
    if score.get("count") == 0 or has_no_candidate or len(features) >= 4 or (numeric_score is not None and numeric_score < 40):
        return "high"
    return "medium"


def _nearest_facility_evidence(features: list[dict[str, Any]]) -> dict[str, Any]:
    available = [
        feature["properties"]
        for feature in features
        if feature["properties"].get("nearest_facility_id")
        and feature["properties"].get("nearest_walk_minutes") is not None
    ]
    if not available:
        return {
            "status": "not_found",
            "id": None,
            "name": None,
            "walk_minutes": None,
            "walk_distance_m": None,
            "source_region_id": None,
            "message": "目标盲区没有可核验的最近同类设施。",
        }
    nearest = min(available, key=lambda item: (item["nearest_walk_minutes"], item.get("nearest_walk_distance_m") or math.inf))
    return {
        "status": "available",
        "id": nearest["nearest_facility_id"],
        "name": nearest["nearest_facility_name"],
        "walk_minutes": nearest["nearest_walk_minutes"],
        "walk_distance_m": nearest["nearest_walk_distance_m"],
        "source_region_id": nearest["grid_id"],
        "message": nearest["basis"],
    }


def _connected_clusters(features: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    remaining = {item["properties"]["grid_id"]: item for item in features}
    clusters: list[list[dict[str, Any]]] = []
    while remaining:
        first_id = min(remaining)
        queue = [remaining.pop(first_id)]
        cluster: list[dict[str, Any]] = []
        while queue:
            current = queue.pop()
            cluster.append(current)
            current_position = _grid_position(current["properties"]["grid_id"])
            if current_position is None:
                continue
            adjacent_ids = [
                grid_id
                for grid_id in remaining
                if _is_adjacent(current_position, _grid_position(grid_id))
            ]
            queue.extend(remaining.pop(grid_id) for grid_id in adjacent_ids)
        clusters.append(sorted(cluster, key=lambda item: item["properties"]["grid_id"]))
    return clusters


def _grid_position(grid_id: str) -> tuple[int, int] | None:
    match = re.search(r"-r(\d+)c(\d+)$", grid_id)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _is_adjacent(first: tuple[int, int], second: tuple[int, int] | None) -> bool:
    return second is not None and abs(first[0] - second[0]) + abs(first[1] - second[1]) == 1


def _candidate_for_cluster(
    score: dict[str, Any],
    cluster: list[dict[str, Any]],
    index: int,
) -> dict[str, Any]:
    centroids = [(_polygon_centroid(item["geometry"]["coordinates"][0]), item) for item in cluster]
    point, representative = min(
        centroids,
        key=lambda entry: sum(_squared_distance(entry[0], other[0]) for other in centroids),
    )
    related_region_ids = [item["properties"]["grid_id"] for item in cluster]
    representative_id = representative["properties"]["grid_id"]
    return {
        "id": f"candidate-{score['category']}-{index}",
        "category": score["category"],
        "coordinate_system": "BD-09",
        "lng": round(point[0], 7),
        "lat": round(point[1], 7),
        "region_id": representative_id,
        "related_region_ids": related_region_ids,
        "reason": (
            f"候选点位于重点服务盲区 {representative_id} 内，并代表相邻的 "
            f"{len(related_region_ids)} 个同类盲区，便于后续模拟集中改善效果。"
        ),
        "selection_method": "critical_cluster_medoid_cell_centroid",
    }


def _polygon_centroid(coordinates: list[list[float]]) -> tuple[float, float]:
    points = coordinates[:-1] if coordinates and coordinates[0] == coordinates[-1] else coordinates
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def _polygon_area_sqm(coordinates: list[list[float]]) -> float:
    points = coordinates[:-1] if coordinates and coordinates[0] == coordinates[-1] else coordinates
    if len(points) < 3:
        return 0
    latitude = sum(point[1] for point in points) / len(points)
    projected = [
        (lng * 111_320 * math.cos(math.radians(latitude)), lat * 111_320)
        for lng, lat in points
    ]
    return abs(
        sum(
            projected[index][0] * projected[(index + 1) % len(projected)][1]
            - projected[(index + 1) % len(projected)][0] * projected[index][1]
            for index in range(len(projected))
        )
    ) / 2


def _squared_distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return (first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2
