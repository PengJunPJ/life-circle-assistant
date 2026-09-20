from math import cos, pi

CENTER = {"lng": 113.4872, "lat": 23.1068, "address": "广州市黄埔区红山街道海韵东路离线样例中心"}

CATEGORIES = {
    "market": {"label": "菜市场", "color": "#e38b45", "weight": 25},
    "pharmacy": {"label": "药店", "color": "#d65a5a", "weight": 25},
    "school": {"label": "小学", "color": "#3d83b8", "weight": 25},
    "medical": {"label": "医疗服务", "color": "#3e9b8b", "weight": 25},
}

POIS = [
    {"id": "m-01", "name": "离线样例菜市场 A", "category": "market", "lng": 113.4891, "lat": 23.1085, "walk_minutes": 6},
    {"id": "m-02", "name": "离线样例农贸市场 B", "category": "market", "lng": 113.4818, "lat": 23.1042, "walk_minutes": 10},
    {"id": "p-01", "name": "离线样例药店 A", "category": "pharmacy", "lng": 113.4887, "lat": 23.1053, "walk_minutes": 5},
    {"id": "p-02", "name": "离线样例药店 B", "category": "pharmacy", "lng": 113.4937, "lat": 23.1092, "walk_minutes": 12},
    {"id": "s-01", "name": "离线样例小学 A", "category": "school", "lng": 113.4904, "lat": 23.1078, "walk_minutes": 8},
    {"id": "s-02", "name": "离线样例小学 B", "category": "school", "lng": 113.4808, "lat": 23.1105, "walk_minutes": 16},
    {"id": "h-01", "name": "离线样例医疗服务 A", "category": "medical", "lng": 113.4851, "lat": 23.1029, "walk_minutes": 9},
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
