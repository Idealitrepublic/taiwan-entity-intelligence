"""Offline PDF renderer for the existing evidence-backed report projection."""
from html import escape
from io import BytesIO
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer

FONT = "TEI-NotoSansTC"
FONT_PATH = Path(__file__).resolve().parents[1] / "assets/fonts/NotoSansTC-Regular.ttf"
FONT_LOCK = RLock()


def _register_font():
    with FONT_LOCK:
        if FONT not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(FONT, str(FONT_PATH)))


def render_report_pdf(report):
    # JSON retains the full projection; PDF emphasizes readable findings and sources.
    from src.report_presentation import present_report

    _register_font()
    output = BytesIO()
    page_width, page_height = landscape(A4)
    margin = 12 * mm
    width = page_width - margin * 2
    view = present_report(report)
    normal = ParagraphStyle(
        "Body", fontName=FONT, fontSize=9, leading=14, wordWrap="CJK",
        splitLongWords=True, textColor=colors.HexColor("#17202a"))
    heading = ParagraphStyle(
        "Heading", parent=normal, fontSize=13, leading=20, spaceBefore=12,
        spaceAfter=8, keepWithNext=True)
    title = ParagraphStyle("Title", parent=heading, fontSize=19, leading=27)
    muted = ParagraphStyle("Muted", parent=normal, textColor=colors.HexColor("#5c6975"))

    def paragraph(value, style=normal, key=""):
        text = escape(str(value)).replace("\n", "<br/>")
        parsed = urlsplit(str(value)) if "URL" in key else None
        # All content is escaped. No images, files or external resources are loaded.
        if parsed and parsed.scheme in ("http", "https") and parsed.netloc:
            text = f'<link href="{escape(str(value), quote=True)}" color="#1769aa">{text}</link>'
        return Paragraph(text, style)

    story = [paragraph(report["title"], title), paragraph(report["methodology"]),
             paragraph(f"產生時間 / Generated at: {report['generated_at']}", muted),
             Spacer(1, 7), paragraph("調查摘要 / Investigation summary", heading)]
    summary = "    ·    ".join(f"{label}: {count}" for label, count in view["summary"].items())
    story.extend([paragraph(summary), Spacer(1, 5)])
    for warning in view["warnings"]:
        story.append(paragraph(warning, muted))

    def table(facts):
        rows = [[paragraph("Field / 欄位"), paragraph("Value / 內容")]]
        rows.extend([paragraph(key, muted), paragraph(value, key=key)] for key, value in facts)
        if len(rows) == 1:
            return
        result = LongTable(rows, colWidths=[width * .28, width * .72],
                           repeatRows=1, splitByRow=1, splitInRow=1,
                           hAlign="LEFT")
        result.setStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9eef4")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f7f9fb")]),
            ("LINEBELOW", (0, 0), (-1, -1), .25, colors.HexColor("#dce3e8")),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])
        story.extend([result, Spacer(1, 8)])

    for section in view["sections"]:
        story.append(paragraph(f"{section['title']} · {len(section['items'])} 筆", heading))
        for index, item in enumerate(section["items"], 1):
            story.append(paragraph(f"{index}. {item['title']}", muted))
            table(item["facts"])
    if view["empty"]:
        story.append(paragraph("尚無已發布紀錄 / No published records", heading))
        story.append(paragraph("、".join(view["empty"]), muted))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.setFillColor(colors.HexColor("#5c6975"))
        canvas.drawString(margin, 6 * mm, "T.E.I. · Evidence-backed public records / 公開資料與證據")
        canvas.drawRightString(page_width - margin, 6 * mm, f"Page / 頁 {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        output, pagesize=(page_width, page_height), leftMargin=margin,
        rightMargin=margin, topMargin=margin, bottomMargin=margin,
        title=report["title"], author="T.E.I.", pageCompression=1)
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
