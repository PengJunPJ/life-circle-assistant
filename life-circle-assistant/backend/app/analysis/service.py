from __future__ import annotations

import math
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable

from ..contracts.reports import build_quality_summary, create_report_skeleton, quality_event
from ..maps.provider import MapProvider, MapProviderError, WalkingResult
from ..mock_data import CATEGORIES, mock_isochrone
from ..schemas import AnalyzeRequest
from .scoring import score_report
from .service_areas import build_category_service_areas


StageUpdater = Callable[[str, str, int], None]

STAGES = {
    "request_validation": "请求校验",
    "facility_discovery": "设施发现",
    "walking_calculation": "步行计算",
    "region_classification": "区域分类",
    "scoring": "评分生成",
    "report_assembly": "报告组装",
    "completed": "分析完成",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def polygon_feature(coords: list[list[float]], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "Feature", "properties": properties, "geometry": {"type": "Polygon", "coordinates": [coords]}}


def interpolate_point(center: tuple[float, float], angle: float, radius_m: float) -> tuple[float, float]:
    lng, lat = center
    return (
        lng + math.cos(angle) * radius_m / (111_320 * math.cos(math.radians(lat))),
        lat + math.sin(angle) * radius_m / 111_320,
    )


class AnalysisApplicationService:
    """通过可替换地图提供方编排一次公开分析任务。"""

    def __init__(self, provider: MapProvider, update_stage: StageUpdater | None = None) -> None:
        self.provider = provider
        self.update_stage = update_stage or (lambda _code, _label, _progress: None)
        self.stage_history: list[dict[str, Any]] = []

    async def run(self, task_id: str, request: AnalyzeRequest) -> dict[str, Any]:
        started_at = now()
        started_clock = time.perf_counter()
        events: list[dict[str, Any]] = []
        partial_failures: list[dict[str, Any]] = []
        descriptor = self.provider.descriptor
        center = (request.lng, request.lat)

        self._stage("request_validation", 16)
        if descriptor.source == "real_api":
            events.append(
                quality_event(
                    "real_api_used",
                    "info",
                    "task",
                    f"设施与步行结果使用{descriptor.label}。",
                    "real_api",
                    "provider",
                )
            )
        else:
            events.append(
                quality_event(
                    "snapshot_used",
                    "warning",
                    "task",
                    "当前使用本地快照完成离线演示，不代表最新真实地图测算。",
                    "local_snapshot",
                    "provider",
                )
            )

        self._stage("facility_discovery", 32)
        facilities: list[dict[str, Any]] = []
        failed_categories: set[str] = set()
        for category in request.categories:
            try:
                results = await self.provider.search_facilities(category, center, radius_m=3_000)
                facilities.extend(asdict(item) for item in results)
            except MapProviderError as exc:
                failed_categories.add(category)
                partial_failures.append({"scope": "category", "category": category, "code": "facility_search_failed", "message": str(exc)})
                events.append(
                    quality_event(
                        "category_partial",
                        "warning",
                        "category",
                        f"{CATEGORIES[category]['label']}设施检索失败，该类别结果不完整：{exc}",
                        descriptor.source,
                        "facility_search",
                        category=category,
                    )
                )

        self._stage("walking_calculation", 54)
        await self._attach_walking_results(center, facilities, events, partial_failures)
        isochrone = await self._build_isochrone(center, request, events, partial_failures)

        self._stage("region_classification", 72)
        zones, zone_events, zone_failures = await build_category_service_areas(
            self.provider,
            center,
            list(request.categories),
            facilities,
            request.minutes,
            failed_categories=failed_categories,
        )
        events.extend(zone_events)
        partial_failures.extend(zone_failures)

        self._stage("scoring", 86)
        scoring = score_report(request.categories, facilities, center, failed_categories)
        stats = scoring["category_scores"]
        overall_scoring = scoring["overall"]
        critical = sum(item["properties"]["kind"] == "critical" for item in zones["features"])
        sparse = sum(item["properties"]["kind"] == "sparse" for item in zones["features"])
        recommendations = [
            {
                "priority": "高",
                "title": f"补充{item['label']}服务",
                "body": f"{item['label']}的步行覆盖仍有不足，建议结合盲区位置补充服务点。",
                "category": item["category"],
            }
            for item in stats
            if item["category"] not in failed_categories
            and (item["count"] == 0 or (item["nearest_walk_minutes"] or 0) > request.minutes)
        ]

        self._stage("report_assembly", 95)
        data_quality = build_quality_summary(descriptor, events, partial_failures)
        completed_at = now()
        completeness = "partial" if partial_failures else "complete"
        execution = {
            "current_stage": "completed",
            "current_stage_label": STAGES["completed"],
            "stages": [*self.stage_history, {"code": "completed", "label": STAGES["completed"], "progress": 100, "at": completed_at}],
            "total_duration_ms": round((time.perf_counter() - started_clock) * 1_000),
            "metrics": {
                "facility_count": len(facilities),
                "quality_event_count": len(events),
                "partial_failure_count": len(partial_failures),
            },
        }
        report = create_report_skeleton(
            report_id=str(uuid.uuid4()),
            task_id=task_id,
            created_at=started_at,
            completed_at=completed_at,
            request_parameters=request.model_dump(),
            center={"lng": request.lng, "lat": request.lat, "address": "用户指定分析中心点"},
            descriptor=descriptor,
            completeness=completeness,
            execution=execution,
            data_quality=data_quality,
        )
        report.update(
            {
                "isochrone": isochrone,
                "pois": facilities,
                "facilities": facilities,
                "zones": zones,
                "service_areas": zones,
                "summary": {
                    "score": overall_scoring["score"],
                    "score_status": overall_scoring["status"],
                    "score_explanation": overall_scoring["explanation"],
                    "area_sqm": isochrone["properties"]["area_sqm"],
                    "poi_count": len(facilities),
                    "critical_zone_count": critical,
                    "sparse_zone_count": sparse,
                },
                "categories": stats,
                "category_scores": stats,
                "scoring": overall_scoring,
                "recommendations": recommendations,
            }
        )
        self._stage("completed", 100)
        return report

    def _stage(self, code: str, progress: int) -> None:
        label = STAGES[code]
        self.stage_history.append({"code": code, "label": label, "progress": progress, "at": now()})
        self.update_stage(code, label, progress)

    async def _attach_walking_results(
        self,
        center: tuple[float, float],
        facilities: list[dict[str, Any]],
        events: list[dict[str, Any]],
        partial_failures: list[dict[str, Any]],
    ) -> None:
        if not facilities:
            return
        destinations = [(item["lng"], item["lat"]) for item in facilities]
        try:
            rows = await self.provider.walking_matrix([center], destinations)
        except MapProviderError as exc:
            rows = [[]]
            partial_failures.append({"scope": "walking", "code": "walking_matrix_failed", "message": str(exc)})
        routes = rows[0] if rows else []
        for index, item in enumerate(facilities):
            route = routes[index] if index < len(routes) else None
            if not route or not route.success:
                item["walk_minutes"] = None
                item["walk_distance_m"] = None
                message = route.error_message if route else "步行矩阵未返回坐标对结果"
                partial_failures.append({"scope": "coordinate_pair", "code": "walking_result_failed", "object_ref": item["id"], "message": message})
                events.append(
                    quality_event(
                        "walk_failed",
                        "warning",
                        "coordinate_pair",
                        f"到 {item['name']} 的步行计算失败：{message}",
                        self.provider.descriptor.source,
                        "walking_matrix",
                        category=item["category"],
                        object_ref=item["id"],
                    )
                )
                continue
            item["walk_minutes"] = round((route.duration_s or 0) / 60, 1)
            item["walk_distance_m"] = round(route.distance_m or 0)
            item["source"] = route.source
            item["calculation_method"] = route.method
            self._record_degraded_route(route, events, item["category"], item["id"])

    async def _build_isochrone(
        self,
        center: tuple[float, float],
        request: AnalyzeRequest,
        events: list[dict[str, Any]],
        partial_failures: list[dict[str, Any]],
    ) -> dict[str, Any]:
        directions = 24 if request.mode == "analysis" else 16
        max_radius = 1_250
        boundary: list[tuple[float, float]] = []
        durations: list[float] = []
        for index in range(directions):
            angle = 2 * math.pi * index / directions
            candidate = interpolate_point(center, angle, max_radius)
            route = await self._single_route(center, candidate)
            if route and route.success and (route.duration_s or 0) <= request.minutes * 60:
                boundary.append(candidate)
                durations.append(route.duration_s or 0)
                self._record_degraded_route(route, events, object_ref=f"isochrone-{index}")
                continue
            if not route or not route.success:
                partial_failures.append({"scope": "isochrone_sample", "code": "isochrone_sample_failed", "object_ref": str(index), "message": route.error_message if route else "无步行结果"})
                events.append(
                    quality_event(
                        "isochrone_sample_failed",
                        "warning",
                        "isochrone",
                        f"等时圈方向 {index + 1} 的边界采样失败。",
                        self.provider.descriptor.source,
                        "walking_matrix",
                        object_ref=str(index),
                    )
                )
                continue
            low, high = 0.0, max_radius
            best_route = route
            for _ in range(3 if request.mode == "analysis" else 2):
                radius = (low + high) / 2
                point = interpolate_point(center, angle, radius)
                sample = await self._single_route(center, point)
                if not sample or not sample.success:
                    message = sample.error_message if sample else "无步行结果"
                    partial_failures.append(
                        {
                            "scope": "isochrone_sample",
                            "code": "isochrone_refinement_failed",
                            "object_ref": str(index),
                            "message": message,
                        }
                    )
                    events.append(
                        quality_event(
                            "isochrone_refinement_failed",
                            "warning",
                            "isochrone",
                            f"等时圈方向 {index + 1} 的边界细化失败，保留上一有效边界。",
                            self.provider.descriptor.source,
                            "walking_matrix",
                            object_ref=str(index),
                        )
                    )
                    break
                best_route = sample
                self._record_degraded_route(sample, events, object_ref=f"isochrone-{index}")
                if (sample.duration_s or 0) <= request.minutes * 60:
                    low = radius
                    durations.append(sample.duration_s or 0)
                else:
                    high = radius
            boundary.append(interpolate_point(center, angle, low))
            if best_route.success:
                durations.append(best_route.duration_s or 0)
        if len(boundary) < 6:
            events.append(
                quality_event(
                    "isochrone_degraded",
                    "warning",
                    "isochrone",
                    "有效步行采样不足，等时圈已降级为内置演示边界，不代表实时测算。",
                    "degraded_estimate",
                    "fallback_polygon",
                )
            )
            return mock_isochrone(request.minutes)
        coords = [[lng, lat] for lng, lat in boundary]
        coords.append(coords[0])
        area = abs(sum(coords[i][0] * coords[i + 1][1] - coords[i + 1][0] * coords[i][1] for i in range(len(coords) - 1))) / 2
        area_sqm = round(area * (111_320**2) * math.cos(math.radians(center[1])))
        return polygon_feature(
            coords,
            {
                "minutes": request.minutes,
                "mode": request.mode,
                "area_sqm": area_sqm,
                "sample_count": directions,
                "successful_sample_count": len(boundary),
                "max_duration_s": round(max(durations or [0])),
                "source": self.provider.descriptor.source,
            },
        )

    async def _single_route(self, origin: tuple[float, float], destination: tuple[float, float]) -> WalkingResult | None:
        try:
            rows = await self.provider.walking_matrix([origin], [destination])
        except MapProviderError:
            return None
        return rows[0][0] if rows and rows[0] else None

    @staticmethod
    def _record_degraded_route(
        route: WalkingResult,
        events: list[dict[str, Any]],
        category: str | None = None,
        object_ref: str | None = None,
    ) -> None:
        if route.source not in {"interpolation", "degraded_estimate"}:
            return
        key = (route.source, route.method, category, object_ref)
        if any((event["source"], event["method"], event["category"], event["object_ref"]) == key for event in events):
            return
        events.append(
            quality_event(
                "walking_estimate_used",
                "warning",
                "coordinate_pair",
                "该坐标对缺少快照路线，使用明确标记的步行估算，不代表真实 API 测算。",
                route.source,
                route.method,
                category=category,
                object_ref=object_ref,
            )
        )
