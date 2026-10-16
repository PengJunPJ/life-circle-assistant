"""RFC 7946 交换出口：本地近似反偏移，不调用地图服务，不改变原报告。

BD-09 使用通行的极坐标反偏移公式，GCJ-02 使用公开近似正向公式作
固定点逆解。迭代残差仅表示该近似公式的数值收敛，并非实际地图精度。
无需网络或新依赖；它不是官方逆转换，也不能用于测绘、权属或施工放样。
"""

from __future__ import annotations

import json
import math
from typing import Any

from .structured import ExportArtifact, _filename, build_geojson_collection

CONVERSION_METHOD = "bd09_analytic_inverse_then_gcj02_iterative_inverse"
CONVERSION_VERSION = "local-approximate-inverse-v1"
INVERSE_TOLERANCE_DEGREES = 1e-10
MAX_INVERSE_ITERATIONS = 30
_X_PI = math.pi * 3000 / 180
_ELLIPSOID_AXIS = 6378245.0
_ELLIPSOID_ECCENTRICITY_SQUARED = 0.006693421622965943


def _finite_number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _validate_coordinate(lng: Any, lat: Any) -> None:
    if not _finite_number(lng) or not _finite_number(lat) or not -180 <= lng <= 180 or not -90 <= lat <= 90:
        raise ValueError("坐标必须是范围内的有限经纬度数值，不能使用布尔值或数字字符串")


def _in_gcj_domain(lng: float, lat: float) -> bool:
    # 这是通行近似公式的矩形适用窗口，不是中国行政边界或官方加密范围。
    return 72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271


def _latitude_offset(x: float, y: float) -> float:
    result = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    result += (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
    result += (20 * math.sin(y * math.pi) + 40 * math.sin(y / 3 * math.pi)) * 2 / 3
    return result + (160 * math.sin(y / 12 * math.pi) + 320 * math.sin(y * math.pi / 30)) * 2 / 3


def _longitude_offset(x: float, y: float) -> float:
    result = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    result += (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
    result += (20 * math.sin(x * math.pi) + 40 * math.sin(x / 3 * math.pi)) * 2 / 3
    return result + (150 * math.sin(x / 12 * math.pi) + 300 * math.sin(x / 30 * math.pi)) * 2 / 3


def _wgs84_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    if not _in_gcj_domain(lng, lat):
        return lng, lat
    rad_lat = lat / 180 * math.pi
    sine = math.sin(rad_lat)
    magic = 1 - _ELLIPSOID_ECCENTRICITY_SQUARED * sine * sine
    root = math.sqrt(magic)
    dlat = _latitude_offset(lng - 105, lat - 35)
    dlng = _longitude_offset(lng - 105, lat - 35)
    dlat = dlat * 180 / ((_ELLIPSOID_AXIS * (1 - _ELLIPSOID_ECCENTRICITY_SQUARED)) / (magic * root) * math.pi)
    dlng = dlng * 180 / (_ELLIPSOID_AXIS / root * math.cos(rad_lat) * math.pi)
    return lng + dlng, lat + dlat


def bd09_to_wgs84(lng: float, lat: float) -> tuple[float, float]:
    """返回近似 WGS84 经纬度；拒绝非法值和近似公式无法收敛的输入。"""

    _validate_coordinate(lng, lat)
    x, y = lng - 0.0065, lat - 0.006
    radius = math.hypot(x, y) - 0.00002 * math.sin(y * _X_PI)
    angle = math.atan2(y, x) - 0.000003 * math.cos(x * _X_PI)
    gcj_lng, gcj_lat = radius * math.cos(angle), radius * math.sin(angle)
    guess_lng, guess_lat = gcj_lng, gcj_lat
    if not _in_gcj_domain(gcj_lng, gcj_lat):
        # 不声称该窗口外存在官方偏移；仍需披露 BD-09 反解的近似性质。
        _validate_coordinate(guess_lng, guess_lat)
        return guess_lng, guess_lat
    for _ in range(MAX_INVERSE_ITERATIONS):
        projected_lng, projected_lat = _wgs84_to_gcj02(guess_lng, guess_lat)
        delta_lng, delta_lat = projected_lng - gcj_lng, projected_lat - gcj_lat
        if max(abs(delta_lng), abs(delta_lat)) <= INVERSE_TOLERANCE_DEGREES:
            _validate_coordinate(guess_lng, guess_lat)
            return guess_lng, guess_lat
        guess_lng -= delta_lng
        guess_lat -= delta_lat
    raise ValueError("GCJ-02 近似逆转换未收敛；边界窗口或不适用坐标不能导出为已转换 WGS84")


def _position(position: Any) -> list[float]:
    if not isinstance(position, (list, tuple)) or len(position) not in {2, 3}:
        raise ValueError("GeoJSON 位置须为经纬度二元组，或含一个有限海拔值的三元组")
    lng, lat = bd09_to_wgs84(position[0], position[1])
    result = [lng, lat]
    if len(position) == 3:
        if not _finite_number(position[2]):
            raise ValueError("GeoJSON 海拔必须为有限数值")
        result.append(position[2])
    return result


def _signed_area(ring: list[list[float]]) -> float:
    lng, lat = ring[0][:2]
    return (
        sum(
            (first[0] - lng) * (second[1] - lat) - (second[0] - lng) * (first[1] - lat)
            for first, second in zip(ring, ring[1:])
        )
        / 2
    )


def _ring(ring: Any, *, exterior: bool) -> list[list[float]]:
    if not isinstance(ring, (list, tuple)) or len(ring) < 4 or ring[0] != ring[-1]:
        raise ValueError("GeoJSON 线性环须至少四个位置且首尾闭合；不自动补造边界")
    converted = [_position(position) for position in ring]
    if len({tuple(position[:2]) for position in ring[:-1]}) < 3:
        raise ValueError("GeoJSON 线性环须包含至少三个不同位置")
    area = _signed_area(converted)
    if area == 0:
        raise ValueError("GeoJSON 线性环面积为零")
    # RFC 7946 右手规则：外环逆时针、孔洞顺时针；反向不改变顶点或孔洞归属。
    return list(reversed(converted)) if (area > 0) != exterior else converted


def _polygon(coordinates: Any) -> list[list[list[float]]]:
    if not isinstance(coordinates, (list, tuple)) or not coordinates:
        raise ValueError("GeoJSON Polygon 缺少外环")
    return [_ring(ring, exterior=index == 0) for index, ring in enumerate(coordinates)]


def _geometry(geometry: Any) -> Any:
    if geometry is None:
        return None
    if not isinstance(geometry, dict):
        raise ValueError("GeoJSON geometry 必须是对象或 null")
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind == "Point":
        geometry["coordinates"] = _position(coordinates)
    elif kind in {"MultiPoint", "LineString"}:
        if not isinstance(coordinates, (list, tuple)) or (kind == "LineString" and len(coordinates) < 2):
            raise ValueError("GeoJSON 点列格式无效")
        geometry["coordinates"] = [_position(position) for position in coordinates]
    elif kind == "MultiLineString":
        if not isinstance(coordinates, (list, tuple)):
            raise ValueError("GeoJSON MultiLineString 格式无效")
        geometry["coordinates"] = [
            _geometry({"type": "LineString", "coordinates": line})["coordinates"] for line in coordinates
        ]
    elif kind == "Polygon":
        geometry["coordinates"] = _polygon(coordinates)
    elif kind == "MultiPolygon":
        if not isinstance(coordinates, (list, tuple)):
            raise ValueError("GeoJSON MultiPolygon 格式无效")
        geometry["coordinates"] = [_polygon(polygon) for polygon in coordinates]
    elif kind == "GeometryCollection":
        if not isinstance(geometry.get("geometries"), (list, tuple)):
            raise ValueError("GeoJSON GeometryCollection 格式无效")
        geometry["geometries"] = [_geometry(item) for item in geometry["geometries"]]
    else:
        raise ValueError(f"不支持的 GeoJSON 几何类型：{kind}")
    return geometry


def _location(location: dict[str, Any]) -> None:
    if location.get("coordinate_system", "BD-09") != "BD-09":
        raise ValueError("位置元数据必须属于内部 BD-09，不能重复转换其他坐标系")
    if "lng" in location or "lat" in location:
        lng, lat = bd09_to_wgs84(location.get("lng"), location.get("lat"))
        location.update(lng=lng, lat=lat)
    location.update(coordinate_system="WGS84", source_coordinate_system="BD-09")


def _remove_legacy_members(value: Any) -> None:
    if isinstance(value, dict):
        # 旧 bbox 不能在坐标转换后复用；标准出口选择不输出 bbox，避免误导。
        value.pop("crs", None)
        value.pop("bbox", None)
        for nested in value.values():
            _remove_legacy_members(nested)
    elif isinstance(value, list):
        for nested in value:
            _remove_legacy_members(nested)


def build_wgs84_geojson_export(report: dict[str, Any]) -> ExportArtifact:
    """生成本地近似转换的 RFC 7946 坐标出口；原 BD-09 报告不可变。"""

    source_system = (report.get("calculation_mode") or {}).get("coordinate_system", "BD-09")
    if source_system != "BD-09":
        raise ValueError("标准出口仅接受内部 BD-09 报告，不能重复转换其他坐标系")
    spatial_features = [report.get("isochrone")]
    spatial_features.extend((report.get("service_areas") or report.get("zones") or {}).get("features", []))
    if any(
        feature and (feature.get("properties") or {}).get("coordinate_system", "BD-09") != "BD-09"
        for feature in spatial_features
    ):
        raise ValueError("标准出口不接受与内部 BD-09 不一致的空间图层")
    collection = build_geojson_collection(report)
    for feature in collection["features"]:
        feature["geometry"] = _geometry(feature.get("geometry"))
        _location(feature["properties"])
    _location(collection["analysis_center"])
    _remove_legacy_members(collection)
    collection.update(
        coordinate_system="WGS84",
        source_coordinate_system="BD-09",
        parameters_coordinate_system="BD-09",
        conversion_method=CONVERSION_METHOD,
        conversion_version=CONVERSION_VERSION,
        conversion_precision={
            "approximate": True,
            "survey_grade": False,
            "verified_accuracy_m": None,
            "numerical_inverse_tolerance_degrees": INVERSE_TOLERANCE_DEGREES,
            "max_inverse_iterations": MAX_INVERSE_ITERATIONS,
            "gcj_approximation_window": [72.004, 0.8293, 137.8347, 55.8271],
            "outside_window_behavior": "仅反解 BD-09；不施加近似 GCJ-02 偏移",
            "disclosure": (
                "本地非官方近似逆转换；迭代残差不是现场精度，未获测绘级认证。"
                "GCJ 公式矩形窗口不是行政边界，窗口边缘不收敛时拒绝导出。"
                "孔洞和顶点连接保留并规范环方向；不修复或认证原始拓扑。"
                "不适用于权属、施工放样或精确测绘；请求参数仍为原始 BD-09。"
            ),
        },
    )
    return ExportArtifact(
        content=json.dumps(collection, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"),
        media_type="application/geo+json",
        filename=_filename(report, "geojson"),
    )
