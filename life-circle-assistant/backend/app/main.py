import asyncio
import math
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .baidu import BaiduMapClient, BaiduMapError, haversine_meters
from .local_snapshot import load_snapshot, snapshot_path
from .mock_data import CATEGORIES, CENTER, POIS, mock_isochrone, mock_zones
from .schemas import AnalyzeRequest

load_dotenv()
app = FastAPI(title="15分钟生活圈智能体检与规划助手", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
TASKS: dict[str, dict[str, Any]] = {}
MAP_CLIENT = BaiduMapClient()
LOCAL_SNAPSHOT = load_snapshot()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def polygon_feature(coords: list[list[float]], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "Feature", "properties": properties, "geometry": {"type": "Polygon", "coordinates": [coords]}}


def score_category(category: str, pois: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(pois)
    nearest = min((item.get("walk_minutes") for item in pois if item.get("walk_minutes") is not None), default=None)
    quantity_score = min(100, count * 35)
    time_score = 100 if nearest is None else max(0, round((1 - nearest / 20) * 100))
    distribution_score = min(100, 45 + count * 20)
    score = round(quantity_score * 0.4 + time_score * 0.4 + distribution_score * 0.2)
    return {"category": category, "label": CATEGORIES[category]["label"], "count": count, "nearest_walk_minutes": nearest, "score": score, "color": CATEGORIES[category]["color"]}


def interpolate_point(center: tuple[float, float], angle: float, radius_m: float) -> tuple[float, float]:
    lng, lat = center
    return (lng + math.cos(angle) * radius_m / (111_320 * math.cos(math.radians(lat))), lat + math.sin(angle) * radius_m / 111_320)


async def real_isochrone(center: tuple[float, float], minutes: int, mode: str) -> dict[str, Any]:
    directions = 24 if mode == "analysis" else 16
    max_radius = 1_250
    boundary: list[tuple[float, float]] = []
    durations: list[float] = []
    for index in range(directions):
        angle = 2 * math.pi * index / directions
        candidate = interpolate_point(center, angle, max_radius)
        route = await MAP_CLIENT.walking_route(center, candidate)
        if route["duration_s"] <= minutes * 60:
            boundary.append(candidate)
            durations.append(route["duration_s"])
            continue
        low, high = 0.0, max_radius
        for _ in range(3 if mode == "analysis" else 2):
            radius = (low + high) / 2
            point = interpolate_point(center, angle, radius)
            route = await MAP_CLIENT.walking_route(center, point)
            if route["duration_s"] <= minutes * 60:
                low = radius
                durations.append(route["duration_s"])
            else:
                high = radius
        boundary.append(interpolate_point(center, angle, low))
    if len(boundary) < 6:
        raise BaiduMapError("步行等时圈有效边界采样不足")
    coords = [[lng, lat] for lng, lat in boundary]
    coords.append(coords[0])
    area = abs(sum(coords[i][0] * coords[i + 1][1] - coords[i + 1][0] * coords[i][1] for i in range(len(coords) - 1))) / 2
    area_sqm = round(area * (111_320**2) * math.cos(math.radians(center[1])))
    return polygon_feature(coords, {"minutes": minutes, "mode": "real", "area_sqm": area_sqm, "sample_count": directions, "max_duration_s": round(max(durations or [0]))})


async def real_pois(center: tuple[float, float], categories: list[str]) -> list[dict[str, Any]]:
    queries = {"market": "菜市场,农贸市场,生鲜超市", "pharmacy": "药店", "school": "小学", "medical": "社区卫生服务中心,医院,诊所"}
    grouped: list[tuple[str, dict[str, Any]]] = []
    for category in categories:
        results = await MAP_CLIENT.search_poi(queries[category], center[0], center[1], 1_000)
        for item in results:
            location = item.get("location") or {}
            if "lng" not in location or "lat" not in location:
                continue
            grouped.append((category, {"id": item.get("uid") or str(uuid.uuid4()), "name": item.get("name") or CATEGORIES[category]["label"], "category": category, "lng": float(location["lng"]), "lat": float(location["lat"]), "address": item.get("address", ""), "source": "baidu"}))
    unique = {item[1]["id"]: item for item in grouped}
    values = list(unique.values())
    routes = await MAP_CLIENT.walking_routes(center, [(item[1]["lng"], item[1]["lat"]) for item in values])
    output = []
    for (_, item), route in zip(values, routes):
        item["walk_minutes"] = round(route["duration_s"] / 60, 1) if route else None
        item["walk_distance_m"] = round(route["distance_m"]) if route else None
        output.append(item)
    return output


def build_real_zones(center: tuple[float, float], pois: list[dict[str, Any]]) -> dict[str, Any]:
    features = []
    grid_size, span = 4, 1_000
    cell = span * 2 / grid_size
    for row in range(grid_size):
        for column in range(grid_size):
            x, y = -span + column * cell, -span + row * cell
            grid_center = interpolate_point(center, math.atan2(y, x), math.hypot(x, y))
            nearest = min((haversine_meters(grid_center, (item["lng"], item["lat"])) for item in pois), default=2_000)
            kind = "critical" if nearest > 1_000 else "sparse" if nearest > 650 else None
            if not kind:
                continue
            corners = [interpolate_point(center, math.atan2(y + dy, x + dx), math.hypot(x + dx, y + dy)) for dx, dy in [(0, 0), (cell, 0), (cell, cell), (0, cell)]]
            coords = [[lng, lat] for lng, lat in corners]
            coords.append(coords[0])
            features.append(polygon_feature(coords, {"kind": kind, "label": "重点服务盲区" if kind == "critical" else "设施稀疏区", "category": "mixed", "color": "#c75c43" if kind == "critical" else "#d8a64e", "basis": "百度 POI 真实坐标预筛选"}))
    return {"type": "FeatureCollection", "features": features}


async def build_report(request: AnalyzeRequest) -> dict[str, Any]:
    center = (request.lng, request.lat)
    if not MAP_CLIENT.real_available:
        snapshot = LOCAL_SNAPSHOT or {}
        snapshot_center = snapshot.get("center") or CENTER
        snapshot_pois = snapshot.get("pois") or POIS
        selected = [item for item in snapshot_pois if item["category"] in request.categories]
        stats = [score_category(category, [item for item in selected if item["category"] == category]) for category in request.categories]
        iso = snapshot.get("isochrone") if request.minutes == 15 else None
        iso = iso or mock_isochrone(request.minutes)
        zones = snapshot.get("zones") or mock_zones()
        critical = sum(item["properties"]["kind"] == "critical" for item in zones["features"])
        sparse = sum(item["properties"]["kind"] == "sparse" for item in zones["features"])
        return {"id": str(uuid.uuid4()), "status": "completed", "created_at": now(), "source": "local_snapshot", "quality": {"mode": "本地百度数据快照", "confidence": 0.86, "message": f"当前使用本地快照，不消耗百度地图 API 额度。快照文件：{snapshot_path()}"}, "center": snapshot_center, "isochrone": iso, "pois": selected, "zones": zones, "summary": {"score": round(sum(x["score"] for x in stats) / max(1, len(stats))), "area_sqm": iso["properties"]["area_sqm"], "poi_count": len(selected), "critical_zone_count": critical, "sparse_zone_count": sparse}, "categories": stats, "recommendations": [], "parameters": request.model_dump()}
    pois = await real_pois(center, request.categories)
    iso = await real_isochrone(center, request.minutes, request.mode)
    stats = [score_category(category, [item for item in pois if item["category"] == category]) for category in request.categories]
    zones = build_real_zones(center, pois)
    critical = sum(item["properties"]["kind"] == "critical" for item in zones["features"])
    sparse = sum(item["properties"]["kind"] == "sparse" for item in zones["features"])
    recommendations = [{"priority": "高", "title": f"补充{item['label']}服务", "body": f"真实百度地图数据表明，{item['label']}的步行覆盖仍有不足，建议结合盲区位置补充服务点。", "category": item["category"]} for item in stats if item["count"] == 0 or (item["nearest_walk_minutes"] or 0) > request.minutes]
    return {"id": str(uuid.uuid4()), "status": "completed", "created_at": now(), "source": "baidu", "quality": {"mode": "百度地图真实数据", "confidence": 0.92, "message": "POI、步行路线和等时圈边界来自百度地图 Web 服务。"}, "center": {"lng": request.lng, "lat": request.lat, "address": "用户指定分析中心点"}, "isochrone": iso, "pois": pois, "zones": zones, "summary": {"score": round(sum(x["score"] for x in stats) / max(1, len(stats))), "area_sqm": iso["properties"]["area_sqm"], "poi_count": len(pois), "critical_zone_count": critical, "sparse_zone_count": sparse}, "categories": stats, "recommendations": recommendations, "parameters": request.model_dump()}


def run_task(task_id: str, request: AnalyzeRequest) -> None:
    async def execute() -> None:
        TASKS[task_id]["status"], TASKS[task_id]["progress"] = "running", 24
        try:
            TASKS[task_id]["result"] = await build_report(request)
            TASKS[task_id]["status"], TASKS[task_id]["progress"] = "completed", 100
        except Exception as exc:
            TASKS[task_id]["status"], TASKS[task_id]["progress"] = "failed", 100
            TASKS[task_id]["error"] = str(exc)
    asyncio.run(execute())


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": MAP_CLIENT.mode, "real_api_available": MAP_CLIENT.real_available}


@app.get("/api/map/status")
def map_status():
    return {"mode": MAP_CLIENT.mode, "real_api_available": MAP_CLIENT.real_available, "mock_available": True, "snapshot_available": LOCAL_SNAPSHOT is not None, "message": "已启用百度地图 Web 服务" if MAP_CLIENT.real_available else "当前使用本地百度数据快照，不消耗 API 额度"}

@app.get("/api/map/config")
def map_config():
    # 浏览器端 AK 与服务器端 Web 服务 AK 分离，避免把后端凭据下发到浏览器。
    browser_ak = os.getenv("VITE_BAIDU_MAP_AK", "").strip()
    return {"mode": MAP_CLIENT.mode, "browser_ak": browser_ak if browser_ak else ""}


@app.get("/api/geocode")
async def geocode(address: str, city: str = "广州"):
    if not MAP_CLIENT.real_available:
        center = (LOCAL_SNAPSHOT or {}).get("center") or CENTER
        return {"source": "local_snapshot", "result": {"location": {"lng": center["lng"], "lat": center["lat"]}, "formatted_address": center["address"]}}
    try:
        return {"source": "baidu", "result": await MAP_CLIENT.geocode(address, city)}
    except BaiduMapError as exc:
        raise HTTPException(status_code=502, detail=f"百度地图地理编码失败：{exc}") from exc


@app.get("/api/pois")
async def pois(query: str, lng: float = CENTER["lng"], lat: float = CENTER["lat"], radius: int = 1000):
    if not MAP_CLIENT.real_available:
        snapshot_pois = (LOCAL_SNAPSHOT or {}).get("pois") or POIS
        return {"source": "local_snapshot", "results": [item for item in snapshot_pois if query in item["name"] or query in CATEGORIES[item["category"]]["label"]]}
    try:
        return {"source": "baidu", "results": await MAP_CLIENT.search_poi(query, lng, lat, radius)}
    except BaiduMapError as exc:
        raise HTTPException(status_code=502, detail=f"百度地图地点检索失败：{exc}") from exc


@app.get("/api/demo/default")
def default_demo():
    return {"center": CENTER, "categories": CATEGORIES}


@app.post("/api/analyze")
def create_analysis(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    TASKS[task_id] = {"id": task_id, "status": "queued", "progress": 12, "created_at": now(), "result": None}
    background_tasks.add_task(run_task, task_id, request)
    return TASKS[task_id]


@app.get("/api/analyze/{task_id}")
def get_analysis(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="体检任务不存在")
    return task


@app.get("/api/report/{task_id}")
def get_report(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="体检任务不存在")
    if task.get("status") == "failed":
        raise HTTPException(status_code=502, detail=task.get("error", "百度地图分析失败"))
    if task.get("status") != "completed":
        raise HTTPException(status_code=404, detail="体检报告尚未生成")
    return task["result"]
