from __future__ import annotations

import shutil
import struct
import subprocess
from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.exports import build_pdf_export
from app.main import create_app


def _standard_report(task_id: str = "task-pdf-001") -> dict:
    center = {"lng": 113.4872, "lat": 23.1068, "address": "广州市黄埔区萝岗街道样例社区"}
    request = {
        "lng": center["lng"],
        "lat": center["lat"],
        "minutes": 15,
        "mode": "analysis",
        "categories": ["market", "school"],
        "center_address": center["address"],
        "center_selection_method": "default",
    }
    isochrone_ring = [
        [113.4765, 23.1068],
        [113.4810, 23.0970],
        [113.4930, 23.0980],
        [113.4980, 23.1068],
        [113.4930, 23.1160],
        [113.4810, 23.1160],
        [113.4765, 23.1068],
    ]
    critical_ring = [
        [113.4765, 23.0970],
        [113.4820, 23.0970],
        [113.4820, 23.1020],
        [113.4765, 23.1020],
        [113.4765, 23.0970],
    ]
    sparse_ring = [
        [113.4820, 23.1020],
        [113.4872, 23.1020],
        [113.4872, 23.1068],
        [113.4820, 23.1068],
        [113.4820, 23.1020],
    ]
    category_scores = [
        {
            "category": "market",
            "label": "菜市场",
            "count": 2,
            "nearest_walk_minutes": 6.0,
            "score": 66,
            "status": "valid",
            "status_label": "数据有效",
            "status_explanation": "设施数量、最近步行时间和空间分布均可核验。",
            "valid_for_overall": True,
            "applied_weight": 0.5,
            "components": [
                {"key": "quantity", "score": 70},
                {"key": "walking_time", "score": 70},
                {"key": "spatial_distribution", "score": 50},
            ],
        },
        {
            "category": "school",
            "label": "小学",
            "count": 2,
            "nearest_walk_minutes": 8.0,
            "score": 62,
            "status": "valid",
            "status_label": "数据有效",
            "status_explanation": "设施数量、最近步行时间和空间分布均可核验。",
            "valid_for_overall": True,
            "applied_weight": 0.5,
            "components": [
                {"key": "quantity", "score": 70},
                {"key": "walking_time", "score": 60},
                {"key": "spatial_distribution", "score": 50},
            ],
        },
    ]
    service_areas = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "grid_id": "school-r1c1",
                    "region_type": "critical",
                    "category": "school",
                    "category_label": "小学",
                    "nearest_facility_name": "香雪小学",
                    "nearest_walk_minutes": 15.5,
                    "nearest_walk_distance_m": 1166,
                    "basis": "最近同类设施步行15.5分钟，超过15分钟阈值，且周边1000米内无同类设施。",
                },
                "geometry": {"type": "Polygon", "coordinates": [critical_ring]},
            },
            {
                "type": "Feature",
                "properties": {
                    "grid_id": "market-r2c2",
                    "region_type": "sparse",
                    "category": "market",
                    "category_label": "菜市场",
                },
                "geometry": {"type": "Polygon", "coordinates": [sparse_ring]},
            },
        ],
    }
    return {
        "schema_version": "2.0",
        "id": "report-pdf-001",
        "report_id": "report-pdf-001",
        "task_id": task_id,
        "status": "completed",
        "completeness": "partial",
        "created_at": "2026-09-20T08:00:00+00:00",
        "completed_at": "2026-09-20T08:01:12+00:00",
        "parameters": request,
        "request": request,
        "center": center,
        "analysis_center": center,
        "calculation_mode": {
            "requested_mode": "analysis",
            "provider_mode": "snapshot",
            "coordinate_system": "BD-09",
            "walking_method": "provider_walking_matrix",
        },
        "execution": {
            "total_duration_ms": 72311,
            "metrics": {
                "walking_provider_calls": 99,
                "walking_api_calls": 0,
                "walking_cache_hits": 12,
                "walking_cache_misses": 87,
                "walking_retries": 2,
                "walking_timeouts": 1,
                "walking_failures": 1,
                "walking_degraded_results": 18,
                "partial_failure_count": 1,
            },
        },
        "data_quality": {
            "overall_status": "partial",
            "summary": "当前结果包含本地快照、缓存和降级估算，且小学存在一项步行结果超时。",
            "sources": [
                {
                    "kind": "local_snapshot",
                    "provider": "huangpu-local-snapshot",
                    "label": "黄埔区本地百度数据快照",
                    "usage": "设施发现和基础路线",
                    "is_latest_real_measurement": False,
                },
                {
                    "kind": "cache",
                    "provider": "walking-cache",
                    "label": "有效缓存",
                    "usage": "12 个坐标对",
                    "is_latest_real_measurement": False,
                },
                {
                    "kind": "degraded_estimate",
                    "provider": "walking-service",
                    "label": "降级估算",
                    "usage": "18 个坐标对",
                    "is_latest_real_measurement": False,
                },
            ],
            "events": [
                {
                    "code": "snapshot_used",
                    "severity": "warning",
                    "scope": "task",
                    "category": None,
                    "source": "local_snapshot",
                    "method": "provider",
                    "message": "当前使用本地快照完成离线演示，不代表最新真实地图测算。",
                },
                *[
                    {
                        "code": "walking_estimate_used",
                        "severity": "warning",
                        "scope": "coordinate_pair",
                        "category": "school",
                        "source": "degraded_estimate",
                        "method": "straight_line_walking_estimate",
                        "message": "该坐标对使用降级步行估算，不代表真实 API 测算。",
                    }
                    for _ in range(18)
                ],
            ],
            "partial_failures": [
                {
                    "category": "school",
                    "code": "walk_timeout",
                    "object_ref": "school-r1c1",
                    "message": "一个小学网格的真实步行请求超时，已在分类时明确标记。",
                }
            ],
        },
        "isochrone": {
            "type": "Feature",
            "properties": {
                "minutes": 15,
                "mode": "analysis",
                "area_sqm": 3715469,
                "sample_count": 24,
                "successful_sample_count": 23,
                "source": "local_snapshot",
            },
            "geometry": {"type": "Polygon", "coordinates": [isochrone_ring]},
        },
        "facilities": [
            {"id": "m-01", "name": "萝岗市场", "category": "market", "lng": 113.4891, "lat": 23.1085},
            {"id": "s-01", "name": "黄埔区萝岗小学", "category": "school", "lng": 113.4904, "lat": 23.1078},
        ],
        "pois": [],
        "zones": service_areas,
        "service_areas": service_areas,
        "summary": {
            "score": 64,
            "area_sqm": 3715469,
            "poi_count": 4,
            "critical_zone_count": 1,
            "sparse_zone_count": 1,
        },
        "categories": category_scores,
        "category_scores": category_scores,
        "scoring": {"score": 64, "explanation": "综合分按 2 个有效已选类别的实际权重计算。"},
        "recommendation_summary": {
            "status": "needs_action",
            "message": "发现 1 类服务短板，建议优先改善小学。",
        },
        "recommendations": [
            {
                "id": "recommendation-school-critical",
                "category": "school",
                "category_label": "小学",
                "priority": "中",
                "title": "补充小学服务点",
                "body": "类别评分为 62 分，共识别 1 个重点服务盲区。",
                "problem_basis": "重点盲区 school-r1c1 超过 15 分钟步行阈值。",
                "target_region_ids": ["school-r1c1"],
                "target_improvement": {"description": "预计减少 1 个重点服务盲区，改善约 250,013 平方米。"},
                "candidate_locations": [
                    {
                        "id": "candidate-school-1",
                        "lng": 113.479875,
                        "lat": 23.1000627,
                        "reason": "候选点位于重点服务盲区内，实际效果需在规划模拟中复算。",
                    }
                ],
            }
        ],
    }


def _extract_text(content: bytes) -> tuple[PdfReader, str]:
    reader = PdfReader(BytesIO(content))
    return reader, "\n".join(page.extract_text() or "" for page in reader.pages)


def test_pdf_export_contains_required_sections_and_expected_page_range():
    artifact = build_pdf_export(_standard_report())
    reader, text = _extract_text(artifact.content)

    assert artifact.media_type == "application/pdf"
    assert artifact.filename.endswith(".pdf")
    assert artifact.content.startswith(b"%PDF-")
    assert 6 <= len(reader.pages) <= 10
    for expected in (
        "15分钟生活圈体检报告",
        "广州市黄埔区萝岗街道样例社区",
        "分析范围与空间摘要",
        "评分与核心指标",
        "重点服务盲区",
        "补充小学服务点",
        "数据质量与方法披露",
        "有效缓存",
        "降级估算",
        "walk_timeout",
    ):
        assert expected in text


def test_pdf_export_endpoint_reads_persisted_report(tmp_path):
    app = create_app(database_path=tmp_path / "pdf-export.db")
    task = app.state.task_repository.create(_standard_report()["request"])
    report = _standard_report(task["id"])
    app.state.report_repository.save_for_task(task["id"], report)
    client = TestClient(app)

    response = client.get(f"/api/reports/{report['report_id']}/exports/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["x-report-id"] == report["report_id"]
    assert response.headers["x-coordinate-system"] == "BD-09"
    assert ".pdf" in response.headers["content-disposition"]
    reader, text = _extract_text(response.content)
    assert len(reader.pages) >= 6
    assert report["report_id"] in text


def test_pdf_main_pages_render_to_legible_pngs(tmp_path):
    pdftoppm = shutil.which("pdftoppm")
    assert pdftoppm, "PDF 渲染验收需要安装 Poppler 的 pdftoppm"
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(build_pdf_export(_standard_report()).content)
    prefix = tmp_path / "page"

    subprocess.run(
        [pdftoppm, "-f", "1", "-l", "6", "-r", "96", "-png", str(pdf_path), str(prefix)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )

    rendered = sorted(tmp_path.glob("page-*.png"))
    assert len(rendered) == 6
    for image_path in rendered:
        data = image_path.read_bytes()
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", data[16:24])
        assert width >= 790
        assert height >= 1100
        assert len(data) >= 20_000
