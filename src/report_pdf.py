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
from reportlab.platypus import Flowable, KeepTogether, LongTable, Paragraph, SimpleDocTemplate, Spacer

FONT = "TEI-NotoSansTC"
FONT_PATH = Path(__file__).resolve().parents[1] / "assets/fonts/NotoSansTC-Regular.ttf"
FONT_LOCK = RLock()


class RelationshipDiagram(Flowable):
    """A page-safe vector diagram of every edge in one bounded graph chunk."""

    def __init__(self, rows, width, font):
        super().__init__()
        self.rows = rows
        self.width = width
        self.font = font
        self.height = 0
        self._layout = []

    def wrap(self, avail_width, avail_height):
        style = ParagraphStyle("Diagram label", fontName=self.font, fontSize=9,
                               leading=13, wordWrap="CJK", splitLongWords=True)
        self._layout = []
        for source, relation, target, source_type, target_type in self.rows:
            texts = [Paragraph(escape(str(value)), style) for value in (source, relation, target)]
            heights = [item.wrap(218 if index != 1 else 185, 500)[1]
                       for index, item in enumerate(texts)]
            row_height = max(54, max(heights) + 28)
            self._layout.append((texts, heights, row_height, source_type, target_type))
        self.height = sum(item[2] for item in self._layout) + 10
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        y = self.height - 5
        palette = {"Company": "#5d8fd9", "Person": "#4ab989", "Politician": "#4ab989",
                   "Penalty": "#dc687e", "Judgment": "#ac78e2", "Contract": "#dcae50",
                   "GovernmentAgency": "#dcae50"}
        for texts, heights, row_height, source_type, target_type in self._layout:
            y -= row_height
            canvas.setFillColor(colors.HexColor("#f5f8fb"))
            canvas.roundRect(0, y + 3, self.width, row_height - 5, 7, stroke=0, fill=1)
            line_y = y + 12
            for x, radius, kind in ((243, 5, source_type), (self.width - 243, 5, target_type)):
                canvas.setFillColor(colors.HexColor(palette.get(kind, "#8192a4")))
                canvas.circle(x, line_y, radius, stroke=0, fill=1)
            canvas.setStrokeColor(colors.HexColor("#8095ac"))
            canvas.setLineWidth(1.3)
            canvas.line(250, line_y, self.width - 250, line_y)
            canvas.line(self.width - 255, line_y + 4, self.width - 250, line_y)
            canvas.line(self.width - 255, line_y - 4, self.width - 250, line_y)
            for index, x in enumerate((14, 255, self.width - 233)):
                text_y = y + row_height - heights[index] - 5 if index == 1 else y + (row_height - heights[index]) / 2
                texts[index].drawOn(canvas, x, text_y)
        canvas.setStrokeColor(colors.HexColor("#d7e1eb"))


def graph_diagrams(graph, width):
    from src.report_presentation import LABELS

    nodes = {node.get("id"): node for node in (graph or {}).get("nodes", []) if node.get("id")}
    rows, connected = [], set()
    for item in (graph or {}).get("edges", []):
        edge = item.get("relationship") or item
        source_id = edge.get("source_entity_id") or edge.get("source")
        target_id = edge.get("target_entity_id") or edge.get("target")
        source = nodes.get(source_id) or item.get("source_entity") or {}
        target = nodes.get(target_id) or item.get("target_entity") or {}
        connected.update((source_id, target_id))
        rows.append((source.get("display_name") or source.get("canonical_name") or source_id or "—",
                     LABELS.get(edge.get("relationship_type"),
                                "公開關係 / " + str(edge.get("relationship_type") or "Public link").replace("_", " ").title()),
                     target.get("display_name") or target.get("canonical_name") or target_id or "—",
                     source.get("entity_type"), target.get("entity_type")))
    for node_id, node in nodes.items():
        if node_id not in connected:
            rows.append((node.get("display_name") or node.get("canonical_name") or node_id,
                         "尚無載入關係 / No loaded link", "—", node.get("entity_type"), None))
    return [RelationshipDiagram(rows[index:index + 5], width, FONT)
            for index in range(0, len(rows), 5)]


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
        if section["key"] == "relationship_graph":
            diagrams = graph_diagrams(report.get("relationship_graph"), width)
            intro = [paragraph(f"{section['title']} · {len(section['items'])} 筆", heading),
                     paragraph("下圖逐條呈現本報告已載入的全部節點與關係；資料量受下方範圍提示限制。 / All loaded nodes and links are diagrammed; see scope limits.", muted)]
            if diagrams:
                story.append(KeepTogether(intro + diagrams[:1]))
                story.extend(diagrams[1:])
            else:
                story.extend(intro)
        else:
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
