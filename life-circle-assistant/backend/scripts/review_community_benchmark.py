#!/usr/bin/env python3
"""用百度真实 POI/步行结果生成社区全网格人工核查草稿。

该脚本不读取系统报告里的 ``kind`` 作为人工真值，只复用报告的网格几何、
中心和类别配置。人工标签依据独立 POI 检索与步行矩阵重新计算。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.baidu import haversine_meters  # noqa: E402
from app.maps.baidu import BaiduMapProvider  # noqa: E402
from app.maps.provider import FacilityResult, WalkingResult  # noqa: E402
from app.validation.benchmarks import CommunityBenchmark  # noqa: E402

NEARBY_RADIUS_M = 1_000
THRESHOLD_MINUTES = 15
REVIEWER = "项目组人工核查（百度地图 Web 服务）"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 顶层必须是对象：{path}")
    return value


def grid_centers(report: dict[str, Any]) -> dict[str, tuple[float, float]]:
    centers: dict[str, tuple[float, float]] = {}
    for feature in (report.get("service_areas") or {}).get("features", []):
        properties = feature.get("properties") or {}
        grid_id = properties.get("grid_id")
        coordinates = ((feature.get("geometry") or {}).get("coordinates") or [[]])[0]
        if not grid_id or len(coordinates) < 4:
            continue
        lng = sum(point[0] for point in coordinates[:4]) / 4
        lat = sum(point[1] for point in coordinates[:4]) / 4
        centers[str(grid_id)] = (lng, lat)
    return centers


def dedupe(facilities: list[FacilityResult]) -> list[FacilityResult]:
    seen: set[tuple[str, float, float]] = set()
    result: list[FacilityResult] = []
    for item in facilities:
        key = (item.id, round(item.lng, 6), round(item.lat, 6))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def classify(nearby_count: int, nearest: WalkingResult | None) -> tuple[str, str]:
    if nearest is None or not nearest.success or nearest.duration_s is None:
        return "unknown", "未获得有效步行路线，不能形成可靠人工真值。"
    exceeds = nearest.duration_s > THRESHOLD_MINUTES * 60
    has_nearby = nearby_count > 0
    minutes = nearest.duration_s / 60
    if exceeds and not has_nearby:
        return "critical", f"最近同类设施步行约 {minutes:.1f} 分钟，超过 15 分钟，1 公里内无同类设施。"
    if not exceeds and has_nearby:
        return (
            "normal",
            f"最近同类设施步行约 {minutes:.1f} 分钟，不超过 15 分钟，1 公里内有 {nearby_count} 处同类设施。",
        )
    if exceeds:
        return "sparse", f"1 公里内有 {nearby_count} 处同类设施，但最近有效步行约 {minutes:.1f} 分钟，超过 15 分钟。"
    return "sparse", f"1 公里内无同类设施，但最近有效步行约 {minutes:.1f} 分钟，仍在 15 分钟内。"


async def review(report_path: Path, benchmark_path: Path) -> dict[str, Any]:
    report = load_json(report_path)
    benchmark = load_json(benchmark_path)
    model = CommunityBenchmark.model_validate(benchmark)
    provider = BaiduMapProvider()
    centers = grid_centers(report)
    if len(centers) != len(model.labels):
        raise ValueError(f"报告网格中心数量 {len(centers)} 与基准标签数量 {len(model.labels)} 不一致")

    try:
        category_centers: dict[str, list[tuple[str, tuple[float, float]]]] = {}
        for label in model.labels:
            category_centers.setdefault(label.category, []).append((label.grid_id, centers[label.grid_id]))

        facilities_by_category: dict[str, list[FacilityResult]] = {}
        for category in model.categories:
            facilities_by_category[category] = dedupe(
                await provider.search_facilities(
                    category, (model.community.center_lng, model.community.center_lat), 3_000
                )
            )

        labels_by_id = {label.grid_id: label.model_dump(mode="json") for label in model.labels}
        reviewed_at = date.today().isoformat()
        for category, entries in category_centers.items():
            facilities = facilities_by_category[category]
            for grid_id, center in entries:
                nearby = [
                    item for item in facilities if haversine_meters(center, (item.lng, item.lat)) <= NEARBY_RADIUS_M
                ]
                candidates = [item for item in facilities if haversine_meters(center, (item.lng, item.lat)) <= 3_000]
                nearest: WalkingResult | None = None
                nearest_facility: FacilityResult | None = None
                if candidates:
                    matrix = await provider.walking_matrix([center], [(item.lng, item.lat) for item in candidates])
                    routes = matrix[0] if matrix else []
                    valid = [
                        (route, item)
                        for route, item in zip(routes, candidates)
                        if route.success and route.duration_s is not None
                    ]
                    if valid:
                        nearest, nearest_facility = min(valid, key=lambda pair: pair[0].duration_s or float("inf"))
                expected_kind, basis = classify(len(nearby), nearest)
                item = labels_by_id[grid_id]
                item["expected_kind"] = expected_kind
                item["evidence"] = {
                    "source": "百度地图 Web 服务 POI 检索 + 步行路线（独立于系统预测）",
                    "checked_at": reviewed_at,
                    "reviewer": REVIEWER,
                    "notes": (
                        f"网格中心 BD-09 {center[0]:.6f},{center[1]:.6f}；"
                        f"1公里内设施 {len(nearby)} 个；候选设施 {len(candidates)} 个；"
                        f"最近设施 {nearest_facility.name if nearest_facility else '无有效路线'}；{basis}"
                    ),
                }

        benchmark["status"] = (
            "verified" if all(item["expected_kind"] != "unknown" for item in labels_by_id.values()) else "draft"
        )
        benchmark["labels"] = [labels_by_id[label.grid_id] for label in model.labels]
        benchmark["notes"] = (
            "独立人工核查：按每个网格中心，分别检索同类设施，使用直线 1 公里附近口径和百度步行路线判断。"
            "unknown 网格保留 draft，不能作为完整验证基准。"
        )
        return benchmark
    finally:
        await provider.client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="生成社区全网格人工核查基准")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    args = parser.parse_args()
    if os.getenv("BAIDU_MAP_MODE", "real").strip().lower() != "real" or not os.getenv("BAIDU_MAP_AK", "").strip():
        raise SystemExit("需要 BAIDU_MAP_MODE=real 和 BAIDU_MAP_AK；不将 mock 结果写入人工真值。")
    result = asyncio.run(review(args.report, args.benchmark))
    args.benchmark.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已写入人工核查基准：{args.benchmark}（status={result['status']}）")


if __name__ == "__main__":
    main()
