from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as ReportImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = PROJECT_ROOT / "docs" / "contest" / "screenshots"
OUTPUT_PATH = PROJECT_ROOT / "docs" / "contest" / "submission" / "15-minute-life-circle-competition-brief.pdf"
PAGE_WIDTH, PAGE_HEIGHT = A4

INK = colors.HexColor("#173D36")
GREEN = colors.HexColor("#2F8F80")
GREEN_LIGHT = colors.HexColor("#E8F3EF")
BLUE = colors.HexColor("#326B8A")
AMBER = colors.HexColor("#C88729")
RED = colors.HexColor("#B95343")
MUTED = colors.HexColor("#60766F")
LINE = colors.HexColor("#D9E4DF")
PAPER = colors.HexColor("#F6F9F7")


def register_fonts() -> tuple[str, str]:
    regular_name = "CompetitionChinese"
    bold_name = "CompetitionChineseBold"
    if regular_name in pdfmetrics.getRegisteredFontNames():
        return regular_name, bold_name
    candidates = [
        os.getenv("LIFE_CIRCLE_PDF_FONT_PATH", "").strip(),
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "C:/Windows/Fonts/msyh.ttc",
    ]
    for candidate in candidates:
        path = Path(candidate) if candidate else None
        if not path or not path.is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont(regular_name, str(path), subfontIndex=0))
            pdfmetrics.registerFont(TTFont(bold_name, str(path), subfontIndex=0))
            return regular_name, bold_name
        except Exception:
            continue
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light", "STSong-Light"


def build_styles(font: str, bold: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover": ParagraphStyle("cover", parent=base["Title"], fontName=bold, fontSize=26, leading=35, textColor=INK, spaceAfter=5 * mm),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontName=font, fontSize=11, leading=18, textColor=MUTED, spaceAfter=5 * mm),
        "section": ParagraphStyle("section", parent=base["Heading1"], fontName=bold, fontSize=18, leading=25, textColor=INK, spaceAfter=4 * mm),
        "subsection": ParagraphStyle("subsection", parent=base["Heading2"], fontName=bold, fontSize=11, leading=17, textColor=GREEN, spaceBefore=3 * mm, spaceAfter=2 * mm),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName=font, fontSize=9, leading=15, textColor=INK, wordWrap="CJK", spaceAfter=2.5 * mm),
        "bullet": ParagraphStyle("bullet", parent=base["BodyText"], fontName=font, fontSize=8.6, leading=14, leftIndent=5 * mm, firstLineIndent=-3 * mm, textColor=INK, wordWrap="CJK", spaceAfter=1.4 * mm),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontName=font, fontSize=7.4, leading=11, textColor=MUTED, wordWrap="CJK"),
        "table": ParagraphStyle("table", parent=base["BodyText"], fontName=font, fontSize=7.5, leading=11, textColor=INK, wordWrap="CJK"),
        "table_head": ParagraphStyle("table_head", parent=base["BodyText"], fontName=bold, fontSize=7.5, leading=11, textColor=colors.white, alignment=TA_CENTER, wordWrap="CJK"),
        "metric": ParagraphStyle("metric", parent=base["Normal"], fontName=bold, fontSize=16, leading=21, alignment=TA_CENTER, textColor=GREEN),
        "metric_label": ParagraphStyle("metric_label", parent=base["Normal"], fontName=font, fontSize=7.5, leading=11, alignment=TA_CENTER, textColor=MUTED),
    }


def para(text: str, styles: dict[str, ParagraphStyle], style: str = "body") -> Paragraph:
    return Paragraph(text, styles[style])


def bullet(text: str, styles: dict[str, ParagraphStyle]) -> Paragraph:
    return para(f"• {text}", styles, "bullet")


def image(name: str, width: float = 174 * mm) -> ReportImage:
    path = SCREENSHOT_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"缺少截图 {path}，请先运行 make contest-screenshots")
    height = width * 950 / 1600
    return ReportImage(str(path), width=width, height=height)


def cell(text: str, styles: dict[str, ParagraphStyle], header: bool = False) -> Paragraph:
    return para(text, styles, "table_head" if header else "table")


def styled_table(rows: list[list[Paragraph]], widths: list[float], header: bool = True) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.45, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, PAPER]),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), INK))
    table.setStyle(TableStyle(commands))
    return table


def draw_page(canvas, document, font: str) -> None:
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 15 * mm, PAGE_WIDTH - 18 * mm, 15 * mm)
    canvas.setFont(font, 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 9.5 * mm, "15分钟生活圈智能体检与规划助手 · 参赛作品介绍")
    canvas.drawRightString(PAGE_WIDTH - 18 * mm, 9.5 * mm, f"{document.page}")
    canvas.restoreState()


def story(styles: dict[str, ParagraphStyle], version: str) -> list:
    metrics = Table(
        [
            [para("2.3.0", styles, "metric"), para("140 + 48", styles, "metric"), para("0 / 0", styles, "metric"), para("13.2 s", styles, "metric")],
            [para("候选版本", styles, "metric_label"), para("后端 / 前端测试", styles, "metric_label"), para("运行镜像 Critical / High", styles, "metric_label"), para("真实热缓存复测", styles, "metric_label")],
        ],
        colWidths=[43.5 * mm] * 4,
    )
    metrics.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GREEN_LIGHT), ("BOX", (0, 0), (-1, -1), 0.7, GREEN), ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.white), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))

    architecture = styled_table(
        [
            [cell("交互层", styles, True), cell("分析与解释层", styles, True), cell("数据与外部服务层", styles, True)],
            [cell("Vue 3 + TypeScript\n地图工作台、报告、模拟、导出", styles), cell("FastAPI\n任务、网格、评分、建议、AI 证据约束", styles), cell("百度地图 / 离线快照\nSQLite 报告与步行缓存", styles)],
            [cell("ECharts\n柱图、雷达图、悬浮证据", styles), cell("扇形采样 + 二分细化\n4×4 网格盲区识别", styles), cell("Docker Compose\nNginx + Python Alpine", styles)],
        ],
        [58 * mm] * 3,
    )

    performance = styled_table(
        [
            [cell("实测场景", styles, True), cell("总耗时", styles, True), cell("地图 API 调用", styles, True), cell("缓存命中率", styles, True)],
            [cell("2.3.0 真实冷缓存", styles), cell("149.2 s", styles), cell("263", styles), cell("0%", styles)],
            [cell("2.3.0 真实热缓存", styles), cell("13.2 s", styles), cell("18", styles), cell("100%", styles)],
            [cell("历史 2.1.0 全缓存基线", styles), cell("12.5 s", styles), cell("18", styles), cell("100%", styles)],
        ],
        [60 * mm, 38 * mm, 38 * mm, 38 * mm],
    )

    requirement_map = styled_table(
        [
            [cell("赛题关注", styles, True), cell("作品响应", styles, True), cell("仓库证据", styles, True)],
            [cell("地图开发能力", styles), cell("地理编码、POI、步行矩阵、等时圈、GeoJSON 导出", styles), cell("算法一页纸与真实历史报告", styles)],
            [cell("AI 工具价值", styles), cell("证据约束解读、优先级建议、改善模拟；无密钥可降级", styles), cell("AI 接口、测试与演示路径 A6/A7", styles)],
            [cell("创新与实用性", styles), cell("把覆盖、盲区、建议、模拟和数据质量放进同一报告契约", styles), cell("标准报告、七类评分与前端工作台", styles)],
            [cell("开源与可复现", styles), cell("Apache-2.0、Compose、离线样例、质量/安全工作流", styles), cell("README、治理文档、证据索引", styles)],
        ],
        [38 * mm, 77 * mm, 59 * mm],
    )

    return [
        Spacer(1, 7 * mm),
        para("15分钟生活圈智能体检与规划助手", styles, "cover"),
        para("让社区服务可达性从“看起来合理”变成可计算、可解释、可追溯的空间体检报告", styles, "subtitle"),
        metrics,
        Spacer(1, 7 * mm),
        image("01-workspace-dark.png"),
        Spacer(1, 3 * mm),
        para(f"开源 AI 工具赛道 · 版本 {version} · 生成日期 {date.today().isoformat()} · Apache-2.0", styles, "small"),

        PageBreak(),
        para("1. 项目背景与解决方案", styles, "section"),
        para("城市生活圈规划经常停留在 POI 数量或直线半径层面，难以回答“居民步行能否真正到达、缺口在哪里、补什么最有效、结果是否可信”。本项目把地图能力、规则分析和 AI 解读组合成一个可复现的社区体检工作台。", styles),
        para("核心闭环", styles, "subsection"),
        bullet("选择地址或坐标，统一转换为百度 BD-09，并明确记录选点方式。", styles),
        bullet("检索七类民生设施，以真实步行时间生成等时圈并对 4×4 网格分级。", styles),
        bullet("输出数量、最近步行、空间分布三项可解释评分，以及带证据的规划候选点。", styles),
        bullet("对候选设施进行不改写原报告的改善模拟，再由 AI 只读报告证据生成摘要。", styles),
        bullet("将来源、缓存、失败、降级、耗时和调用量写入同一报告，支持 JSON、CSV、GeoJSON、PDF 导出。", styles),
        para("典型应用场景", styles, "subsection"),
        bullet("街道与社区：识别菜市场、药店、小学、医疗服务的重点服务盲区。", styles),
        bullet("规划汇报：用统一口径说明短板类别、问题网格、候选位置与预期改善。", styles),
        bullet("公众参与：用深浅主题工作台和可展开证据降低空间分析的理解门槛。", styles),
        Spacer(1, 3 * mm),
        image("02-isochrone-grid-light.png", 166 * mm),

        PageBreak(),
        para("2. 技术架构与算法", styles, "section"),
        architecture,
        para("地图 API 策略", styles, "subsection"),
        bullet("逐类别多关键词 POI 检索，按 uid、规范化名称和坐标去重；直线距离仅作候选预筛。", styles),
        bullet("步行矩阵按 100 点对分块，失败退化到逐对路线；24 小时坐标对缓存配合 QPS 节流、重试和超时分类。", styles),
        bullet("等时圈以 24/16 方向扇形采样并二分逼近步行阈值；有效边界不足时显式标记降级。", styles),
        para("评分与盲区口径", styles, "subsection"),
        bullet("重点盲区同时满足“最近同类设施步行超阈值”和“1 公里内无同类设施”；证据不足不参与结论。", styles),
        bullet("类别分 = 数量 40% + 最近步行 40% + 空间分布 20%；无效类别从综合分权重中排除。", styles),
        bullet("AI 仅解释已持久化报告实体，引用需通过校验；模型不可用时使用规则模板，不改变空间计算。", styles),
        Spacer(1, 3 * mm),
        image("03-blindspot-evidence.png", 166 * mm),

        PageBreak(),
        para("3. 创新点与赛题映射", styles, "section"),
        requirement_map,
        para("差异化创新", styles, "subsection"),
        bullet("从“半径覆盖”提升到“路网步行 + 网格证据”，每个盲区可回看最近设施、时间、距离、来源和置信度。", styles),
        bullet("模拟以不可变来源报告为基线，只重算受影响类别，明确区分事实、假设与改善量。", styles),
        bullet("数据质量不是附录，而是界面和导出报告的一等信息；部分失败不会被包装成完整结论。", styles),
        bullet("离线合成快照、历史缓存种子与最新真实调用始终分开披露，评审无需真实密钥也能复现完整交互。", styles),
        Spacer(1, 3 * mm),
        image("04-score-breakdown.png", 166 * mm),

        PageBreak(),
        para("4. 验证、性能与工程质量", styles, "section"),
        performance,
        para("验证结论", styles, "subsection"),
        bullet("本地候选版：后端 140 项、前端 48 项测试通过，并通过 Ruff、ESLint、类型检查、Vite 构建和容器冒烟。", styles),
        bullet("Python 生产/开发依赖和 npm high/critical 审计均为 0；API/Web 最终运行镜像经 Trivy 与 Grype 复扫为 0 Critical / 0 High。", styles),
        bullet("沙涌长盛花园 64 格核查属于百度同源一致性证据，不宣传为跨来源准确率或整体泛化能力。", styles),
        bullet("真实性边界：2.3.0 已完成受控真实复跑并归档；独立来源准确率、许可证和外部服务条款仍需人工确认。", styles),
        Spacer(1, 4 * mm),
        image("08-ai-interpretation.png", 166 * mm),

        PageBreak(),
        para("5. 开源治理、限制与长期规划", styles, "section"),
        para("治理与交付", styles, "subsection"),
        bullet("GitHub `PengJunPJ/life-circle-assistant` 是唯一权威参赛仓库；许可证为 Apache-2.0。", styles),
        bullet("CONTRIBUTING、SECURITY、CODEOWNERS、维护者职责、ADR、证据索引和发布工作流均在仓库内可追溯。", styles),
        bullet("发布标签触发质量、依赖审计、容器构建、SBOM 与 provenance；正式锁版仍以远端门禁为准。", styles),
        para("已知限制", styles, "subsection"),
        bullet("当前主分析为百度单源；高德只作为默认关闭的辅助观察，没有书面许可和人工标签前不宣称多源准确率。", styles),
        bullet("离线快照为合成样例；真实模式受配额、网络、缓存和地图服务条款影响。", styles),
        bullet("产品是功能型 Beta，不含账号、多租户、监控和备份，不作为规划审批依据。", styles),
        para("后续路线", styles, "subsection"),
        bullet("取得高德书面许可并完成 50–100 对真实双源人工标签，再计算 precision / recall / F1。", styles),
        bullet("扩展 2–3 个不同路网社区的独立核查，持续生成正式 SBOM 并复核逐包许可证。", styles),
        Spacer(1, 3 * mm),
        image("09-simulation.png", 166 * mm),

        PageBreak(),
        para("6. 一键复现与评审路径", styles, "section"),
        para("在仓库 `life-circle-assistant/` 下执行：", styles),
        para("<font name='Courier'>cp .env.example .env<br/>docker compose up --build -d --wait<br/>make quality<br/>make contest-screenshots<br/>make contest-brief<br/>make contest-preflight</font>", styles),
        para("建议评审顺序", styles, "subsection"),
        bullet("README 启动离线样例，按 docs/contest/demo-script.md 完成路径 A。", styles),
        bullet("阅读 docs/contest/algorithm-overview.md 与 evidence-index.md，核对算法、证据状态和限制。", styles),
        bullet("查看 docs/contest/screenshots/ 和本作品介绍；真实模式演示必须同时显示服务探活与数据质量。", styles),
        para("提交前仍需人工完成", styles, "subsection"),
        bullet("当前候选版真实百度复跑报告与真实步行路线截图。", styles),
        bullet("3–5 分钟演示视频、报名/邮件提交回执。", styles),
        bullet("GitHub 候选提交远端 CI、合并 main、创建并推送 v2.3.0 标签与 Release。", styles),
        bullet("高德许可和双源人工标签属于后续证据成熟度工作，不伪装成本次已完成能力。", styles),
        Spacer(1, 6 * mm),
        image("12-data-quality.png", 166 * mm),
    ]


def main() -> None:
    version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    font, bold = register_fonts()
    styles = build_styles(font, bold)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(OUTPUT_PATH),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=20 * mm,
        title="15分钟生活圈智能体检与规划助手参赛作品介绍",
        author="15分钟生活圈智能体检与规划助手",
        subject="2026 上海开源软件应用创新大赛参赛材料",
    )
    document.build(
        story(styles, version),
        onFirstPage=lambda canvas, doc: draw_page(canvas, doc, font),
        onLaterPages=lambda canvas, doc: draw_page(canvas, doc, font),
    )
    print(f"已生成 {OUTPUT_PATH.relative_to(PROJECT_ROOT)}（{OUTPUT_PATH.stat().st_size // 1024} KiB）")


if __name__ == "__main__":
    main()
