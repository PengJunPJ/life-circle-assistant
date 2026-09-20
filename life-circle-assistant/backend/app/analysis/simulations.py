from __future__ import annotations

import copy
import math
import uuid
from datetime import datetime, timezone
from typing import Any

from ..maps.provider import MapProvider, MapProviderError
from ..mock_data import CATEGORIES
from ..schemas import SimulationRequest
from .scoring import aggregate_overall_score, score_category
from .service_areas import build_category_service_areas


class SimulationValidationError(ValueError):
    """模拟请求与来源报告不一致。"""


class ReportSimulationService:
    """基于不可变来源报告计算单个假设设施场景。"""

    def __init__(self, provider: MapProvider) -> None:
        self.provider = provider

    async def run(self, report: dict[str, Any], request: SimulationRequest) -> dict[str, Any]:
        selected_categories = list(report.get("request", {}).get("categories", []))
        if request.category not in selected_categories:
            raise SimulationValidationError("只能模拟来源报告已选择的民生设施类别")

        lng, lat, candidate = self._resolve_location(report, request)
        center_data = report["analysis_center"]
        center = (float(center_data["lng"]), float(center_data["lat"]))
        source_facilities = copy.deepcopy(report.get("facilities") or report.get("pois") or [])
        category_facilities = [item for item in source_facilities if item.get("category") == request.category]
        hypothetical, facility_events, facility_failures = await self._build_hypothetical_facility(
            request.category,
            lng,
            lat,
            center,
        )
        simulated_category_facilities = [*category_facilities, hypothetical]

        service_areas, quality_events, partial_failures = await build_category_service_areas(
            self.provider,
            center,
            [request.category],
            simulated_category_facilities,
            int(report["request"]["minutes"]),
        )
        quality_events = [*facility_events, *quality_events]
        partial_failures = [*facility_failures, *partial_failures]
        original_areas = {
            "type": "FeatureCollection",
            "features": [
                copy.deepcopy(feature)
                for feature in (report.get("service_areas") or report.get("zones") or {}).get("features", [])
                if feature.get("properties", {}).get("category") == request.category
            ],
        }

        original_scores = copy.deepcopy(report.get("category_scores") or report.get("categories") or [])
        original_category_score = next(
            (item for item in original_scores if item.get("category") == request.category),
            None,
        )
        if original_category_score is None:
            raise SimulationValidationError("来源报告缺少该类别的评分结果")

        simulated_category_score = score_category(
            request.category,
            simulated_category_facilities,
            center,
        )
        simulated_scores = [
            simulated_category_score if item.get("category") == request.category else item
            for item in original_scores
        ]
        simulated_overall = aggregate_overall_score(simulated_scores)
        before = self._snapshot(
            original_category_score,
            report.get("scoring", {}).get("score"),
            original_areas,
        )
        after = self._snapshot(
            simulated_category_score,
            simulated_overall["score"],
            service_areas,
        )

        return {
            "id": str(uuid.uuid4()),
            "report_id": report["report_id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "coordinate_system": "BD-09",
            "selection_method": request.selection_method,
            "candidate_id": candidate.get("id") if candidate else None,
            "category": request.category,
            "category_label": CATEGORIES[request.category]["label"],
            "hypothetical_facility": hypothetical,
            "before": before,
            "after": after,
            "delta": {
                "category_score": _difference(after["category_score"], before["category_score"]),
                "overall_score": _difference(after["overall_score"], before["overall_score"]),
                "coverage_area_sqm": after["coverage_area_sqm"] - before["coverage_area_sqm"],
                "critical_zone_count": after["critical_zone_count"] - before["critical_zone_count"],
                "sparse_zone_count": after["sparse_zone_count"] - before["sparse_zone_count"],
            },
            "unaffected_category_scores": [
                item for item in simulated_scores if item.get("category") != request.category
            ],
            "data_quality": {
                "source": self.provider.descriptor.source,
                "events": quality_events,
                "partial_failures": partial_failures,
                "disclosure": "模拟结果仅用于方案比较，不修改来源设施或原始体检报告。",
            },
        }

    def _resolve_location(
        self,
        report: dict[str, Any],
        request: SimulationRequest,
    ) -> tuple[float, float, dict[str, Any] | None]:
        if request.selection_method == "map":
            return request.lng, request.lat, None
        if not request.candidate_id:
            raise SimulationValidationError("从规划建议模拟时必须提供候选点标识")
        for recommendation in report.get("recommendations", []):
            if recommendation.get("category") != request.category:
                continue
            for candidate in recommendation.get("candidate_locations", []):
                if candidate.get("id") == request.candidate_id:
                    return float(candidate["lng"]), float(candidate["lat"]), candidate
        raise SimulationValidationError("规划候选点不存在或与所选类别不一致")

    async def _build_hypothetical_facility(
        self,
        category: str,
        lng: float,
        lat: float,
        center: tuple[float, float],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        route = None
        events: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        failure_message = ""
        try:
            matrix = await self.provider.walking_matrix(
                [center],
                [(lng, lat)],
            )
            route = matrix[0][0] if matrix and matrix[0] else None
        except MapProviderError as exc:
            failure_message = str(exc)
        if route is None or not route.success:
            message = failure_message or (route.error_message if route else "步行矩阵未返回假设设施结果")
            failures.append({
                "scope": "hypothetical_facility",
                "code": "hypothetical_walking_failed",
                "message": message,
            })
            events.append({
                "code": "hypothetical_walking_failed",
                "severity": "warning",
                "scope": "hypothetical_facility",
                "category": category,
                "object_ref": None,
                "source": self.provider.descriptor.source,
                "method": "provider_walking_matrix",
                "message": message,
            })
        facility = {
            "id": f"hypothetical-{category}-{uuid.uuid4().hex[:10]}",
            "name": f"假设{CATEGORIES[category]['label']}",
            "category": category,
            "lng": lng,
            "lat": lat,
            "address": "规划模拟点",
            "walk_minutes": round((route.duration_s or 0) / 60, 1) if route and route.success else None,
            "walk_distance_m": round(route.distance_m or 0) if route and route.success else None,
            "source": route.source if route and route.success else "hypothetical",
            "calculation_method": route.method if route and route.success else "provider_walking_matrix_failed",
            "is_hypothetical": True,
        }
        return facility, events, failures

    @staticmethod
    def _snapshot(
        category_score: dict[str, Any],
        overall_score: int | None,
        service_areas: dict[str, Any],
    ) -> dict[str, Any]:
        features = service_areas.get("features", [])
        critical = [item for item in features if item.get("properties", {}).get("kind") == "critical"]
        sparse = [item for item in features if item.get("properties", {}).get("kind") == "sparse"]
        covered = [item for item in features if item.get("properties", {}).get("kind") != "critical"]
        return {
            "category_score": category_score.get("score"),
            "overall_score": overall_score,
            "coverage_area_sqm": round(sum(_polygon_area_sqm(item["geometry"]["coordinates"][0]) for item in covered)),
            "critical_zone_count": len(critical),
            "sparse_zone_count": len(sparse),
            "category_score_detail": category_score,
            "service_areas": service_areas,
        }


def _difference(after: int | None, before: int | None) -> int | None:
    return after - before if after is not None and before is not None else None


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
