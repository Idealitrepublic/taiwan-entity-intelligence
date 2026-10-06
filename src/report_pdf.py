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


def _fields(value, prefix=""):
    """Flatten hierarchy into full-width rows, never nested narrow tables."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "content_hash":
                continue
            name = str(key).replace("_", " ")
            path = f"{prefix} / {name}" if prefix else name
            yield from _fields(child, path)
    elif isinstance(value, list):
        if not value:
            yield prefix, "No published records / 目前無已發布紀錄"
        for index, child in enumerate(value, 1):
            yield from _fields(child, f"{prefix} [{index}]")
    else:
        yield prefix, "—" if value is None or value == "" else str(value)


def render_report_pdf(report):
    # Imported here to keep the HTML/JSON path independent of the PDF dependency.
    from src.reports import SECTION_TITLES

    _register_font()
    output = BytesIO()
    page_width, page_height = landscape(A4)
    margin = 12 * mm
    width = page_width - margin * 2
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
        parsed = urlsplit(str(value)) if key.endswith("source url") else None
        # All content is escaped. No images, files or external resources are loaded.
        if parsed and parsed.scheme in ("http", "https") and parsed.netloc:
            text = f'<link href="{escape(str(value), quote=True)}" color="#1769aa">{text}</link>'
        return Paragraph(text, style)

    story = [paragraph(report["title"], title),
             paragraph(report["methodology"]), Spacer(1, 6),
             paragraph(f"Report type / 類型: {report['report_type']}"),
             paragraph(f"Generated at / 產生時間: {report['generated_at']}"),
             paragraph("Coverage / 範圍", heading)]

    def table(value):
        rows = [[paragraph("Field / 欄位"), paragraph("Value / 內容")]]
        rows.extend([paragraph(key, muted), paragraph(child, key=key)]
                    for key, child in _fields(value))
        if len(rows) == 1:
            story.append(paragraph("No published records / 目前無已發布紀錄", muted))
            return
        result = LongTable(rows, colWidths=[width * .29, width * .71],
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

    table(report["coverage"])
    sections = list(SECTION_TITLES)
    if report["report_type"] == "WORKSPACE":
        sections = [("workspace_items", "Saved Workspace Items / 已收藏項目"),
                    ("saved_evidence", "Saved Evidence / 已收藏證據"), *sections]
    for key, label in sections:
        story.append(paragraph(label, heading))
        values = report.get(key)
        if not values:
            story.append(paragraph("No published records / 目前無已發布紀錄", muted))
            continue
        if isinstance(values, list):
            for index, row in enumerate(values, 1):
                story.append(paragraph(f"{index}.", muted))
                table(row)
        else:
            table(values)

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
