from __future__ import annotations

import math
from typing import Any

from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Flowable

INK = colors.HexColor("#173D36")
MUTED = colors.HexColor("#60766F")
LINE = colors.HexColor("#D9E2DE")
GREEN = colors.HexColor("#2F7D68")
MISSING = colors.HexColor("#E3E9E6")
COMPONENTS = [("quantity", "数量"), ("walking_time", "步行时间"), ("spatial_distribution", "空间分布")]


def score_color(score: float | None) -> colors.Color:
    if score is None:
        return MISSING
    stops = [colors.HexColor(value) for value in ["#D77C69", "#E4BC67", "#72BAA0", "#287B68"]]
    position = max(0.0, min(100.0, score)) / 100 * (len(stops) - 1)
    index = min(int(position), len(stops) - 2)
    fraction = position - index
    first, second = stops[index], stops[index + 1]
    return colors.Color(
        first.red + (second.red - first.red) * fraction,
        first.green + (second.green - first.green) * fraction,
        first.blue + (second.blue - first.blue) * fraction,
    )


class ReportScoreChart(Flowable):
    """只读取报告评分的矢量图；缺失数据单独标记，不生成替代评分。"""

    def __init__(self, scores: list[dict[str, Any]], kind: str, width: float, height: float, font_name: str):
        super().__init__()
        self.scores = scores
        self.kind = kind
        self.width = width
        self.height = height
        self.font_name = font_name

    def _text(self, x: float, y: float, text: str, align: str = "left", color: colors.Color = INK, size: float = 8):
        self.canv.setFillColor(color)
        self.canv.setFont(self.font_name, size)
        method = {
            "left": self.canv.drawString,
            "right": self.canv.drawRightString,
            "center": self.canv.drawCentredString,
        }[align]
        method(x, y, text)

    def _label(self, item: dict[str, Any], max_width: float) -> str:
        text = str(item.get("label") or item.get("category") or "未命名")
        while len(text) > 1 and pdfmetrics.stringWidth(text, self.font_name, 8) > max_width:
            text = text[:-2] + "…"
        return text

    def draw(self):
        self.canv.saveState()
        if not self.scores:
            self._text(self.width / 2, self.height / 2, "暂无设施评分数据", "center", MUTED)
        elif self.kind == "bar":
            self._bar()
        elif self.kind == "radar":
            self._radar()
        else:
            self._heatmap()
        self.canv.restoreState()

    def _bar(self):
        left, right, bottom, top = 58, self.width - 30, 25, self.height - 8
        step = (top - bottom) / len(self.scores)
        self.canv.setStrokeColor(LINE)
        self.canv.setLineWidth(0.4)
        for tick in [0, 25, 50, 75, 100]:
            x = left + (right - left) * tick / 100
            self.canv.line(x, bottom, x, top)
            self._text(x, bottom - 12, str(tick), "center", MUTED, 7)
        for row, item in enumerate(self.scores):
            y = top - (row + 0.5) * step
            self._text(left - 6, y - 3, self._label(item, left - 8), "right")
            score = item.get("score")
            if score is None:
                self._text(right, y - 3, "无数据", "right", MUTED, 7)
                continue
            self.canv.setFillColor(GREEN)
            self.canv.roundRect(left, y - 5, (right - left) * score / 100, 10, 2, fill=1, stroke=0)
            self._text(left + (right - left) * score / 100 + 4, y - 3, str(score), size=8)

    def _radar(self):
        valid = [item for item in self.scores if item.get("score") is not None]
        if len(valid) < 3:
            self._text(self.width / 2, self.height * 0.6, f"当前 {len(valid)} 类有效评分", "center", MUTED)
            self._text(self.width / 2, self.height * 0.6 - 18, "雷达图至少需要 3 类有效评分", "center", MUTED)
            return
        cx, cy = self.width / 2, self.height / 2 + 4
        radius = min(self.width * 0.27, self.height * 0.32)
        angles = [math.pi / 2 - index * 2 * math.pi / len(valid) for index in range(len(valid))]

        def path_for(values: list[float]):
            path = self.canv.beginPath()
            for index, (angle, value) in enumerate(zip(angles, values, strict=True)):
                point = cx + math.cos(angle) * radius * value, cy + math.sin(angle) * radius * value
                if index == 0:
                    path.moveTo(*point)
                else:
                    path.lineTo(*point)
            path.close()
            return path

        self.canv.setStrokeColor(LINE)
        self.canv.setLineWidth(0.5)
        for tick in [0.2, 0.4, 0.6, 0.8, 1]:
            self.canv.drawPath(path_for([tick] * len(valid)), stroke=1, fill=0)
        for angle, item in zip(angles, valid, strict=True):
            x, y = cx + math.cos(angle) * radius, cy + math.sin(angle) * radius
            self.canv.line(cx, cy, x, y)
            lx, ly = cx + math.cos(angle) * (radius + 10), cy + math.sin(angle) * (radius + 10)
            align = "center" if abs(math.cos(angle)) < 0.2 else "left" if math.cos(angle) > 0 else "right"
            self._text(lx, ly, self._label(item, 60), align, size=8)
            self._text(lx, ly - 11, str(item["score"]), align, MUTED, 7)
        self._text(cx + 3, cy + radius - 10, "100", color=MUTED, size=6)
        self._text(cx + 3, cy - 2, "0", color=MUTED, size=6)
        self.canv.setFillColor(colors.HexColor("#D4EBE2"))
        self.canv.setStrokeColor(GREEN)
        self.canv.setLineWidth(1.5)
        self.canv.drawPath(path_for([item["score"] / 100 for item in valid]), stroke=1, fill=1)
        for angle, item in zip(angles, valid, strict=True):
            self.canv.setFillColor(GREEN)
            self.canv.circle(
                cx + math.cos(angle) * radius * item["score"] / 100,
                cy + math.sin(angle) * radius * item["score"] / 100,
                2,
                fill=1,
                stroke=0,
            )
        if len(valid) != len(self.scores):
            self._text(cx, 5, "缺失评分的类别未纳入雷达图", "center", MUTED, 7)

    def _heatmap(self):
        left, top, bottom = 70, self.height - 25, 35
        cell_width = (self.width - left - 5) / len(COMPONENTS)
        cell_height = (top - bottom) / len(self.scores)
        for column, (_, label) in enumerate(COMPONENTS):
            self._text(left + (column + 0.5) * cell_width, top + 10, label, "center", size=9)
        for row, item in enumerate(self.scores):
            y = top - (row + 1) * cell_height
            self._text(left - 8, y + cell_height / 2 - 3, self._label(item, left - 10), "right", size=8)
            components = {component.get("key"): component.get("score") for component in item.get("components", [])}
            for column, (key, _) in enumerate(COMPONENTS):
                score = components.get(key)
                self.canv.setFillColor(score_color(score))
                self.canv.rect(left + column * cell_width, y, cell_width - 2, cell_height - 2, fill=1, stroke=0)
                self._text(
                    left + (column + 0.5) * cell_width,
                    y + cell_height / 2 - 3,
                    "—" if score is None else str(score),
                    "center",
                    colors.white if score is not None and score >= 75 else INK,
                    9,
                )
        for index in range(50):
            self.canv.setFillColor(score_color(index * 100 / 49))
            self.canv.rect(left + index * 3, 9, 3, 8, fill=1, stroke=0)
        self._text(left - 5, 9, "0", "right", MUTED, 7)
        self._text(left + 155, 9, "100", color=MUTED, size=7)
        self._text(self.width - 5, 9, "灰色 —：无数据", "right", MUTED, 8)
