"""复核作品介绍正文、截图嵌入与文本边界，输出逐页联系表。"""
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw
from pypdf import PdfReader

app = Path(__file__).resolve().parents[1]
root = app.parent
pdf = app / "docs/output/作品介绍文档.pdf"
preview = root / ".scratch/work-introduction/preview/current-real"
preview.mkdir(parents=True, exist_ok=True)
subprocess.run(["pdftoppm", "-scale-to", "1200", "-png", str(pdf), str(preview / "page")], check=True)
subprocess.run(["pdftotext", "-bbox", str(pdf), str(preview / "bounds.html")], check=True)
reader = PdfReader(pdf)
normalize = lambda s: re.sub(r"\s+", "", s)
text = normalize("".join(p.extract_text() for p in reader.pages))
source = (app / "docs/contest/submission/作品介绍文档.md").read_text()
count = 0
for chunk in source.split("<!-- page -->")[1:]:
    for line in chunk.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ">", ":::" , "![", "```", "| ---")):
            continue
        values = line.strip("|").split("|") if line.startswith("|") else [line.removeprefix("- ")]
        for value in values:
            if value.strip():
                assert normalize(value) in text, f"正文缺失：{value}"
                count += 1
ns = {"x": "http://www.w3.org/1999/xhtml"}
bbox = ET.parse(preview / "bounds.html")
words = 0
for page in bbox.findall(".//x:page", ns):
    width, height = float(page.attrib["width"]), float(page.attrib["height"])
    for word in page.findall(".//x:word", ns):
        a = word.attrib
        assert 0 <= float(a["xMin"]) <= float(a["xMax"]) <= width
        assert 0 <= float(a["yMin"]) <= float(a["yMax"]) <= height
        words += 1
shots = app / "docs/contest/submission/screenshots-20261015"
embedded = {}
for page_number, filename in [(1, "01-real-map-report.png"), (3, "01-real-map-report.png"), (6, "02-real-ai-summary.png"), (7, "04-real-simulation.png")]:
    original = Image.open(shots / filename).convert("RGB")
    matches = [im for im in reader.pages[page_number - 1].images if im.image.size == original.size and ImageChops.difference(original, im.image.convert("RGB")).getbbox() is None]
    assert matches, f"第{page_number}页不是新截图：{filename}"
    embedded[str(page_number)] = filename
files = sorted(preview.glob("page-*.png"))
sheet = Image.new("RGB", (1100, 350 * 2), "#dfe7e5")
draw = ImageDraw.Draw(sheet)
for i, file in enumerate(files):
    im = Image.open(file).convert("RGB")
    im.thumbnail((208, 318))
    x, y = (i % 5) * 220 + 6, (i // 5) * 350 + 20
    sheet.paste(im, (x, y))
    draw.text((x, y - 14), str(i + 1), fill="#173b3d")
sheet.save(preview / "contact-sheet.png")
check = root / ".scratch/work-introduction/verification.json"
result = json.loads(check.read_text())
result.update({"paragraphs_and_cells_checked": count, "words_within_page": words, "embedded_current_screenshots": embedded, "all_pages_rendered": True, "preview": str(preview.relative_to(root))})
check.write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False, indent=2))
