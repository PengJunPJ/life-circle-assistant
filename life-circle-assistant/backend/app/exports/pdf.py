from __future__ import annotations

import io
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..contracts.sources import source_label

from .structured import ExportArtifact, _filename


PAGE_WIDTH, PAGE_HEIGHT = A4
FONT_NAME = "LifeCircleChinese"
FONT_BOLD_NAME = "LifeCircleChineseBold"

INK = colors.HexColor("#173D36")
MUTED = colors.HexColor("#60766F")
GREEN = colors.HexColor("#2F7D68")
GREEN_LIGHT = colors.HexColor("#E7F2EE")
AMBER = colors.HexColor("#D99732")
AMBER_LIGHT = colors.HexColor("#FFF3DC")
RED = colors.HexColor("#C64F45")
RED_LIGHT = colors.HexColor("#FCE8E5")
BLUE = colors.HexColor("#3977A8")
LINE = colors.HexColor("#D9E2DE")
PAPER = colors.HexColor("#F7F9F8")


def build_pdf_export(report: dict[str, Any]) -> ExportArtifact:
    """基于持久化标准报告生成可分享的中文 PDF，不重新计算分析结果。"""

    font_name, bold_font_name = _register_chinese_fonts()
    styles = _build_styles(font_name, bold_font_name)
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        title="15分钟生活圈体检报告",
        author="15分钟生活圈智能体检与规划助手",
        subject="可信、可解释的生活圈分析",
    )
    story = _build_story(report, styles)
    document.build(
        story,
        onFirstPage=lambda canvas, doc: _draw_page(canvas, doc, report, font_name),
        onLaterPages=lambda canvas, doc: _draw_page(canvas, doc, report, font_name),
    )
    return ExportArtifact(
        content=output.getvalue(),
        media_type="application/pdf",
        filename=_filename(report, "pdf"),
    )


def _register_chinese_fonts() -> tuple[str, str]:
    if FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return FONT_NAME, FONT_BOLD_NAME

    configured = os.getenv("LIFE_CIRCLE_PDF_FONT_PATH", "").strip()
    candidates = [
        configured,
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "C:/Windows/Fonts/msyh.ttc",
    ]
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, candidate, subfontIndex=0))
            pdfmetrics.registerFont(TTFont(FONT_BOLD_NAME, candidate, subfontIndex=0))
            return FONT_NAME, FONT_BOLD_NAME
        except Exception:
            continue

    # ReportLab 的 CID 字体作为最后保障，确保无额外字体文件时仍可生成中文报告。
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light", "STSong-Light"


def _build_styles(font_name: str, bold_font_name: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "CoverTitle",
            parent=base["Title"],
            fontName=bold_font_name,
            fontSize=25,
            leading=34,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=8 * mm,
        ),
        "cover_subtitle": ParagraphStyle(
            "CoverSubtitle",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=11,
            leading=18,
            textColor=MUTED,
            spaceAfter=8 * mm,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=base["Heading1"],
            fontName=bold_font_name,
            fontSize=17,
            leading=24,
            textColor=INK,
            spaceAfter=5 * mm,
        ),
        "subsection": ParagraphStyle(
            "Subsection",
            parent=base["Heading2"],
            fontName=bold_font_name,
            fontSize=11,
            leading=17,
            textColor=INK,
            spaceBefore=3 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=9,
            leading=15,
            textColor=INK,
            wordWrap="CJK",
            spaceAfter=2 * mm,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=7.5,
            leading=12,
            textColor=MUTED,
            wordWrap="CJK",
        ),
        "table": ParagraphStyle(
            "Table",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=7.3,
            leading=11,
            textColor=INK,
            wordWrap="CJK",
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["BodyText"],
            fontName=bold_font_name,
            fontSize=7.3,
            leading=11,
            textColor=colors.white,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
        "metric": ParagraphStyle(
            "Metric",
            parent=base["BodyText"],
            fontName=bold_font_name,
            fontSize=16,
            leading=21,
            textColor=INK,
            alignment=TA_CENTER,
        ),
        "metric_label": ParagraphStyle(
            "MetricLabel",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=7.2,
            leading=10,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
    }


def _build_story(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    request = report.get("request") or report.get("parameters") or {}
    center = report.get("analysis_center") or report.get("center") or {}
    quality = report.get("data_quality") or {}
    story: list[Flowable] = []

    story.extend(
        [
            Spacer(1, 18 * mm),
            Paragraph("15分钟生活圈体检报告", styles["cover_title"]),
            Paragraph(
                "可信、可解释的社区服务可达性分析 - 报告中的评分、盲区和建议均来自同一份持久化标准报告。",
                styles["cover_subtitle"],
            ),
            _status_banner(report, styles),
            Spacer(1, 8 * mm),
            _parameter_table(report, styles),
            Spacer(1, 6 * mm),
            Paragraph("核心结论", styles["subsection"]),
            _metric_table(report, styles),
            Spacer(1, 5 * mm),
            Paragraph(_executive_summary(report), styles["body"]),
            Paragraph(
                f"数据质量结论：{_escape(quality.get('summary') or '未提供数据质量说明。')}",
                styles["body"],
            ),
            PageBreak(),
            Paragraph("分析范围与空间摘要", styles["section"]),
            Paragraph(
                f"分析中心：{_escape(center.get('address') or '未命名分析中心')}；坐标系：BD-09；"
                f"步行阈值：{request.get('minutes', '-')} 分钟。地图为基于报告 GeoJSON 的矢量摘要，不含商业底图。",
                styles["body"],
            ),
            ReportMap(report, 174 * mm, 112 * mm, styles["small"]),
            Spacer(1, 4 * mm),
            _map_legend(styles),
            Spacer(1, 5 * mm),
            Paragraph("空间图层说明", styles["subsection"]),
            _isochrone_table(report, styles),
            PageBreak(),
            Paragraph("评分与核心指标", styles["section"]),
            Paragraph(_scoring_explanation(report), styles["body"]),
            _score_table(report, styles),
            Spacer(1, 5 * mm),
            Paragraph("评分规则", styles["subsection"]),
            Paragraph(
                "每类设施评分由设施数量 40%、最近步行时间 40%、空间分布 20% 组成。综合分只纳入有效的已选类别，并按实际采用权重归一化。",
                styles["body"],
            ),
            PageBreak(),
            Paragraph("重点服务盲区", styles["section"]),
            Paragraph(_blind_spot_summary(report), styles["body"]),
            _blind_spot_table(report, styles),
            PageBreak(),
            Paragraph("规划建议", styles["section"]),
            Paragraph(
                _escape((report.get("recommendation_summary") or {}).get("message") or "当前没有规划建议。"),
                styles["body"],
            ),
        ]
    )
    story.extend(_recommendation_flows(report, styles))
    story.extend(
        [
            PageBreak(),
            Paragraph("数据质量与方法披露", styles["section"]),
            Paragraph(
                "本节完整披露本报告使用的数据来源、计算方式、重复事件数量、部分失败、缓存和降级估算。"
                "同类重复事件按代码和方法汇总，数量保持可核验。",
                styles["body"],
            ),
            _quality_overview_table(report, styles),
            Spacer(1, 4 * mm),
            Paragraph("数据来源", styles["subsection"]),
            _source_table(report, styles),
            Spacer(1, 4 * mm),
            Paragraph("质量事件汇总", styles["subsection"]),
            _quality_event_table(report, styles),
            Spacer(1, 4 * mm),
            Paragraph("部分失败", styles["subsection"]),
            _partial_failure_table(report, styles),
            Spacer(1, 4 * mm),
            Paragraph("执行与缓存指标", styles["subsection"]),
            _execution_table(report, styles),
            Spacer(1, 5 * mm),
            Paragraph(
                "使用限制：本报告用于社区服务可达性辅助研判，不替代现场踏勘、最新地图核验、人口需求分析、用地审批或最终公共政策决策。",
                styles["small"],
            ),
        ]
    )
    return story


def _status_banner(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    complete = report.get("completeness") == "complete"
    quality = report.get("data_quality") or {}
    cells = [
        Paragraph("报告完整性", styles["small"]),
        Paragraph("完整结果" if complete else "部分结果", styles["body"]),
        Paragraph("数据质量", styles["small"]),
        Paragraph(_quality_status_label(quality.get("overall_status")), styles["body"]),
    ]
    table = Table([cells], colWidths=[28 * mm, 50 * mm, 28 * mm, 50 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), GREEN_LIGHT if complete else AMBER_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.6, GREEN if complete else AMBER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _parameter_table(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    request = report.get("request") or report.get("parameters") or {}
    center = report.get("analysis_center") or report.get("center") or {}
    category_labels = _category_labels(report)
    rows = [
        ["分析中心", center.get("address") or "未命名分析中心"],
        ["中心坐标", f"{_number(center.get('lng'), 6)}, {_number(center.get('lat'), 6)} (BD-09)"],
        ["生成时间", _format_datetime(report.get("completed_at"))],
        ["步行阈值", f"{request.get('minutes', '-')} 分钟"],
        ["分析模式", _mode_label(request.get("mode"))],
        ["设施类别", "、".join(category_labels.get(item, item) for item in request.get("categories", [])) or "未指定"],
        ["报告标识", report.get("report_id") or report.get("id") or "-"],
    ]
    return _key_value_table(rows, styles)


def _metric_table(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    summary = report.get("summary") or {}
    score = summary.get("score")
    values = [
        ("-" if score is None else str(score), "综合生活圈指数"),
        (_format_integer(summary.get("poi_count")), "设施点位"),
        (_format_integer(summary.get("critical_zone_count")), "重点盲区"),
        (_format_integer(summary.get("sparse_zone_count")), "设施稀疏区"),
        (_format_area(summary.get("area_sqm")), "可达面积"),
    ]
    data = [[Paragraph(value, styles["metric"]) for value, _ in values], [Paragraph(label, styles["metric_label"]) for _, label in values]]
    table = Table(data, colWidths=[31.2 * mm] * 5)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("TOPPADDING", (0, 0), (-1, 0), 7),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
            ]
        )
    )
    return table


def _isochrone_table(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    properties = (report.get("isochrone") or {}).get("properties") or {}
    rows = [
        ["步行阈值", f"{properties.get('minutes', '-')} 分钟"],
        ["采样模式", _mode_label(properties.get("mode"))],
        ["采样数量", f"{properties.get('successful_sample_count', 0)} / {properties.get('sample_count', 0)} 成功"],
        ["边界来源", _source_label(properties.get("source"))],
        ["可达面积", _format_area(properties.get("area_sqm"))],
    ]
    return _key_value_table(rows, styles)


def _score_table(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    headers = ["设施类别", "类别评分", "设施数量", "最近步行", "数量 40%", "步行 40%", "分布 20%", "综合权重"]
    rows: list[list[Any]] = [[Paragraph(item, styles["table_header"]) for item in headers]]
    for score in report.get("category_scores", report.get("categories", [])):
        components = {item.get("key"): item for item in score.get("components", [])}
        rows.append(
            [
                _cell(score.get("label") or score.get("category"), styles),
                _cell(score.get("score") if score.get("score") is not None else "无效", styles),
                _cell(score.get("count", 0), styles),
                _cell(_minutes(score.get("nearest_walk_minutes")), styles),
                _cell(_component_score(components, "quantity"), styles),
                _cell(_component_score(components, "walking_time"), styles),
                _cell(_component_score(components, "spatial_distribution"), styles),
                _cell(_percent(score.get("applied_weight")), styles),
            ]
        )
        rows.append([_cell(f"状态：{score.get('status_label') or score.get('status') or '-'}。{score.get('status_explanation') or ''}", styles)] + [""] * 7)
    table = Table(rows, colWidths=[23 * mm, 18 * mm, 18 * mm, 20 * mm, 20 * mm, 20 * mm, 20 * mm, 20 * mm], repeatRows=1)
    commands = _table_commands()
    for row_index in range(2, len(rows), 2):
        commands.extend(
            [
                ("SPAN", (0, row_index), (-1, row_index)),
                ("BACKGROUND", (0, row_index), (-1, row_index), PAPER),
                ("ALIGN", (0, row_index), (-1, row_index), "LEFT"),
            ]
        )
    table.setStyle(TableStyle(commands))
    return table


def _blind_spot_table(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Flowable:
    spots = [
        feature.get("properties") or {}
        for feature in (report.get("service_areas") or report.get("zones") or {}).get("features", [])
        if (feature.get("properties") or {}).get("region_type", (feature.get("properties") or {}).get("kind")) == "critical"
    ]
    if not spots:
        return Paragraph("未识别到重点服务盲区。", styles["body"])
    rows: list[list[Any]] = [[_header_cell(item, styles) for item in ["区域", "设施类别", "最近同类设施", "步行时间/距离", "判定依据"]]]
    for spot in spots:
        rows.append(
            [
                _cell(spot.get("grid_id") or "-", styles),
                _cell(spot.get("category_label") or spot.get("category") or "-", styles),
                _cell(spot.get("nearest_facility_name") or "未找到", styles),
                _cell(f"{_minutes(spot.get('nearest_walk_minutes'))} / {_meters(spot.get('nearest_walk_distance_m'))}", styles),
                _cell(spot.get("basis") or "未提供判定依据", styles),
            ]
        )
    table = Table(rows, colWidths=[24 * mm, 22 * mm, 31 * mm, 27 * mm, 53 * mm], repeatRows=1)
    table.setStyle(TableStyle(_table_commands()))
    return table


def _recommendation_flows(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    recommendations = report.get("recommendations") or []
    if not recommendations:
        return [Paragraph("所选类别当前无需补充设施建议。", styles["body"])]
    flows: list[Flowable] = []
    for index, item in enumerate(recommendations, start=1):
        candidates = item.get("candidate_locations") or []
        candidate_text = "；".join(
            f"{candidate.get('id', '候选点')} ({_number(candidate.get('lng'), 6)}, {_number(candidate.get('lat'), 6)}) - {candidate.get('reason', '')}"
            for candidate in candidates
        ) or "未生成候选位置"
        improvement = item.get("target_improvement") or {}
        block = [
            Paragraph(f"{index}. {_escape(item.get('title') or '规划建议')}", styles["subsection"]),
            _key_value_table(
                [
                    ["设施类别", item.get("category_label") or item.get("category") or "-"],
                    ["优先级", item.get("priority") or item.get("priority_level") or "-"],
                    ["目标区域", "、".join(item.get("target_region_ids") or []) or "-"],
                    ["问题依据", item.get("problem_basis") or item.get("body") or "-"],
                    ["预计改善", improvement.get("description") or "需通过规划模拟进一步验证"],
                    ["候选位置", candidate_text],
                ],
                styles,
            ),
            Spacer(1, 3 * mm),
        ]
        flows.append(KeepTogether(block))
    return flows


def _quality_overview_table(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    quality = report.get("data_quality") or {}
    return _key_value_table(
        [
            ["总体状态", _quality_status_label(quality.get("overall_status"))],
            ["完整性", "完整结果" if report.get("completeness") == "complete" else "部分结果"],
            ["质量说明", quality.get("summary") or "未提供"],
            ["计算模式", (report.get("calculation_mode") or {}).get("walking_method") or "未提供"],
            ["坐标系", (report.get("calculation_mode") or {}).get("coordinate_system") or "BD-09"],
        ],
        styles,
    )


def _source_table(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Flowable:
    sources = (report.get("data_quality") or {}).get("sources") or []
    if not sources:
        return Paragraph("未记录数据来源。", styles["body"])
    rows = [[_header_cell(item, styles) for item in ["来源", "提供方", "用途", "是否最新真实测算"]]]
    for source in sources:
        rows.append(
            [
                _cell(source.get("label") or _source_label(source.get("kind")), styles),
                _cell(source.get("provider") or "-", styles),
                _cell(source.get("usage") or "-", styles),
                _cell("是" if source.get("is_latest_real_measurement") else "否", styles),
            ]
        )
    table = Table(rows, colWidths=[39 * mm, 40 * mm, 51 * mm, 27 * mm], repeatRows=1)
    table.setStyle(TableStyle(_table_commands()))
    return table


def _quality_event_table(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Flowable:
    events = (report.get("data_quality") or {}).get("events") or []
    if not events:
        return Paragraph("未记录数据质量事件。", styles["body"])
    grouped = Counter(
        (
            event.get("code") or "unknown",
            event.get("severity") or "info",
            event.get("scope") or "task",
            event.get("category") or "-",
            event.get("source") or "-",
            event.get("method") or "-",
            event.get("message") or "-",
        )
        for event in events
    )
    rows = [[_header_cell(item, styles) for item in ["事件/次数", "范围", "来源/方法", "说明"]]]
    for (code, severity, scope, category, source, method, message), count in sorted(grouped.items()):
        rows.append(
            [
                _cell(f"{code} ({severity}) × {count}", styles),
                _cell(f"{scope} / {category}", styles),
                _cell(f"{_source_label(source)} / {method}", styles),
                _cell(message, styles),
            ]
        )
    table = Table(rows, colWidths=[39 * mm, 28 * mm, 43 * mm, 47 * mm], repeatRows=1)
    table.setStyle(TableStyle(_table_commands()))
    return table


def _partial_failure_table(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Flowable:
    failures = (report.get("data_quality") or {}).get("partial_failures") or []
    if not failures:
        return Paragraph("未记录部分失败。", styles["body"])
    rows = [[_header_cell(item, styles) for item in ["类别/范围", "错误类型", "对象", "说明"]]]
    for failure in failures:
        rows.append(
            [
                _cell(failure.get("category") or failure.get("scope") or "-", styles),
                _cell(failure.get("code") or failure.get("error_type") or "-", styles),
                _cell(failure.get("object_ref") or "-", styles),
                _cell(failure.get("message") or failure.get("error") or str(failure), styles),
            ]
        )
    table = Table(rows, colWidths=[32 * mm, 34 * mm, 35 * mm, 56 * mm], repeatRows=1)
    table.setStyle(TableStyle(_table_commands()))
    return table


def _execution_table(report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    execution = report.get("execution") or {}
    metrics = execution.get("metrics") or {}
    rows = [
        ["总耗时", f"{_number(execution.get('total_duration_ms'), 0)} ms"],
        ["地图提供方调用", _format_integer(metrics.get("walking_provider_calls"))],
        ["真实 API 调用", _format_integer(metrics.get("walking_api_calls"))],
        ["缓存命中/未命中", f"{_format_integer(metrics.get('walking_cache_hits'))} / {_format_integer(metrics.get('walking_cache_misses'))}"],
        ["重试/超时/失败", f"{_format_integer(metrics.get('walking_retries'))} / {_format_integer(metrics.get('walking_timeouts'))} / {_format_integer(metrics.get('walking_failures'))}"],
        ["降级估算结果", _format_integer(metrics.get("walking_degraded_results"))],
        ["部分失败数量", _format_integer(metrics.get("partial_failure_count"))],
    ]
    return _key_value_table(rows, styles)


def _map_legend(styles: dict[str, ParagraphStyle]) -> Table:
    entries = [
        ("等时圈", GREEN_LIGHT),
        ("正常覆盖区", colors.HexColor("#DCEDE6")),
        ("设施稀疏区", AMBER_LIGHT),
        ("重点服务盲区", RED_LIGHT),
        ("设施点位", BLUE),
        ("分析中心", INK),
    ]
    cells: list[Any] = []
    for label, color in entries:
        cells.extend([ColorSwatch(color), Paragraph(label, styles["small"])])
    table = Table([cells], colWidths=[7 * mm, 19 * mm] * len(entries))
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
    return table


class ColorSwatch(Flowable):
    def __init__(self, color: colors.Color) -> None:
        super().__init__()
        self.color = color
        self.width = 5 * mm
        self.height = 5 * mm

    def draw(self) -> None:
        self.canv.setFillColor(self.color)
        self.canv.setStrokeColor(LINE)
        self.canv.roundRect(0, 0, self.width, self.height, 1.5, fill=1, stroke=1)


class ReportMap(Flowable):
    def __init__(self, report: dict[str, Any], width: float, height: float, label_style: ParagraphStyle) -> None:
        super().__init__()
        self.report = report
        self.width = width
        self.height = height
        self.label_style = label_style

    def draw(self) -> None:
        canvas = self.canv
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#EEF3F1"))
        canvas.setStrokeColor(LINE)
        canvas.roundRect(0, 0, self.width, self.height, 6, fill=1, stroke=1)

        points = list(_all_coordinates(self.report))
        if not points:
            canvas.setFillColor(MUTED)
            canvas.setFont(self.label_style.fontName, 9)
            canvas.drawCentredString(self.width / 2, self.height / 2, "报告缺少可绘制的空间坐标")
            canvas.restoreState()
            return
        lngs = [point[0] for point in points]
        lats = [point[1] for point in points]
        min_lng, max_lng = min(lngs), max(lngs)
        min_lat, max_lat = min(lats), max(lats)
        lng_pad = max((max_lng - min_lng) * 0.08, 0.0008)
        lat_pad = max((max_lat - min_lat) * 0.08, 0.0008)
        min_lng -= lng_pad
        max_lng += lng_pad
        min_lat -= lat_pad
        max_lat += lat_pad
        margin = 8 * mm

        def project(point: tuple[float, float]) -> tuple[float, float]:
            x = margin + (point[0] - min_lng) / max(max_lng - min_lng, 1e-9) * (self.width - 2 * margin)
            y = margin + (point[1] - min_lat) / max(max_lat - min_lat, 1e-9) * (self.height - 2 * margin)
            return x, y

        isochrone = self.report.get("isochrone") or {}
        _draw_geometry(canvas, isochrone.get("geometry"), project, GREEN_LIGHT, GREEN, 0.8)

        for feature in (self.report.get("service_areas") or self.report.get("zones") or {}).get("features", []):
            properties = feature.get("properties") or {}
            kind = properties.get("region_type", properties.get("kind"))
            fill = {"critical": RED_LIGHT, "sparse": AMBER_LIGHT, "normal": colors.HexColor("#DCEDE6")}.get(kind, PAPER)
            stroke = {"critical": RED, "sparse": AMBER, "normal": colors.HexColor("#8BB9A6")}.get(kind, LINE)
            _draw_geometry(canvas, feature.get("geometry"), project, fill, stroke, 0.35 if kind == "normal" else 0.75)

        for facility in self.report.get("facilities", self.report.get("pois", [])):
            if facility.get("lng") is None or facility.get("lat") is None:
                continue
            x, y = project((float(facility["lng"]), float(facility["lat"])))
            canvas.setFillColor(BLUE)
            canvas.setStrokeColor(colors.white)
            canvas.circle(x, y, 2.2, fill=1, stroke=1)

        for recommendation in self.report.get("recommendations", []):
            for candidate in recommendation.get("candidate_locations", []):
                if candidate.get("lng") is None or candidate.get("lat") is None:
                    continue
                x, y = project((float(candidate["lng"]), float(candidate["lat"])))
                canvas.setFillColor(AMBER)
                canvas.setStrokeColor(INK)
                canvas.rect(x - 2.3, y - 2.3, 4.6, 4.6, fill=1, stroke=1)

        center = self.report.get("analysis_center") or self.report.get("center") or {}
        if center.get("lng") is not None and center.get("lat") is not None:
            x, y = project((float(center["lng"]), float(center["lat"])))
            canvas.setFillColor(INK)
            canvas.setStrokeColor(colors.white)
            canvas.circle(x, y, 4.2, fill=1, stroke=1)
            canvas.setFillColor(colors.white)
            canvas.circle(x, y, 1.4, fill=1, stroke=0)

        canvas.setFillColor(colors.white)
        canvas.setStrokeColor(LINE)
        canvas.roundRect(5 * mm, self.height - 14 * mm, 68 * mm, 8 * mm, 3, fill=1, stroke=1)
        canvas.setFillColor(INK)
        canvas.setFont(self.label_style.fontName, 7.5)
        canvas.drawString(8 * mm, self.height - 10.8 * mm, "空间摘要 - BD-09 - 非商业底图")
        canvas.restoreState()


def _draw_geometry(
    canvas: Canvas,
    geometry: dict[str, Any] | None,
    project: Any,
    fill: colors.Color,
    stroke: colors.Color,
    alpha: float,
) -> None:
    if not geometry or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        return
    polygon_groups = geometry.get("coordinates") or []
    if geometry.get("type") == "Polygon":
        polygon_groups = [polygon_groups]
    canvas.saveState()
    canvas.setFillColor(fill)
    canvas.setStrokeColor(stroke)
    try:
        canvas.setFillAlpha(alpha)
    except AttributeError:
        pass
    for polygon in polygon_groups:
        if not polygon or not polygon[0]:
            continue
        path = canvas.beginPath()
        first_x, first_y = project((float(polygon[0][0][0]), float(polygon[0][0][1])))
        path.moveTo(first_x, first_y)
        for coordinate in polygon[0][1:]:
            x, y = project((float(coordinate[0]), float(coordinate[1])))
            path.lineTo(x, y)
        path.close()
        canvas.drawPath(path, fill=1, stroke=1)
    canvas.restoreState()


def _all_coordinates(report: dict[str, Any]) -> Iterable[tuple[float, float]]:
    for feature in [report.get("isochrone"), *((report.get("service_areas") or report.get("zones") or {}).get("features", []))]:
        if not feature:
            continue
        geometry = feature.get("geometry") or {}
        yield from _geometry_coordinates(geometry)
    for item in [
        report.get("analysis_center") or report.get("center") or {},
        *report.get("facilities", report.get("pois", [])),
    ]:
        if item.get("lng") is not None and item.get("lat") is not None:
            yield float(item["lng"]), float(item["lat"])
    for recommendation in report.get("recommendations", []):
        for candidate in recommendation.get("candidate_locations", []):
            if candidate.get("lng") is not None and candidate.get("lat") is not None:
                yield float(candidate["lng"]), float(candidate["lat"])


def _geometry_coordinates(geometry: dict[str, Any]) -> Iterable[tuple[float, float]]:
    coordinates = geometry.get("coordinates") or []
    if geometry.get("type") == "Polygon":
        for ring in coordinates:
            for coordinate in ring:
                yield float(coordinate[0]), float(coordinate[1])
    elif geometry.get("type") == "MultiPolygon":
        for polygon in coordinates:
            for ring in polygon:
                for coordinate in ring:
                    yield float(coordinate[0]), float(coordinate[1])


def _draw_page(canvas: Canvas, doc: Any, report: dict[str, Any], font_name: str) -> None:
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, PAGE_HEIGHT - 13 * mm, PAGE_WIDTH - 18 * mm, PAGE_HEIGHT - 13 * mm)
    canvas.setFont(font_name, 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, PAGE_HEIGHT - 10 * mm, "15分钟生活圈体检报告")
    canvas.drawRightString(PAGE_WIDTH - 18 * mm, PAGE_HEIGHT - 10 * mm, str(report.get("report_id") or report.get("id") or "-")[:18])
    canvas.line(18 * mm, 12 * mm, PAGE_WIDTH - 18 * mm, 12 * mm)
    canvas.drawString(18 * mm, 8 * mm, "坐标系 BD-09 - 生成结果以持久化标准报告为准")
    canvas.drawRightString(PAGE_WIDTH - 18 * mm, 8 * mm, f"第 {doc.page} 页")
    canvas.restoreState()


def _key_value_table(rows: list[list[Any]], styles: dict[str, ParagraphStyle]) -> Table:
    formatted = [[Paragraph(_escape(label), styles["small"]), Paragraph(_escape(value), styles["body"])] for label, value in rows]
    table = Table(formatted, colWidths=[34 * mm, 123 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), PAPER),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _table_commands() -> list[tuple[Any, ...]]:
    return [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]


def _cell(value: Any, styles: dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(_escape(value), styles["table"])


def _header_cell(value: Any, styles: dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(_escape(value), styles["table_header"])


def _category_labels(report: dict[str, Any]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for item in report.get("category_scores", report.get("categories", [])):
        if item.get("category"):
            labels[item["category"]] = item.get("label") or item["category"]
    for feature in (report.get("service_areas") or report.get("zones") or {}).get("features", []):
        properties = feature.get("properties") or {}
        if properties.get("category"):
            labels.setdefault(properties["category"], properties.get("category_label") or properties["category"])
    return labels


def _executive_summary(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    score = summary.get("score")
    score_text = "暂不展示" if score is None else f"{score} 分"
    return _escape(
        f"本次分析的综合生活圈指数为 {score_text}，识别 {summary.get('critical_zone_count', 0)} 个重点服务盲区、"
        f"{summary.get('sparse_zone_count', 0)} 个设施稀疏区，纳入 {summary.get('poi_count', 0)} 个设施点位。"
        f"{(report.get('scoring') or {}).get('explanation') or ''}"
    )


def _scoring_explanation(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    score = summary.get("score")
    return _escape(
        f"综合生活圈指数：{'暂不展示' if score is None else str(score) + ' 分'}。"
        f"{(report.get('scoring') or {}).get('explanation') or summary.get('score_explanation') or ''}"
    )


def _blind_spot_summary(report: dict[str, Any]) -> str:
    features = (report.get("service_areas") or report.get("zones") or {}).get("features", [])
    spots = [feature.get("properties") or {} for feature in features if (feature.get("properties") or {}).get("region_type", (feature.get("properties") or {}).get("kind")) == "critical"]
    counts = Counter(spot.get("category_label") or spot.get("category") or "未分类" for spot in spots)
    detail = "、".join(f"{label} {count} 个" for label, count in sorted(counts.items())) or "无"
    return _escape(f"共识别 {len(spots)} 个重点服务盲区，按设施类别统计为：{detail}。下表保留每个盲区的最近同类设施和判定依据。")


def _component_score(components: dict[str, dict[str, Any]], key: str) -> str:
    value = (components.get(key) or {}).get("score")
    return "-" if value is None else str(value)


def _quality_status_label(status: Any) -> str:
    return {"good": "良好", "limited": "有限", "partial": "部分结果"}.get(str(status), str(status or "未说明"))


def _mode_label(mode: Any) -> str:
    return {"demo": "演示模式", "analysis": "分析模式", "snapshot": "本地快照模式", "real": "真实地图模式"}.get(str(mode), str(mode or "未提供"))


def _source_label(source: Any) -> str:
    return source_label(source)


def _format_datetime(value: Any) -> str:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.strftime("%Y-%m-%d %H:%M:%S %z")
        except ValueError:
            return value
    return "-"


def _format_integer(value: Any) -> str:
    try:
        return f"{int(value or 0):,}"
    except (TypeError, ValueError):
        return "-"


def _format_area(value: Any) -> str:
    try:
        numeric = float(value or 0)
    except (TypeError, ValueError):
        return "-"
    if numeric >= 1_000_000:
        return f"{numeric / 1_000_000:.2f} km²"
    return f"{numeric:,.0f} m²"


def _minutes(value: Any) -> str:
    return "-" if value is None else f"{_number(value, 1)} 分钟"


def _meters(value: Any) -> str:
    return "-" if value is None else f"{_number(value, 0)} 米"


def _percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "-"


def _number(value: Any, decimals: int) -> str:
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return "-"


def _escape(value: Any) -> str:
    return str(value if value is not None else "-").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
