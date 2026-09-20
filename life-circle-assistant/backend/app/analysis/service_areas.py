from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from ..baidu import haversine_meters
from ..maps.provider import MapProvider, MapProviderError, WalkingResult
from ..mock_data import CATEGORIES


AreaKind = Literal["normal", "sparse", "critical"]

GRID_SIZE = 4
GRID_SPAN_M = 1_000
NEARBY_RADIUS_M = 1_000
CANDIDATE_PREFILTER_RADIUS_M = 3_000


@dataclass(frozen=True)
class CellEvidence:
    nearby_facility_count: int
    candidate_facility_count: int
    nearest_facility: dict[str, Any] | None
    nearest_route: WalkingResult | None
    failed_route_count: int = 0
    facility_discovery_succeeded: bool = True


@dataclass(frozen=True)
class CellClassification:
    kind: AreaKind
    confidence: Literal["high", "medium", "low"]
    basis: str


def classify_service_area_cell(evidence: CellEvidence, threshold_minutes: int) -> CellClassification:
    """仅根据已准备好的设施与步行证据分类，不调用地图服务。"""
    route = evidence.nearest_route
    lacks_nearby_facility = evidence.nearby_facility_count == 0

    if not evidence.facility_discovery_succeeded:
        return CellClassification(
            kind="sparse",
            confidence="low",
            basis="同类设施检索失败，缺少可靠输入；为避免误报重点盲区，暂归为设施稀疏区。",
        )

    if evidence.candidate_facility_count == 0:
        return CellClassification(
            kind="critical",
            confidence="high",
            basis=f"候选预筛选范围内无同类设施，且周边{NEARBY_RADIUS_M}米内无同类设施。",
        )

    if route is None:
        return CellClassification(
            kind="sparse",
            confidence="low",
            basis="存在同类候选设施，但步行结果全部失败；为避免误报重点盲区，暂归为设施稀疏区。",
        )

    walk_minutes = (route.duration_s or 0) / 60
    exceeds_threshold = walk_minutes > threshold_minutes
    confidence: Literal["high", "medium", "low"] = "medium" if evidence.failed_route_count else "high"

    if exceeds_threshold and lacks_nearby_facility:
        return CellClassification(
            kind="critical",
            confidence=confidence,
            basis=(
                f"最近同类设施步行{walk_minutes:.1f}分钟，超过{threshold_minutes}分钟阈值，"
                f"且周边{NEARBY_RADIUS_M}米内无同类设施。"
            ),
        )
    if not exceeds_threshold and not lacks_nearby_facility:
        return CellClassification(
            kind="normal",
            confidence=confidence,
            basis=(
                f"最近同类设施步行{walk_minutes:.1f}分钟，不超过{threshold_minutes}分钟阈值，"
                f"且周边{NEARBY_RADIUS_M}米内有{evidence.nearby_facility_count}处同类设施。"
            ),
        )
    if exceeds_threshold:
        basis = (
            f"周边{NEARBY_RADIUS_M}米内有同类设施，但最近步行时间{walk_minutes:.1f}分钟"
            f"超过{threshold_minutes}分钟阈值；未同时满足重点盲区条件。"
        )
    else:
        basis = (
            f"周边{NEARBY_RADIUS_M}米内无同类设施，但最近同类设施步行{walk_minutes:.1f}分钟"
            f"仍在{threshold_minutes}分钟阈值内。"
        )
    return CellClassification(kind="sparse", confidence=confidence, basis=basis)


async def build_category_service_areas(
    provider: MapProvider,
    center: tuple[float, float],
    categories: list[str],
    facilities: list[dict[str, Any]],
    threshold_minutes: int,
    *,
    grid_size: int = GRID_SIZE,
    grid_span_m: int = GRID_SPAN_M,
    failed_categories: set[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """用外部步行矩阵准备证据，再交给纯分类器生成完整 BD-09 GeoJSON。"""
    cells = _build_grid(center, grid_size, grid_span_m)
    features: list[dict[str, Any]] = []
    quality_events: list[dict[str, Any]] = []
    partial_failures: list[dict[str, Any]] = []
    failed_categories = failed_categories or set()

    for category in categories:
        category_facilities = [item for item in facilities if item["category"] == category]
        candidates_by_cell = [
            [
                facility
                for facility in category_facilities
                if haversine_meters(cell["center"], (facility["lng"], facility["lat"]))
                <= CANDIDATE_PREFILTER_RADIUS_M
            ]
            for cell in cells
        ]
        routes_by_cell = await _walking_results_by_cell(provider, cells, candidates_by_cell)
        category_failed_count = sum(
            1
            for row_index, candidates in enumerate(candidates_by_cell)
            for facility in candidates
            if (
                routes_by_cell[row_index].get(facility["id"]) is None
                or not routes_by_cell[row_index][facility["id"]].success
            )
        )
        if category_failed_count:
            partial_failures.append(
                {
                    "scope": "category",
                    "category": category,
                    "code": "walking_category_incomplete",
                    "failed_count": category_failed_count,
                    "message": f"{CATEGORIES[category]['label']}共有 {category_failed_count} 个网格步行坐标对失败，该类别排除综合评分。",
                }
            )
            quality_events.append(
                {
                    "code": "walking_category_incomplete",
                    "severity": "warning",
                    "scope": "category",
                    "category": category,
                    "object_ref": None,
                    "source": provider.descriptor.source,
                    "method": "provider_walking_matrix",
                    "message": partial_failures[-1]["message"],
                }
            )
        for row_index, cell in enumerate(cells):
            candidates = candidates_by_cell[row_index]
            nearby_count = sum(
                haversine_meters(cell["center"], (facility["lng"], facility["lat"])) <= NEARBY_RADIUS_M
                for facility in category_facilities
            )
            route_map = routes_by_cell[row_index]
            successful: list[tuple[WalkingResult, dict[str, Any]]] = []
            failed_count = 0
            for facility in candidates:
                route = route_map.get(facility["id"])
                if route is not None and route.success:
                    successful.append((route, facility))
                else:
                    failed_count += 1
            successful.sort(key=lambda item: (item[0].duration_s or math.inf, item[0].distance_m or math.inf))
            nearest_route, nearest_facility = successful[0] if successful else (None, None)
            evidence = CellEvidence(
                nearby_facility_count=nearby_count,
                candidate_facility_count=len(candidates),
                nearest_facility=nearest_facility,
                nearest_route=nearest_route,
                failed_route_count=failed_count,
                facility_discovery_succeeded=category not in failed_categories,
            )
            classification = classify_service_area_cell(evidence, threshold_minutes)
            grid_id = f"{category}-{cell['id']}"
            if failed_count:
                failure = {
                    "scope": "service_area_grid",
                    "category": category,
                    "code": "service_area_walking_partial",
                    "object_ref": grid_id,
                    "failed_count": failed_count,
                    "message": f"{grid_id} 有 {failed_count} 条同类设施步行结果失败",
                }
                partial_failures.append(failure)
                quality_events.append(
                    {
                        "code": "service_area_walking_partial",
                        "severity": "warning",
                        "scope": "service_area_grid",
                        "category": category,
                        "object_ref": grid_id,
                        "source": provider.descriptor.source,
                        "method": "provider_walking_matrix",
                        "message": failure["message"],
                    }
                )
            features.append(
                _feature(
                    cell,
                    category,
                    threshold_minutes,
                    evidence,
                    classification,
                    provider.descriptor.source,
                )
            )

    return {"type": "FeatureCollection", "features": features}, quality_events, partial_failures


async def _walking_results_by_cell(
    provider: MapProvider,
    cells: list[dict[str, Any]],
    candidates_by_cell: list[list[dict[str, Any]]],
) -> list[dict[str, WalkingResult]]:
    """按相同候选集合分组调用矩阵，避免为预筛选外的坐标对计算路线。"""
    route_maps: list[dict[str, WalkingResult]] = [{} for _ in cells]
    groups: dict[tuple[str, ...], list[int]] = {}
    for cell_index, candidates in enumerate(candidates_by_cell):
        signature = tuple(item["id"] for item in candidates)
        if signature:
            groups.setdefault(signature, []).append(cell_index)

    facilities_by_id = {
        item["id"]: item
        for candidates in candidates_by_cell
        for item in candidates
    }
    for signature, cell_indexes in groups.items():
        destinations = [facilities_by_id[facility_id] for facility_id in signature]
        try:
            matrix = await provider.walking_matrix(
                [cells[cell_index]["center"] for cell_index in cell_indexes],
                [(item["lng"], item["lat"]) for item in destinations],
            )
        except MapProviderError:
            matrix = []
        for matrix_row_index, cell_index in enumerate(cell_indexes):
            row = matrix[matrix_row_index] if matrix_row_index < len(matrix) else []
            route_maps[cell_index] = {
                facility_id: row[destination_index]
                for destination_index, facility_id in enumerate(signature)
                if destination_index < len(row)
            }
    return route_maps


def _build_grid(center: tuple[float, float], grid_size: int, span_m: int) -> list[dict[str, Any]]:
    cell_size = span_m * 2 / grid_size
    cells: list[dict[str, Any]] = []
    for row in range(grid_size):
        for column in range(grid_size):
            west = -span_m + column * cell_size
            south = -span_m + row * cell_size
            corners = [
                _offset_point(center, west, south),
                _offset_point(center, west + cell_size, south),
                _offset_point(center, west + cell_size, south + cell_size),
                _offset_point(center, west, south + cell_size),
            ]
            cells.append(
                {
                    "id": f"r{row + 1}c{column + 1}",
                    "center": _offset_point(center, west + cell_size / 2, south + cell_size / 2),
                    "coordinates": [[lng, lat] for lng, lat in [*corners, corners[0]]],
                }
            )
    return cells


def _offset_point(center: tuple[float, float], east_m: float, north_m: float) -> tuple[float, float]:
    lng, lat = center
    return (
        lng + east_m / (111_320 * math.cos(math.radians(lat))),
        lat + north_m / 111_320,
    )


def _feature(
    cell: dict[str, Any],
    category: str,
    threshold_minutes: int,
    evidence: CellEvidence,
    classification: CellClassification,
    provider_source: str,
) -> dict[str, Any]:
    route = evidence.nearest_route
    facility = evidence.nearest_facility
    walk_threshold_exceeded = None if route is None else (route.duration_s or 0) > threshold_minutes * 60
    if evidence.candidate_facility_count == 0 and evidence.facility_discovery_succeeded:
        walk_threshold_exceeded = True
    lacks_nearby_facility = evidence.nearby_facility_count == 0
    labels = {"normal": "正常覆盖区", "sparse": "设施稀疏区", "critical": "重点服务盲区"}
    colors = {"normal": "#4f9d7f", "sparse": "#d8a64e", "critical": "#c75c43"}
    return {
        "type": "Feature",
        "properties": {
            "grid_id": f"{category}-{cell['id']}",
            "coordinate_system": "BD-09",
            "kind": classification.kind,
            "region_type": classification.kind,
            "label": labels[classification.kind],
            "category": category,
            "category_label": CATEGORIES[category]["label"],
            "color": colors[classification.kind],
            "threshold_minutes": threshold_minutes,
            "nearby_radius_m": NEARBY_RADIUS_M,
            "nearby_facility_count": evidence.nearby_facility_count,
            "lacks_nearby_facility": lacks_nearby_facility,
            "candidate_prefilter_radius_m": CANDIDATE_PREFILTER_RADIUS_M,
            "candidate_facility_count": evidence.candidate_facility_count,
            "nearest_facility_id": facility["id"] if facility else None,
            "nearest_facility_name": facility["name"] if facility else None,
            "nearest_walk_minutes": round((route.duration_s or 0) / 60, 1) if route else None,
            "nearest_walk_distance_m": round(route.distance_m or 0) if route else None,
            "walk_threshold_exceeded": walk_threshold_exceeded,
            "critical_conditions_met": walk_threshold_exceeded is True and lacks_nearby_facility,
            "source": route.source if route else provider_source,
            "calculation_method": route.method if route else "facility_absence_or_failed_walking_matrix",
            "basis": classification.basis,
            "confidence": classification.confidence,
            "failed_route_count": evidence.failed_route_count,
        },
        "geometry": {"type": "Polygon", "coordinates": [cell["coordinates"]]},
    }
