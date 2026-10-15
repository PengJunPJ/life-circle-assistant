"""将概要设计源稿排版为可搜索、带导航的 A4 PDF。

运行：python scripts/build_summary_design.py
依赖：reportlab、pypdf。中文字体可通过 LCA_DESIGN_BODY_FONT 和
LCA_DESIGN_HEADING_FONT 指定，支持 TTF/TTC。不会访问地图或模型服务。
"""

from __future__ import annotations

import argparse
import os
import re
from html import escape
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


APP = Path(__file__).resolve().parents[1]
SOURCE = APP / "docs/output/软件概要设计.md"
OUTPUT = APP / "docs/output/软件概要设计.pdf"
PAGE_W, PAGE_H = A4
LEFT, RIGHT, TOP, BOTTOM = 22 * mm, 22 * mm, 24 * mm, 22 * mm
WIDTH = PAGE_W - LEFT - RIGHT
INK = colors.HexColor("#193A39")
GREEN = colors.HexColor("#247B6A")
MUTED = colors.HexColor("#647371")
LIGHT = colors.HexColor("#F1F6F4")
LINE = colors.HexColor("#D2DEDA")
BLUE = colors.HexColor("#346A8A")
AMBER = colors.HexColor("#996C29")


def register_fonts() -> None:
    pairs = [
        ("LcaBody", "LCA_DESIGN_BODY_FONT", [
            "/System/Library/Fonts/Supplemental/Songti.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "C:/Windows/Fonts/simsun.ttc",
        ]),
        ("LcaHeading", "LCA_DESIGN_HEADING_FONT", [
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "C:/Windows/Fonts/msyh.ttc",
        ]),
    ]
    for name, env, defaults in pairs:
        candidates = [os.getenv(env, ""), *defaults]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                try:
                    # macOS 字体集合分别选择简体常规宋体和简体中黑体。
                    subfont_index = {
                        "Songti.ttc": 6,
                        "STHeiti Medium.ttc": 1,
                    }.get(Path(candidate).name, 0)
                    pdfmetrics.registerFont(TTFont(name, candidate, subfontIndex=subfont_index))
                    break
                except Exception:
                    continue
        else:
            raise RuntimeError(f"未找到可嵌入的中文字体，请配置 {env}")


def styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle(
        "正文", fontName="LcaBody", fontSize=10.4, leading=18.1,
        textColor=INK, alignment=TA_JUSTIFY, wordWrap="CJK",
        spaceAfter=7, allowWidows=0, allowOrphans=0,
        splitLongWords=True,
    )
    return {
        "body": base,
        "h1": ParagraphStyle(
            "章标题", parent=base, fontName="LcaHeading", fontSize=19,
            leading=28, alignment=TA_LEFT, spaceAfter=15, keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "节标题", parent=base, fontName="LcaHeading", fontSize=11.8,
            leading=18, textColor=GREEN, alignment=TA_LEFT,
            spaceBefore=9, spaceAfter=7, keepWithNext=True,
        ),
        "cell": ParagraphStyle(
            "表格正文", parent=base, fontSize=8.65, leading=13.4,
            spaceAfter=0, alignment=TA_LEFT,
        ),
        "th": ParagraphStyle(
            "表头", parent=base, fontName="LcaHeading", fontSize=8.7,
            leading=13.6, textColor=colors.white, alignment=TA_LEFT, spaceAfter=0,
        ),
        "caption": ParagraphStyle(
            "图题", parent=base, fontName="LcaHeading", fontSize=8.6,
            leading=13.5, alignment=TA_CENTER, textColor=MUTED,
            spaceBefore=5, spaceAfter=9,
        ),
        "table_caption": ParagraphStyle(
            "表题", parent=base, fontName="LcaHeading", fontSize=8.6,
            leading=13.5, textColor=MUTED, alignment=TA_LEFT,
            spaceBefore=2, spaceAfter=5, keepWithNext=True,
        ),
        "list": ParagraphStyle(
            "顺序条目", parent=base, leftIndent=16, firstLineIndent=-16,
            leading=17.5, spaceAfter=5,
        ),
        "toc": ParagraphStyle(
            "目录", parent=base, fontName="LcaHeading", fontSize=11,
            leading=21, leftIndent=0, firstLineIndent=0,
            alignment=TA_LEFT, spaceBefore=6, spaceAfter=6,
        ),
    }


def markup(text: str) -> str:
    value = escape(text)
    value = re.sub(r"\[R\d{2}\]", lambda m: f'<font color="#247B6A">{m[0]}</font>', value)
    return value


class Cover(Flowable):
    width = WIDTH
    height = PAGE_H - TOP - BOTTOM - 4

    def draw(self) -> None:
        c = self.canv
        c.saveState()
        c.resetTransforms()
        c.setFillColor(colors.HexColor("#F8FAF8"))
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        c.setFillColor(INK)
        c.rect(0, PAGE_H - 13 * mm, PAGE_W, 13 * mm, fill=1, stroke=0)
        c.setFillColor(GREEN)
        c.rect(LEFT, 215 * mm, 3 * mm, 37 * mm, fill=1, stroke=0)
        c.setFont("LcaHeading", 11)
        c.setFillColor(MUTED)
        c.drawString(LEFT + 8 * mm, 255 * mm, "15分钟生活圈智能体检与规划助手")
        c.setFillColor(INK)
        c.setFont("LcaHeading", 34)
        c.drawString(LEFT + 8 * mm, 233 * mm, "软件概要设计")
        c.setFont("LcaBody", 12)
        c.setFillColor(MUTED)
        c.drawString(LEFT + 8 * mm, 219 * mm, "系统架构 · 空间分析 · 事实治理 · 工程交付")

        # 可导出的矢量网络纹样，仅用于版式，不作为实际地理边界。
        c.setStrokeColor(LINE)
        for i in range(9):
            y = (130 + i * 7) * mm
            c.line(LEFT, y, PAGE_W - RIGHT, y)
        for i in range(15):
            x = LEFT + i * 12 * mm
            c.line(x, 129 * mm, x, 188 * mm)
        ring = [(93, 130), (67, 145), (56, 167), (73, 181), (111, 188),
                (144, 181), (161, 162), (148, 144), (121, 135), (93, 130)]
        path = c.beginPath()
        path.moveTo(ring[0][0] * mm, ring[0][1] * mm)
        for x, y in ring[1:]:
            path.lineTo(x * mm, y * mm)
        path.close()
        c.setFillColor(colors.HexColor("#E0EEE7"))
        c.setStrokeColor(GREEN)
        c.setLineWidth(1.5)
        c.drawPath(path, fill=1, stroke=1)
        for x, y in [(74, 155), (121, 169), (103, 182), (140, 151)]:
            c.setStrokeColor(colors.HexColor("#8EB7A7"))
            c.line(105 * mm, 159 * mm, x * mm, y * mm)
            c.setFillColor(colors.white)
            c.circle(x * mm, y * mm, 2.4 * mm, fill=1, stroke=1)
        c.setFillColor(INK)
        c.circle(105 * mm, 159 * mm, 3.2 * mm, fill=1, stroke=0)
        c.setFont("LcaHeading", 9)
        c.setFillColor(MUTED)
        c.drawRightString(PAGE_W - RIGHT, 121 * mm, "路线可达 · 证据约束 · 结果可追溯")

        fields = [
            ("文档编号", "LCA-SDD-001"), ("文档版本", "1.0"),
            ("应用基线", "2.3.0候选版 / 2026-10-14工作区"),
            ("编制日期", "2026年10月14日"), ("文档状态", "编制完成 · 待项目负责人评审"),
        ]
        for i, (label, value) in enumerate(fields):
            y = (100 - i * 9) * mm
            c.setFont("LcaHeading", 9)
            c.setFillColor(MUTED)
            c.drawString(LEFT, y, label)
            c.setFont("LcaBody", 10.5)
            c.setFillColor(INK)
            c.drawString(LEFT + 28 * mm, y, value)
        c.setStrokeColor(LINE)
        c.line(LEFT, 30 * mm, PAGE_W - RIGHT, 30 * mm)
        c.setFont("LcaBody", 9)
        c.setFillColor(MUTED)
        c.drawString(LEFT, 23 * mm, "面向设计评审、开发实现、测试验证及部署维护")
        c.restoreState()


class Diagram(Flowable):
    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind
        self.width = WIDTH
        self.height = {
            "context": 174, "architecture": 168, "analysis": 168,
            "lifecycle": 166, "simulation": 100, "factgate": 154,
            "governance": 144, "data": 228, "deployment": 184,
        }[kind]
        self.keepWithNext = True

    def draw(self) -> None:
        c = self.canv
        w = self.width
        c.saveState()
        c.setFillColor(LIGHT)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        c.roundRect(0, 0, w, self.height, 6, fill=1, stroke=1)

        def box(x, y, bw, bh, title, sub="", color=GREEN):
            c.setFillColor(colors.white)
            c.setStrokeColor(color)
            c.setLineWidth(0.65)
            c.roundRect(x, y, bw, bh, 4, fill=1, stroke=1)
            text = f'<font name="LcaHeading" color="{color.hexval()}">{escape(title)}</font>'
            if sub:
                text += f'<br/><font name="LcaBody" size="8" color="#647371">{escape(sub)}</font>'
            p = Paragraph(text, ParagraphStyle(
                "图节点", fontName="LcaHeading", fontSize=9.2, leading=14,
                alignment=TA_CENTER, wordWrap="CJK",
            ))
            _, ph = p.wrap(bw - 10, bh)
            p.drawOn(c, x + 5, y + (bh - ph) / 2)

        def arrow(x1, y1, x2, y2, label="", dashed=False):
            import math
            c.setStrokeColor(GREEN)
            c.setFillColor(GREEN)
            c.setLineWidth(0.8)
            c.setDash(3, 2) if dashed else c.setDash()
            c.line(x1, y1, x2, y2)
            c.setDash()
            angle = math.atan2(y2 - y1, x2 - x1)
            path = c.beginPath()
            path.moveTo(x2, y2)
            for offset in (-0.48, 0.48):
                path.lineTo(x2 - 5.5 * math.cos(angle + offset), y2 - 5.5 * math.sin(angle + offset))
            path.close()
            c.drawPath(path, fill=1, stroke=0)
            if label:
                c.setFont("LcaBody", 7.2)
                c.setFillColor(MUTED)
                c.drawCentredString((x1 + x2) / 2, (y1 + y2) / 2 + 6, label)

        if self.kind == "context":
            bw = (w - 76) / 3
            xs = [12, (w - bw) / 2, w - 12 - bw]
            box(xs[0], 117, bw, 42, "浏览器工作台", "Vue · 地图 · 报告")
            box(xs[1], 117, bw, 42, "FastAPI服务", "体检 · 规划 · 核验")
            box(xs[2], 117, bw, 42, "SQLite", "任务 · 报告 · 账本")
            arrow(xs[0] + bw, 138, xs[1], 138, "/api")
            arrow(xs[1] + bw, 138, xs[2], 138)
            box(xs[0], 21, bw, 46, "百度地图服务", "底图 / 地理编码 / 步行")
            box(xs[1], 21, bw, 46, "可选外部服务", "模型 / 嵌入 / OCR / 高德", BLUE)
            box(xs[2], 21, bw, 46, "本地快照", "合成样例 · 离线演示")
            arrow(xs[1] + bw / 2, 117, xs[0] + bw / 2, 67, "真实模式")
            arrow(xs[1] + bw / 2, 117, xs[1] + bw / 2, 67, dashed=True)
            arrow(xs[1] + bw / 2, 117, xs[2] + bw / 2, 67, "mock")
        elif self.kind == "architecture":
            rows = [(116, "交互与HTTP层", "Vue组件 / 状态 / 请求服务 · FastAPI路由"),
                    (64, "用例与领域层", "体检 / 分类 / 评分 / 模拟 / 对话 / 事实治理"),
                    (12, "契约与适配层", "MapProvider / 仓储 / 模型 / 账本 / 导出")]
            for y, title, sub in rows:
                box(12, y, w - 24, 40, title, sub)
            arrow(w / 2, 116, w / 2, 104)
            arrow(w / 2, 64, w / 2, 52)
        elif self.kind == "analysis":
            bw = (w - 66) / 3
            xs = [12, 33 + bw, 54 + bw * 2]
            names = [("校验与任务创建", "参数 / 范围 / queued"),
                     ("设施发现与归一", "分类 / 来源 / 重复处理"),
                     ("步行与等时圈", "缓存 / 矩阵 / 采样")]
            for x, (title, sub) in zip(xs, names):
                box(x, 109, bw, 44, title, sub)
            arrow(xs[0] + bw, 131, xs[1], 131)
            arrow(xs[1] + bw, 131, xs[2], 131)
            names2 = [("服务区与评分", "四类网格 / 固定规则"),
                      ("建议与报告装配", "证据 / 质量 / 执行"),
                      ("持久化与展示", "原子保存 / 前端轮询")]
            for x, (title, sub) in zip(xs, names2):
                box(x, 22, bw, 44, title, sub)
            arrow(xs[2] + bw / 2, 109, xs[0] + bw / 2, 66, "后台阶段推进")
            arrow(xs[0] + bw, 44, xs[1], 44)
            arrow(xs[1] + bw, 44, xs[2], 44)
        elif self.kind == "lifecycle":
            bw = 112
            box(12, 108, bw, 42, "queued", "已保存任务")
            box(w / 2 - bw / 2, 108, bw, 42, "running", "执行中 / 阶段推进")
            box(w - 12 - bw, 108, bw, 42, "completed", "报告已原子保存")
            arrow(124, 129, w / 2 - bw / 2, 129)
            arrow(w / 2 + bw / 2, 129, w - 124, 129)
            box(12, 17, bw, 43, "中断 / 检查点", "恢复前核对未决调用", BLUE)
            box(w / 2 - bw / 2, 17, bw, 43, "failed", "失败；可重试 / 续算", AMBER)
            box(w - 12 - bw, 17, bw, 43, "cancelled", "用户取消", AMBER)
            arrow(w / 2, 108, 68, 60, dashed=True)
            arrow(68, 60, 68, 108, "恢复", dashed=True)
            arrow(w / 2, 108, w / 2, 60)
            arrow(w / 2 + 35, 108, w - 68, 60)
        elif self.kind == "simulation":
            bw = (w - 76) / 3
            xs = [12, (w - bw) / 2, w - 12 - bw]
            for x, title, sub in zip(xs, ["来源报告", "假设设施与测路", "前后比较"],
                                      ["不可变事实快照", "重算受影响类别", "独立结果 / 披露假设"]):
                box(x, 28, bw, 47, title, sub)
            arrow(xs[0] + bw, 51, xs[1], 51)
            arrow(xs[1] + bw, 51, xs[2], 51)
        elif self.kind == "factgate":
            bw = 130
            box(12, 95, bw, 43, "已保存报告事实", "槽位 / 建议 / 证据")
            box(w / 2 - 65, 95, bw, 43, "模型或规则选择", "结构化字段 / 工具")
            box(w - 142, 95, bw, 43, "服务端校验", "报告绑定 / 白名单")
            arrow(142, 116, w / 2 - 65, 116)
            arrow(w / 2 + 65, 116, w - 142, 116)
            box(40, 14, 170, 43, "规则降级", "超时 / 非法输出 / 引用失败", AMBER)
            box(w - 210, 14, 170, 43, "可信呈现", "服务器渲染事实；评分不变")
            arrow(w - 77, 95, w - 125, 57, "通过")
            arrow(w / 2, 95, 125, 57, "失败")
        elif self.kind == "governance":
            bw = (w - 66) / 3
            xs = [12, 33 + bw, 54 + bw * 2]
            for x, title, sub in zip(xs, ["来源与居民观察", "待人工审核", "目录新版本"],
                                      ["原始记录 / OCR材料", "接纳 / 驳回 / 修正", "事务保存 / 审计"]):
                box(x, 87, bw, 43, title, sub)
            arrow(xs[0] + bw, 109, xs[1], 109)
            arrow(xs[1] + bw, 109, xs[2], 109)
            box(16, 13, 197, 43, "旧报告保留", "目录修订不覆盖既有事实", BLUE)
            box(w - 213, 13, 197, 43, "正式重算产生新报告", "重新测路 / 分类 / 评分")
            arrow(xs[2] + bw / 2, 87, w - 114, 56)
        elif self.kind == "data":
            box(12, 163, 139, 48, "analysis_tasks", "请求 / 状态 / 时间")
            box(173, 163, 139, 48, "analysis_reports", "完成快照 / 不可变")
            box(334, 163, w - 346, 48, "治理与规划", "目录 / 观察 / 候选")
            arrow(151, 187, 173, 187, "1 : 0..1")
            arrow(312, 187, 334, 187, "1 : N")
            box(12, 87, 139, 48, "execution_runs", "预算 / 用量 / 版本")
            box(173, 87, 139, 48, "检查点与结算", "调用状态 / 人工核验")
            box(334, 87, w - 346, 48, "walking_cache", "坐标对 / TTL / 来源")
            arrow(81, 163, 81, 135, "关联执行")
            arrow(151, 111, 173, 111, "1 : N")
            box(12, 13, 204, 46, "conversation_workspaces", "revision / state / pending")
            box(250, 13, w - 262, 46, "conversation_turns", "request_id / fingerprint / result")
            arrow(216, 36, 250, 36, "1 : N")
        elif self.kind == "deployment":
            box(12, 121, 125, 47, "本机浏览器", "localhost:5173")
            box(172, 121, 125, 47, "web容器", "Nginx :80 / Vue产物")
            box(w - 137, 121, 125, 47, "api容器", "FastAPI :8000")
            arrow(137, 144, 172, 144, "HTTP")
            arrow(297, 144, w - 137, 144, "/api")
            box(20, 25, 203, 48, "默认只绑定宿主回环地址", "web :5173 · api :8000", BLUE)
            box(w - 220, 25, 200, 48, "analysis-data持久卷", "/app/data/runtime / SQLite")
            arrow(w - 74, 121, w - 119, 73, "读写")
        c.restoreState()


def make_table(lines: list[str], sty: dict, title: str) -> list[Flowable]:
    raw = [[part.strip() for part in line.strip().strip("|").split("|")] for line in lines]
    raw = [row for row in raw if not all(re.fullmatch(r":?-+:?", cell or "") for cell in row)]
    columns = len(raw[0])
    if any(len(row) != columns for row in raw):
        raise ValueError(f"表格列数不一致：{title}")
    weights = {
        3: [0.22, 0.41, 0.37], 4: [0.18, 0.30, 0.27, 0.25], 2: [0.25, 0.75],
    }[columns]
    if raw[0][0] == "方法":
        weights = [0.15, 0.46, 0.39]
    elif raw[0] == ["编号", "目标或约束", "设计响应"]:
        weights = [0.12, 0.29, 0.59]
    elif raw[0][0] in {"编号", "表名", "字段组"}:
        weights = [0.13, 0.55, 0.32] if raw[0][0] == "编号" else [0.31, 0.34, 0.35]
    elif raw[0][0] == "字段":
        weights = [0.30, 0.35, 0.35]
    elif columns == 4 and raw[0][0] == "类别标识":
        weights = [0.21, 0.23, 0.17, 0.39]
    rows = [[Paragraph(markup(value), sty["th" if i == 0 else "cell"])
             for value in row] for i, row in enumerate(raw)]
    table = Table(rows, colWidths=[WIDTH * x for x in weights], repeatRows=1,
                  hAlign="LEFT", splitByRow=1, spaceAfter=10)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, GREEN),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, LINE),
        ("BOX", (0, 0), (-1, -1), 0.45, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [Paragraph(markup(title), sty["table_caption"]), table]


class DesignDocument(BaseDocTemplate):
    def __init__(self, output: Path, total_pages: int | None):
        super().__init__(str(output), pagesize=A4, leftMargin=LEFT, rightMargin=RIGHT,
                         topMargin=TOP, bottomMargin=BOTTOM, pageCompression=1,
                         title="软件概要设计｜15分钟生活圈智能体检与规划助手",
                         author="15分钟生活圈智能体检与规划助手项目",
                         subject="LCA-SDD-001 · 系统架构、运行、接口、数据及部署设计")
        self.expected_pages = total_pages
        frame = Frame(LEFT, BOTTOM, WIDTH, PAGE_H - TOP - BOTTOM,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates(PageTemplate(id="正文", frames=[frame], onPageEnd=self.decorate))

    def beforeDocument(self):
        self.current_chapter = "软件概要设计"
        self.heading_number = 0
        self.canv.setViewerPreference("DisplayDocTitle", "true")

    def afterFlowable(self, flowable):
        if isinstance(flowable, Cover):
            self.canv.bookmarkPage("cover")
            self.canv.addOutlineEntry("封面", "cover", 0, False)
        level = getattr(flowable, "heading_level", None)
        if level is None:
            return
        title = flowable.getPlainText()
        self.heading_number += 1
        key = f"heading-{self.heading_number}"
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(title, key, level, closed=level == 0)
        if level == 0:
            self.current_chapter = title
            if title != "目录":
                self.notify("TOCEntry", (0, title, self.page, key))

    def decorate(self, canvas, doc):
        if self.page == 1:
            return
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.6)
        canvas.line(LEFT, PAGE_H - 15.5 * mm, PAGE_W - RIGHT, PAGE_H - 15.5 * mm)
        canvas.line(LEFT, 15 * mm, PAGE_W - RIGHT, 15 * mm)
        canvas.setFont("LcaHeading", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(LEFT, PAGE_H - 11.5 * mm, "15分钟生活圈智能体检与规划助手")
        canvas.drawRightString(PAGE_W - RIGHT, PAGE_H - 11.5 * mm, self.current_chapter)
        canvas.setFont("LcaBody", 7.8)
        canvas.drawString(LEFT, 9.5 * mm, "LCA-SDD-001  |  V1.0  |  2026-10-14")
        total = str(self.expected_pages) if self.expected_pages else "—"
        canvas.drawRightString(PAGE_W - RIGHT, 9.5 * mm, f"第 {self.page} 页 / 共 {total} 页")
        canvas.restoreState()


def story(source: Path, sty: dict) -> list[Flowable]:
    text = source.read_text(encoding="utf-8")
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    lines = text.splitlines()
    result = []
    chapter, section = "0", "文档信息"
    table_numbers: dict[str, int] = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line == "<!-- cover -->":
            result.append(Cover())
        elif line == "<!-- page -->":
            result.append(PageBreak())
        elif line == "<!-- toc -->":
            toc = TableOfContents()
            toc.levelStyles = [sty["toc"]]
            toc.dotsMinLevel = 0
            result += [Spacer(1, 8), toc, Spacer(1, 24), Paragraph(
                "目录为可点击导航；PDF书签同时提供章、节定位。页码含封面与文档控制页，全文连续编号。", sty["body"])]
        elif line.startswith("<!-- diagram:"):
            kind = re.fullmatch(r"<!-- diagram: (\w+) -->", line)[1]
            result.append(Diagram(kind))
        elif line.startswith("# "):
            title = line[2:]
            match = re.match(r"(\d+) ", title)
            chapter = match[1] if match else "0"
            section = title
            p = Paragraph(markup(title), sty["h1"])
            p.heading_level = 0
            result.append(p)
        elif line.startswith("## "):
            section = line[3:]
            p = Paragraph(markup(section), sty["h2"])
            p.heading_level = 1
            result.append(p)
        elif line.startswith("|"):
            batch = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                batch.append(lines[i])
                i += 1
            number = table_numbers.get(chapter, 0) + 1
            table_numbers[chapter] = number
            label = re.sub(r"^\d+\.\d+\s+", "", section)
            result.extend(make_table(batch, sty, f"表{chapter}-{number}  {label}"))
            continue
        elif re.match(r"图\d+-\d+ ", line):
            result.append(Paragraph(markup(line), sty["caption"]))
        elif re.match(r"\d+\. ", line):
            result.append(Paragraph(markup(line), sty["list"]))
        else:
            batch = [line]
            while i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith(("#", "|", "<!--")):
                i += 1
                batch.append(lines[i].strip())
            result.append(Paragraph(markup(" ".join(batch)), sty["body"]))
        i += 1
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    register_fonts()
    sty = styles()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    first = DesignDocument(args.output, None)
    first.multiBuild(story(args.source, sty))
    count = len(PdfReader(args.output).pages)
    final = DesignDocument(args.output, count)
    final.multiBuild(story(args.source, sty))
    reader = PdfReader(args.output)
    if len(reader.pages) != count:
        raise RuntimeError("排版两次页数不一致，须重新核对页码")
    print(f"已生成：{args.output}\n页数：{count}\n大小：{args.output.stat().st_size:,}字节")


if __name__ == "__main__":
    main()
