"""百度原生等时圈返回适配。严禁把格式错误或权限失败转为伪造几何。"""

from __future__ import annotations

import copy
import math
import re
from typing import Any

from .provider import MapProviderError


def validate_isochrone_geometry(geometry: dict[str, Any]) -> dict[str, Any]:
    kind = geometry.get("type")
    if kind not in {"Polygon", "MultiPolygon"}:
        raise MapProviderError("原生等时圈必须返回多边形", code="native_geometry_invalid")
    polygons = [geometry.get("coordinates")] if kind == "Polygon" else geometry.get("coordinates")
    if not isinstance(polygons, list) or not polygons:
        raise MapProviderError("原生等时圈缺少坐标", code="native_geometry_invalid")
    count = 0
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise MapProviderError("原生等时圈缺少环", code="native_geometry_invalid")
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                raise MapProviderError("原生等时圈环必须闭合且至少四个坐标", code="native_geometry_invalid")
            for coordinate in ring:
                count += 1
                if (
                    not isinstance(coordinate, (list, tuple))
                    or len(coordinate) != 2
                    or any(
                        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                        for v in coordinate
                    )
                    or not -180 <= coordinate[0] <= 180
                    or not -90 <= coordinate[1] <= 90
                ):
                    raise MapProviderError("原生等时圈含无效经纬度", code="native_geometry_invalid")
            if len({tuple(coordinate) for coordinate in ring[:-1]}) < 3 or _ring_area(ring) <= 0:
                raise MapProviderError("原生等时圈环退化", code="native_geometry_invalid")
    if count > 50_000:
        raise MapProviderError("原生等时圈坐标超出处理上限", code="native_geometry_invalid")
    return copy.deepcopy(geometry)


def parse_native_isochrone(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise MapProviderError("原生等时圈缺少结果", code="native_geometry_invalid")
    if isinstance(result.get("geometry"), dict):
        return validate_isochrone_geometry(result["geometry"])
    path = result.get("path")
    # 官方 result.path 为坐标字符串；兼容分号/竖线逐对和逗号平铺。
    if not isinstance(path, str) or not path.strip() or len(path) > 2_000_000:
        raise MapProviderError("原生等时圈缺少path", code="native_geometry_invalid")
    parts = re.split(r"[;,|\s]+", path.strip())
    if len(parts) % 2:
        raise MapProviderError("原生等时圈path不是完整坐标对", code="native_geometry_invalid")
    try:
        values = [float(value) for value in parts]
    except ValueError as exc:
        raise MapProviderError("原生等时圈path坐标非数字", code="native_geometry_invalid") from exc
    ring = [[values[index], values[index + 1]] for index in range(0, len(values), 2)]
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return validate_isochrone_geometry({"type": "Polygon", "coordinates": [ring]})


def _ring_area(ring) -> float:
    latitude = sum(point[1] for point in ring[:-1]) / max(1, len(ring) - 1)
    factor = 111_320**2 * math.cos(math.radians(latitude))
    # 平移到首点，避免大经纬度相乘导致小面积相消。
    origin = ring[0]
    points = [(lng - origin[0], lat - origin[1]) for lng, lat in ring]
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:]))) * factor / 2


def geometry_area_sqm(geometry: dict[str, Any]) -> int:
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    return round(
        sum(max(0.0, _ring_area(polygon[0]) - sum(_ring_area(ring) for ring in polygon[1:])) for polygon in polygons)
    )
