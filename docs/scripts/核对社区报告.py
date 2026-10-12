#!/usr/bin/env python3
"""离线复算归档社区报告；仅使用标准库，不请求地图 API，也不写入文件。"""

from collections import Counter
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP_DOCS = ROOT / "life-circle-assistant" / "docs"
REPORTS = APP_DOCS / "validation" / "reports"
FILES = {
    "沙涌冷测": REPORTS / "v2.3.0-20261012/f4760b29-cf45-42d6-add2-db9457cce691.json",
    "沙涌热测": REPORTS / "v2.3.0-20261012/46990b2c-0ee2-4eda-a985-b5eea99f5516.json",
    "沙涌历史": REPORTS / "shachong-changsheng-20261004.json",
    "红山历史": REPORTS / "hongshan-haiyundonglu-20260921.json",
}
BUSINESS_FIELDS = (
    "summary", "isochrone", "scoring", "category_scores", "facilities",
    "facility_normalization", "service_areas", "recommendations",
)


def canonical(value):
    # 仅忽略已明确会随缓存变化的来源/计算方法；其他差异都保留。
    if isinstance(value, dict):
        return {
            key: canonical(item)
            for key, item in value.items()
            if key not in {"source", "calculation_method"}
        }
    if isinstance(value, list):
        return [canonical(item) for item in value]
    return value


def grids(report):
    return {
        feature["properties"]["grid_id"]: feature["properties"]
        for feature in report["service_areas"]["features"]
    }


def route_comparison(report, facility_name):
    facility = next(item for item in report["facilities"] if item["name"] == facility_name)
    center = report["center"]
    dx = (facility["lng"] - center["lng"]) * 111320 * math.cos(
        math.radians((facility["lat"] + center["lat"]) / 2)
    )
    dy = (facility["lat"] - center["lat"]) * 111320
    straight_m = math.hypot(dx, dy)
    return {
        "报告编号": report["report_id"],
        "名称": facility_name,
        "设施编号": facility["id"],
        "终点BD09": [facility["lng"], facility["lat"]],
        "局部直线距离米": round(straight_m),
        "直线估算分钟_假定75米每分钟": round(straight_m / 75, 2),
        "路网距离米": facility["walk_distance_m"],
        "路网预测分钟": facility["walk_minutes"],
        "绕行系数": round(facility["walk_distance_m"] / straight_m, 2),
        "现场实走分钟": None,
    }


def main():
    reports = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in FILES.items()}
    cold, warm, old, hongshan = (reports[name] for name in FILES)
    comparisons = {
        field: canonical(cold[field]) == canonical(warm[field])
        for field in BUSINESS_FIELDS
    }
    if not all(comparisons.values()):
        raise SystemExit("冷/热业务字段出现差异，请重新核对文档结论。")
    old_grids, current_grids = grids(old), grids(cold)
    changed = [
        {
            "网格": grid_id,
            "历史类别": previous["kind"],
            "当前类别": current_grids[grid_id]["kind"],
            "历史分钟": previous["nearest_walk_minutes"],
            "当前分钟": current_grids[grid_id]["nearest_walk_minutes"],
            "历史距离米": previous["nearest_walk_distance_m"],
            "当前距离米": current_grids[grid_id]["nearest_walk_distance_m"],
        }
        for grid_id, previous in old_grids.items()
        if previous["kind"] != current_grids[grid_id]["kind"]
    ]
    benchmark_path = APP_DOCS / "validation/benchmarks/shachong-changsheng-20261004.json"
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    labels = benchmark["labels"]
    agreement = {
        name: {
            "相同": sum(grids(report)[label["grid_id"]]["kind"] == label["expected_kind"] for label in labels),
            "总数": len(labels),
            "口径": "与2026-10-04同源历史标注的一致数量，不是独立准确率",
        }
        for name, report in [("历史报告", old), ("当前报告", cold)]
    }
    summaries = {}
    for name, report in reports.items():
        category_counts = {}
        for props in grids(report).values():
            counter = category_counts.setdefault(props["category"], Counter())
            counter[props["kind"]] += 1
        summaries[name] = {
            "文件": str(FILES[name].relative_to(ROOT)),
            "文件SHA256": hashlib.sha256(FILES[name].read_bytes()).hexdigest(),
            "报告编号": report["report_id"],
            "计算模式": report["calculation_mode"],
            "汇总": report["summary"],
            "归一化": {
                key: report["facility_normalization"][key]
                for key in ["input_count", "output_count", "merged_count"]
            },
            "分类数量": dict(Counter(props["kind"] for props in grids(report).values())),
            "分类别网格数量": category_counts,
            "分类别覆盖": [
                {key: item[key] for key in ["category", "count", "nearest_walk_minutes", "score"]}
                for item in report["categories"]
            ],
            "耗时毫秒": report["execution"]["total_duration_ms"],
            "应用调用计数": report["execution"]["api_calls"],
            "缓存": report["execution"]["cache"],
            "步行最终失败数": report["execution"]["metrics"]["walking_failures"],
        }
    cold_ms = cold["execution"]["total_duration_ms"]
    warm_ms = warm["execution"]["total_duration_ms"]
    output = {
        "说明": "归档真实地图数据的离线复算；没有新API请求或现场实走。",
        "报告汇总": summaries,
        "忽略来源及计算方法后冷热业务一致": comparisons,
        "冷测耗时除以热测耗时": round(cold_ms / warm_ms, 2),
        "热测耗时减少百分比": round((1 - warm_ms / cold_ms) * 100, 2),
        "应用调用计数减少百分比": round((1 - warm["execution"]["api_calls"] / cold["execution"]["api_calls"]) * 100, 2),
        "历史与当前网格差异": changed,
        "同源历史标注对比": agreement,
        "代表路线_定向选例不代表随机样本": [
            route_comparison(cold, name)
            for name in ["沙步农贸批发市场", "广州市黄埔区新港小学(西校区)", "领好超市(沙步店)"]
        ] + [
            route_comparison(hongshan, name)
            for name in ["石化小学", "大参林(护林路店)", "冯明润中医诊所"]
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
