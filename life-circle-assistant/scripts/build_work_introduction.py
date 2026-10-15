"""把参赛介绍源稿构建为嵌入中文字体、带书签的 A4 PDF。

运行：python scripts/build_work_introduction.py
依赖：reportlab、Pillow、pypdf。只读取本地资料，不调用外部服务。
"""

from __future__ import annotations

import json
import os
import re
from html import escape
from pathlib import Path

from PIL import Image as PILImage
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


APP = Path(__file__).resolve().parents[1]
ROOT = APP.parent
SOURCE = APP / "docs/contest/submission/作品介绍文档.md"
OUTPUT = APP / "docs/output/作品介绍文档.pdf"
CHECK = ROOT / ".scratch/work-introduction/verification.json"
W, H = A4
LEFT = 20 * mm
WIDTH = W - LEFT * 2
INK = colors.HexColor("#173B3D")
GREEN = colors.HexColor("#147D73")
TEAL = colors.HexColor("#1AB9A5")
PALE = colors.HexColor("#EDF6F3")
MUTED = colors.HexColor("#627779")
LINE = colors.HexColor("#D5E3DF")


def fonts() -> None:
    for name, variable, candidates in (
        ("IntroBody", "LCA_INTRO_BODY_FONT", [
            ("/System/Library/Fonts/Supplemental/Songti.ttc", 6),
            ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
            ("C:/Windows/Fonts/simsun.ttc", 0),
        ]),
        ("IntroHead", "LCA_INTRO_HEADING_FONT", [
            ("/System/Library/Fonts/STHeiti Medium.ttc", 1),
            ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
            ("C:/Windows/Fonts/msyh.ttc", 0),
        ]),
    ):
        override = os.getenv(variable)
        if override:
            candidates = [(override, 0), *candidates]
        for path, index in candidates:
            if Path(path).is_file():
                try:
                    pdfmetrics.registerFont(TTFont(name, path, subfontIndex=index))
                    break
                except Exception:
                    continue
        else:
            raise RuntimeError(f"缺少可嵌入中文字体，请设置 {variable}")


def styles() -> dict[str, ParagraphStyle]:
    body = ParagraphStyle(
        "正文", fontName="IntroBody", fontSize=10.3, leading=17.4,
        textColor=INK, wordWrap="CJK", spaceAfter=8,
        allowWidows=0, allowOrphans=0,
    )
    return {
        "body": body,
        "h1": ParagraphStyle("章", parent=body, fontName="IntroHead",
                             fontSize=20, leading=28, spaceAfter=15,
                             keepWithNext=True),
        "h2": ParagraphStyle("节", parent=body, fontName="IntroHead",
                             fontSize=11.6, leading=18.4, spaceBefore=8,
                             spaceAfter=7, textColor=GREEN, keepWithNext=True),
        "cell": ParagraphStyle("表文", parent=body, fontSize=9.1,
                               leading=14.2, spaceAfter=0),
        "th": ParagraphStyle("表头", parent=body, fontName="IntroHead",
                             fontSize=9, leading=14, textColor=colors.white,
                             spaceAfter=0),
        "caption": ParagraphStyle("图题", parent=body, fontSize=8.3,
                                  leading=12.4, textColor=MUTED,
                                  alignment=TA_CENTER, spaceAfter=10),
        "small": ParagraphStyle("索引", parent=body, fontSize=8.5,
                                leading=12.6, spaceAfter=6),
        "code": ParagraphStyle("命令", parent=body, fontName="Courier",
                               fontSize=9, leading=15, spaceAfter=0),
    }


def markup(value: str) -> str:
    value = escape(value)
    value = re.sub(r"\[R\d+\]", lambda m: f'<font color="#147D73">{m[0]}</font>', value)
    value = re.sub(
        r"https://github.com/PengJunPJ/life-circle-assistant",
        '<link href="https://github.com/PengJunPJ/life-circle-assistant" color="#147D73">'
        'https://github.com/PengJunPJ/life-circle-assistant</link>', value,
    )
    return value


class Diagram(Flowable):
    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind
        self.width = WIDTH
        self.height = 30 * mm if kind == "workflow" else 89 * mm

    def label(self, text: str, x: float, y: float, size: float = 10,
              color=INK, centered: bool = False) -> None:
        self.canv.setFillColor(color)
        self.canv.setFont("IntroHead", size)
        if centered:
            self.canv.drawCentredString(x, y, text)
        else:
            self.canv.drawString(x, y, text)

    def arrow(self, x: float, y: float) -> None:
        c = self.canv
        c.setStrokeColor(GREEN)
        c.setLineWidth(1.1)
        c.line(x, y, x, y - 11)
        c.line(x, y - 11, x - 3, y - 7)
        c.line(x, y - 11, x + 3, y - 7)

    def draw(self) -> None:
        c = self.canv
        c.saveState()
        if self.kind == "workflow":
            labels = ["选点与确认", "真实路网体检", "证据解释", "模拟与导出"]
            subtitles = ["地址／坐标／对话", "等时圈／设施／盲区", "评分／来源／质量", "候选／对照／报告"]
            gap = 9
            bw = (WIDTH - 3 * gap) / 4
            for i, (title, subtitle) in enumerate(zip(labels, subtitles)):
                x = i * (bw + gap)
                c.setFillColor(PALE)
                c.roundRect(x, 25, bw, 54, 7, fill=1, stroke=0)
                self.label(f"0{i+1}", x + 10, 64, 9, GREEN)
                self.label(title, x + 10, 47, 10.5)
                self.label(subtitle, x + 10, 32, 7.5, MUTED)
                if i < 3:
                    c.setStrokeColor(GREEN)
                    c.line(x + bw + 1, 52, x + bw + gap - 1, 52)
            self.label("同一报告事实贯穿地图、对话、模拟与导出", WIDTH / 2, 9, 9, MUTED, True)
        else:
            bands = [
                ("交互工作台", "地图与图层  ·  自然语言对话  ·  体检报告与 AI 核验"),
                ("应用与执行", "FastAPI  ·  异步任务  ·  工具白名单  ·  预算与检查点"),
                ("可信领域计算", "等时圈  ·  设施与网格  ·  规则评分  ·  模拟与组合选址"),
                ("数据与提供方", "百度地图／离线快照  ·  可选模型服务  ·  SQLite／版本账本"),
            ]
            for i, (title, detail) in enumerate(bands):
                y = self.height - 51 - i * 58
                c.setFillColor(INK if i == 0 else PALE)
                c.roundRect(0, y, WIDTH, 44, 6, fill=1, stroke=0)
                self.label(title, 14, y + 26, 11, colors.white if i == 0 else GREEN)
                self.label(detail, 14, y + 10, 9, colors.white if i == 0 else INK)
                if i < 3:
                    self.arrow(WIDTH / 2, y - 1)
            self.label("模型选择事实与工具；后端计算并校验结论", WIDTH / 2, 4, 9, MUTED, True)
        c.restoreState()


class Cover(Flowable):
    width = WIDTH
    height = H - 48 * mm - 2

    def __init__(self, style):
        super().__init__()
        self.style = style

    def draw(self) -> None:
        c = self.canv
        c.saveState()
        c.resetTransforms()
        c.setFillColor(colors.HexColor("#F6F9F7"))
        c.rect(0, 0, W, H, fill=1, stroke=0)
        c.setFillColor(INK)
        c.rect(0, H - 14 * mm, W, 14 * mm, fill=1, stroke=0)
        c.setFillColor(TEAL)
        c.rect(LEFT, H - 36 * mm, 18 * mm, 2 * mm, fill=1, stroke=0)

        def line(text, y, size, color=INK, font="IntroHead"):
            c.setFillColor(color)
            c.setFont(font, size)
            c.drawString(LEFT, y * mm, text)

        line("2026 上海开源软件应用创新大赛", 251, 11, GREEN)
        line("开源 AI 工具赛道  /  作品介绍文档", 241, 10, MUTED)
        line("15分钟生活圈", 218, 34)
        line("智能体检与规划助手", 202, 29)
        line("基于地图开放能力的社区可达性分析与规划辅助工具", 187, 11, MUTED)
        line("让社区服务可达性可计算，让规划建议有证据可查。", 174, 12, GREEN)

        path = APP / "docs/contest/submission/screenshots-20261015/01-real-map-report.png"
        with PILImage.open(path) as im:
            iw, ih = im.size
        image_h = WIDTH * ih / iw
        c.drawImage(str(path), LEFT, 70 * mm, WIDTH, image_h, mask="auto")
        line("当前版本真实百度地图与 AI · 沙涌长盛花园 · 2026年10月15日", 64, 8, MUTED)
        p = Paragraph(
            "面向社区规划与公共服务评估，连接真实步行路线、七类设施体检、"
            "证据约束的 AI 交互及改善模拟，支持无密钥离线复现与多格式报告导出。",
            self.style["body"],
        )
        _, ph = p.wrap(WIDTH, 50 * mm)
        p.drawOn(c, LEFT, 59 * mm - ph)
        line("参赛候选版本 2.3.0    |    Apache-2.0    |    2026年10月15日", 31, 9, GREEN)
        line("github.com/PengJunPJ/life-circle-assistant", 23, 8.8, MUTED)
        c.linkURL("https://github.com/PengJunPJ/life-circle-assistant",
                  (LEFT, 21 * mm, W - LEFT, 27 * mm), relative=0)
        c.restoreState()


class Document(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Cover):
            key, title = "cover", "作品介绍文档"
        elif isinstance(flowable, Paragraph) and flowable.style.name == "章":
            title = flowable.getPlainText()
            key = f"chapter-{self.page}"
        else:
            return
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(title, key, level=0)


def footer(canvas, doc):
    if doc.page == 1:
        return
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(LEFT, H - 17 * mm, W - LEFT, H - 17 * mm)
    canvas.line(LEFT, 17 * mm, W - LEFT, 17 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("IntroHead", 7.3)
    canvas.drawString(LEFT, H - 13 * mm, "15分钟生活圈 · 智能体检与规划助手")
    canvas.drawRightString(W - LEFT, H - 13 * mm, "2026 / 开源 AI 工具赛道")
    canvas.drawString(LEFT, 11.5 * mm, "参赛作品介绍  ·  2026.10.15")
    canvas.drawRightString(W - LEFT, 11.5 * mm, f"{doc.page:02d} / 10")
    canvas.restoreState()


def table(lines, style):
    rows = [[x.strip() for x in line.strip().strip("|").split("|")] for line in lines]
    rows = [row for row in rows if not all(re.fullmatch(r":?-+:?", x) for x in row)]
    n = len(rows[0])
    widths = {
        2: [WIDTH * .27, WIDTH * .73],
        3: [WIDTH * .28, WIDTH * .30, WIDTH * .42],
        4: [WIDTH * .37, WIDTH * .21, WIDTH * .20, WIDTH * .22],
    }[n]
    data = [[Paragraph(markup(x), style["th" if i == 0 else "cell"])
             for x in row] for i, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), .4, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def story(source, style):
    pages = source.split("<!-- page -->")
    result = [Cover(style), PageBreak()]
    for index, page in enumerate(pages[1:]):
        lines = page.strip().splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if line.startswith("# "):
                result.append(Paragraph(markup(line[2:]), style["h1"]))
            elif line.startswith("## "):
                result.append(Paragraph(markup(line[3:]), style["h2"]))
            elif line.startswith(":::mapping"):
                raise ValueError("不支持的图形")
            elif line.startswith(":::"):
                result.append(Diagram(line[3:]))
            elif line.startswith("|"):
                chunk = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    chunk.append(lines[i].strip())
                    i += 1
                result.extend([table(chunk, style), Spacer(1, 9)])
                continue
            elif line.startswith("!["):
                match = re.fullmatch(r"!\[(.+)\]\((.+)\)", line)
                if not match:
                    raise ValueError(line)
                caption, relative = match.groups()
                path = (SOURCE.parent / relative).resolve()
                with PILImage.open(path) as im:
                    iw, ih = im.size
                image_width = 150 * mm if index in (1, 4) else WIDTH
                image = Image(str(path), width=image_width, height=image_width * ih / iw)
                if path.name == "02-real-ai-summary.png":
                    # 原界面全景与原生局部截图并排，方便纸面阅读模型标识和回答。
                    detail_path = path.with_name("05-real-ai-detail.png")
                    with PILImage.open(detail_path) as detail:
                        dw, dh = detail.size
                    overview = Image(str(path), width=112 * mm, height=112 * mm * ih / iw)
                    detail = Image(str(detail_path), width=50 * mm, height=50 * mm * dh / dw)
                    image = Table([[overview, detail]], colWidths=[116 * mm, 54 * mm])
                    image.setStyle(TableStyle([
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ]))
                result.append(KeepTogether([
                    Spacer(1, 4), image, Spacer(1, 6),
                    Paragraph(markup(caption), style["caption"]),
                ]))
            elif line.startswith("```"):
                code = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    text = lines[i]
                    code.append(Paragraph(markup(text), style["small" if text.startswith("#") else "code"]))
                    i += 1
                box = Table([[code]], colWidths=[WIDTH])
                box.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), PALE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]))
                result.extend([box, Spacer(1, 10)])
            elif line.startswith("> "):
                q = Table([[Paragraph(markup(line[2:]), style["body"])]], colWidths=[WIDTH])
                q.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), PALE),
                    ("LINEBEFORE", (0, 0), (0, 0), 2.5, GREEN),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                result.append(q)
            else:
                is_reference = line.startswith("- [R")
                result.append(Paragraph(markup(line[2:] if is_reference else line),
                                        style["small" if is_reference else "body"]))
            i += 1
        if index < len(pages) - 2:
            result.append(PageBreak())
    return result


def verify() -> dict:
    reader = PdfReader(OUTPUT)
    pages = reader.pages
    text = [page.extract_text() or "" for page in pages]
    assert len(pages) == 10, f"预期10页，实际{len(pages)}页，请调整排版"
    assert len(reader.outline) == 10, "书签不完整"
    assert not any("\ufffd" in t or "\x00" in t for t in text), "文本含缺失字符"
    for page in pages:
        assert abs(float(page.mediabox.width) - W) < 1
        assert abs(float(page.mediabox.height) - H) < 1
    for i, page_text in enumerate(text[1:], 1):
        assert f"{i:02d} " in page_text, f"第{i+1}页缺少章标题"
    font_info = {}
    for page in pages:
        for ref in page["/Resources"]["/Font"].values():
            font = ref.get_object()
            name = str(font.get("/BaseFont"))
            if "Song" in name or "Heiti" in name or "/AAAA" in name:
                descriptor = font.get("/FontDescriptor")
                embedded = bool(descriptor and "/FontFile2" in descriptor.get_object())
                font_info[name] = {"embedded": embedded, "unicode": "/ToUnicode" in font}
    assert font_info and all(v["embedded"] and v["unicode"] for v in font_info.values())
    result = {
        "file": str(OUTPUT.relative_to(ROOT)), "pages": len(pages),
        "bytes": OUTPUT.stat().st_size, "bookmarks": len(reader.outline),
        "page_characters": [len(t) for t in text], "chinese_fonts": font_info,
        "page_size": "A4", "replacement_characters": 0,
        "historical_validation_cutoff": "2026-10-14", "document_date": "2026-10-15",
        "screenshot_capture_date": "2026-10-15", "product_tests_rerun": False,
        "capture_evidence": "life-circle-assistant/docs/contest/submission/screenshots-20261015/capture-evidence.json",
    }
    CHECK.parent.mkdir(parents=True, exist_ok=True)
    CHECK.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    fonts()
    style = styles()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = Document(
        str(OUTPUT), pagesize=A4, leftMargin=LEFT, rightMargin=LEFT,
        topMargin=25 * mm, bottomMargin=22 * mm,
        title="15分钟生活圈智能体检与规划助手｜作品介绍文档",
        author="15分钟生活圈智能体检与规划助手项目",
        subject="2026上海开源软件应用创新大赛｜项目背景、技术架构、应用场景与创新点",
    )
    frame = Frame(LEFT, 22 * mm, WIDTH, H - 47 * mm,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    document.addPageTemplates(PageTemplate(id="intro", frames=[frame], onPage=footer))
    document.build(story(SOURCE.read_text(encoding="utf-8"), style))
    print(json.dumps(verify(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
