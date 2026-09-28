from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

CSV_COLUMNS = [
    "记录类型",
    "报告标识",
    "生成时间",
    "分析地点",
    "中心经度(BD-09)",
    "中心纬度(BD-09)",
    "坐标系",
    "步行阈值(分钟)",
    "分析模式",
    "已选设施类别",
    "报告完整性",
    "数据质量状态",
    "数据质量说明",
    "数据来源说明",
    "指标名称",
    "指标值",
    "设施类别",
    "类别名称",
    "类别评分",
    "评分状态",
    "评分说明",
    "类别设施数量",
    "类别最近步行时间(分钟)",
    "数量得分",
    "最近步行时间得分",
    "空间分布得分",
    "是否计入综合分",
    "设施标识",
    "设施名称",
    "设施规范名称",
    "设施语义类型",
    "设施别名",
    "合并原始记录数",
    "设施经度(BD-09)",
    "设施纬度(BD-09)",
    "步行时间(分钟)",
    "步行距离(米)",
    "数据来源",
    "计算方法",
]


@dataclass(frozen=True)
class ExportArtifact:
    content: bytes
    media_type: str
    filename: str

    @property
    def content_disposition(self) -> str:
        ascii_name = _ascii_fallback_filename(self.filename)
        return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(self.filename)}"


def build_json_export(report: dict[str, Any]) -> ExportArtifact:
    """完整导出持久化的标准报告，不在导出阶段重算或删减字段。"""

    return ExportArtifact(
        content=json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"),
        media_type="application/json",
        filename=_filename(report, "json"),
    )


def build_csv_export(report: dict[str, Any]) -> ExportArtifact:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    common = _csv_common_fields(report)
    category_labels = {score.get("category"): score.get("label") for score in report.get("category_scores", [])}

    summary_labels = {
        "score": "综合生活圈指数",
        "area_sqm": "可达面积(平方米)",
        "poi_count": "设施总数",
        "critical_zone_count": "重点服务盲区数",
        "sparse_zone_count": "设施稀疏区数",
    }
    for key, label in summary_labels.items():
        writer.writerow({**common, "记录类型": "汇总", "指标名称": label, "指标值": report.get("summary", {}).get(key)})

    for score in report.get("category_scores", []):
        components = {item.get("key"): item.get("score") for item in score.get("components", [])}
        writer.writerow(
            {
                **common,
                "记录类型": "类别评分",
                "设施类别": score.get("category"),
                "类别名称": score.get("label"),
                "类别评分": score.get("score"),
                "评分状态": score.get("status_label"),
                "评分说明": score.get("status_explanation"),
                "类别设施数量": score.get("count"),
                "类别最近步行时间(分钟)": score.get("nearest_walk_minutes"),
                "数量得分": components.get("quantity"),
                "最近步行时间得分": components.get("walking_time"),
                "空间分布得分": components.get("spatial_distribution"),
                "是否计入综合分": "是" if score.get("valid_for_overall") else "否",
            }
        )

    for facility in report.get("facilities", report.get("pois", [])):
        writer.writerow(
            {
                **common,
                "记录类型": "设施明细",
                "设施类别": facility.get("category"),
                "类别名称": (
                    facility.get("category_label")
                    or facility.get("label")
                    or category_labels.get(facility.get("category"))
                ),
                "设施标识": facility.get("id"),
                "设施名称": facility.get("name"),
                "设施规范名称": facility.get("canonical_name"),
                "设施语义类型": facility.get("semantic_type_label") or facility.get("semantic_type"),
                "设施别名": "、".join((facility.get("normalization") or {}).get("aliases") or []),
                "合并原始记录数": (facility.get("normalization") or {}).get("source_record_count"),
                "设施经度(BD-09)": facility.get("lng"),
                "设施纬度(BD-09)": facility.get("lat"),
                "步行时间(分钟)": facility.get("walk_minutes"),
                "步行距离(米)": facility.get("walk_distance_m"),
                "数据来源": facility.get("source"),
                "计算方法": facility.get("calculation_method"),
            }
        )

    # BOM 让 Excel 等常见表格软件能够直接按 UTF-8 正确识别中文列名。
    content = ("\ufeff" + output.getvalue()).encode("utf-8")
    return ExportArtifact(content=content, media_type="text/csv; charset=utf-8", filename=_filename(report, "csv"))


def build_geojson_export(report: dict[str, Any]) -> ExportArtifact:
    features: list[dict[str, Any]] = []
    isochrone = report.get("isochrone")
    if isochrone:
        features.append(_spatial_feature(isochrone, "isochrone", report))

    service_areas = report.get("service_areas") or report.get("zones") or {}
    for feature in service_areas.get("features", []):
        features.append(_spatial_feature(feature, "service_area", report))

    for recommendation in report.get("recommendations", []):
        for candidate in recommendation.get("candidate_locations", []):
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "layer": "planning_candidate",
                        "report_id": report["report_id"],
                        "generated_at": report["completed_at"],
                        "coordinate_system": "BD-09",
                        "recommendation_id": recommendation.get("id"),
                        "recommendation_title": recommendation.get("title"),
                        **deepcopy(candidate),
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [candidate["lng"], candidate["lat"]],
                    },
                }
            )

    collection = {
        "type": "FeatureCollection",
        "report_id": report["report_id"],
        "generated_at": report["completed_at"],
        "coordinate_system": "BD-09",
        "parameters": deepcopy(report.get("request") or report.get("parameters") or {}),
        "analysis_center": deepcopy(report.get("analysis_center") or report.get("center") or {}),
        "data_quality": deepcopy(report.get("data_quality") or {}),
        "features": features,
    }
    return ExportArtifact(
        content=json.dumps(collection, ensure_ascii=False, indent=2).encode("utf-8"),
        media_type="application/geo+json",
        filename=_filename(report, "geojson"),
    )


def _spatial_feature(feature: dict[str, Any], layer: str, report: dict[str, Any]) -> dict[str, Any]:
    exported = deepcopy(feature)
    exported["properties"] = {
        **exported.get("properties", {}),
        "layer": layer,
        "report_id": report["report_id"],
        "generated_at": report["completed_at"],
        "coordinate_system": "BD-09",
    }
    return exported


def _csv_common_fields(report: dict[str, Any]) -> dict[str, Any]:
    request = report.get("request") or report.get("parameters") or {}
    center = report.get("analysis_center") or report.get("center") or {}
    quality = report.get("data_quality") or {}
    source_labels = [source.get("label") or source.get("kind") for source in quality.get("sources", [])]
    return {
        "报告标识": report.get("report_id"),
        "生成时间": report.get("completed_at"),
        "分析地点": center.get("address"),
        "中心经度(BD-09)": center.get("lng"),
        "中心纬度(BD-09)": center.get("lat"),
        "坐标系": "BD-09",
        "步行阈值(分钟)": request.get("minutes"),
        "分析模式": request.get("mode"),
        "已选设施类别": "、".join(request.get("categories") or []),
        "报告完整性": report.get("completeness"),
        "数据质量状态": quality.get("overall_status"),
        "数据质量说明": quality.get("summary"),
        "数据来源说明": "、".join(label for label in source_labels if label),
    }


def _filename(report: dict[str, Any], extension: str) -> str:
    center = report.get("analysis_center") or report.get("center") or {}
    address = _safe_filename_part(center.get("address") or "分析报告", 24)
    date = _date_part(report.get("completed_at"))
    report_id = _safe_filename_part(str(report.get("report_id") or "unknown")[:8], 8)
    return f"生活圈体检-{address}-{date}-{report_id}.{extension}"


def _safe_filename_part(value: str, maximum_length: int) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", normalized, flags=re.UNICODE)
    safe = re.sub(r"-+", "-", safe).strip("-._")
    return (safe or "未命名")[:maximum_length].rstrip("-._")


def _date_part(value: Any) -> str:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y%m%d")
        except ValueError:
            pass
    return "未知日期"


def _ascii_fallback_filename(filename: str) -> str:
    extension = filename.rsplit(".", 1)[-1]
    match = re.search(r"-(\d{8})-([\w-]+)\.[^.]+$", filename)
    suffix = f"-{match.group(1)}-{match.group(2)}" if match else ""
    return f"life-circle-report{suffix}.{extension}"
