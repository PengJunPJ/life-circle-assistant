from math import cos, pi

CENTER = {"lng": 113.4872, "lat": 23.1068, "address": "广州市黄埔区红山街道海韵东路离线样例中心"}

# service_area_grid=True 的类别参与 16 格盲区网格测算（评审盲区口径：菜市场/药店/小学+医疗）；
# 扩展类（养老/公园/便利超市）只算覆盖度与最近可达，跳过网格以控制步行 API 调用量。
CATEGORIES = {
    "market": {"label": "菜市场", "color": "#e38b45", "weight": 18, "service_area_grid": True},
    "pharmacy": {"label": "药店", "color": "#d65a5a", "weight": 18, "service_area_grid": True},
    "school": {"label": "小学", "color": "#3d83b8", "weight": 18, "service_area_grid": True},
    "medical": {"label": "医疗服务", "color": "#3e9b8b", "weight": 16, "service_area_grid": True},
    "elderly": {"label": "养老", "color": "#9061c2", "weight": 10, "service_area_grid": False},
    "park": {"label": "公园绿地", "color": "#55a05a", "weight": 10, "service_area_grid": False},
    "convenience": {"label": "便利超市", "color": "#d9a13b", "weight": 10, "service_area_grid": False},
}

POIS = [
    {"id": "m-01", "name": "离线样例菜市场 A", "category": "market", "lng": 113.4891, "lat": 23.1085, "walk_minutes": 6},
    {"id": "m-02", "name": "离线样例农贸市场 B", "category": "market", "lng": 113.4818, "lat": 23.1042, "walk_minutes": 10},
    {"id": "p-01", "name": "离线样例药店 A", "category": "pharmacy", "lng": 113.4887, "lat": 23.1053, "walk_minutes": 5},
    {"id": "p-02", "name": "离线样例药店 B", "category": "pharmacy", "lng": 113.4937, "lat": 23.1092, "walk_minutes": 12},
    {"id": "s-01", "name": "离线样例小学 A", "category": "school", "lng": 113.4904, "lat": 23.1078, "walk_minutes": 8},
    {"id": "s-02", "name": "离线样例小学 B", "category": "school", "lng": 113.4808, "lat": 23.1105, "walk_minutes": 16},
    {"id": "h-01", "name": "离线样例医疗服务 A", "category": "medical", "lng": 113.4851, "lat": 23.1029, "walk_minutes": 9},
    {"id": "e-01", "name": "离线样例养老服务中心 A", "category": "elderly", "lng": 113.4862, "lat": 23.1091, "walk_minutes": 7},
    {"id": "e-02", "name": "离线样例敬老院 B", "category": "elderly", "lng": 113.4925, "lat": 23.1040, "walk_minutes": 13},
    {"id": "g-01", "name": "离线样例社区公园 A", "category": "park", "lng": 113.4835, "lat": 23.1080, "walk_minutes": 6},
    {"id": "g-02", "name": "离线样例口袋公园 B", "category": "park", "lng": 113.4910, "lat": 23.1035, "walk_minutes": 11},
    {"id": "c-01", "name": "离线样例便利超市 A", "category": "convenience", "lng": 113.4880, "lat": 23.1062, "walk_minutes": 4},
    {"id": "c-02", "name": "离线样例综合超市 B", "category": "convenience", "lng": 113.4822, "lat": 23.1050, "walk_minutes": 9},
]

def point(lng_offset: float, lat_offset: float) -> list[float]:
    return [CENTER["lng"] + lng_offset, CENTER["lat"] + lat_offset]

def polygon_feature(coords: list[list[float]], properties: dict) -> dict:
    return {"type": "Feature", "properties": properties, "geometry": {"type": "Polygon", "coordinates": [coords]}}

def mock_isochrone(minutes: int = 15) -> dict:
    scale = minutes / 15
    offsets = [
        (-0.010 * scale, 0.000), (-0.007 * scale, 0.006 * scale),
        (0.000, 0.009 * scale), (0.008 * scale, 0.006 * scale),
        (0.012 * scale, 0.000), (0.007 * scale, -0.007 * scale),
        (0.000, -0.011 * scale), (-0.008 * scale, -0.007 * scale),
    ]
    coords = [point(x, y) for x, y in offsets]
    coords.append(coords[0])
    return polygon_feature(coords, {"minutes": minutes, "mode": "mock", "area_sqm": round(860000 * scale * scale)})

def mock_zones() -> dict:
    zones = [
        polygon_feature([point(-0.014, 0.002), point(-0.007, 0.006), point(-0.006, 0.001), point(-0.013, -0.003), point(-0.014, 0.002)], {"kind": "critical", "label": "西北侧菜市场重点服务盲区", "category": "market", "color": "#c75c43"}),
        polygon_feature([point(0.006, 0.009), point(0.014, 0.006), point(0.013, 0.001), point(0.007, 0.002), point(0.006, 0.009)], {"kind": "sparse", "label": "东北侧设施稀疏区", "category": "medical", "color": "#d8a64e"}),
    ]
    return {"type": "FeatureCollection", "features": zones}
