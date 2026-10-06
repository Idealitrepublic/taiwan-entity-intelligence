"""Real PDF regressions: binary transport, font embedding and long-content pages."""
from io import BytesIO
from pathlib import Path
import re
import unittest
from unittest.mock import Mock, patch

from pypdf import PdfReader

from app import app
from src.report_pdf import render_report_pdf
from src.reports import dispatch_report_api

ENTITY = "11111111-1111-4111-8111-111111111111"


def report():
    return {"title": "T.E.I. 大魯閣實業股份有限公司 — Report",
            "methodology": "公開紀錄不等於違法結論。 Evidence-backed facts only.",
            "report_type": "ENTITY", "generated_at": "2026-10-06T12:00:00Z",
            "coverage": {"relationship_truncated": False},
            "entity_profiles": [{"id": ENTITY, "display_name": "大魯閣實業股份有限公司"}],
            "penalties": [{"disposition": "府勞動字第1130101133號", "amount": 50000}],
            "sources": [{"source": "勞動部", "source_url": "https://data.gov.tw/dataset/109896",
                         "retrieved_at": "2026-10-06T08:01:44Z"}],
            "relationship_graph": {"nodes": [{"id": ENTITY}], "edges": []}}


class ReportPDFTests(unittest.TestCase):
    def test_real_landscape_pdf_embeds_chinese_font_and_source_link(self):
        data = render_report_pdf(report())
        self.assertTrue(data.startswith(b"%PDF-"))
        reader = PdfReader(BytesIO(data))
        text = "".join(page.extract_text() for page in reader.pages)
        for value in ("大魯閣實業股份有限公司", "府勞動字第1130101133號", "50000",
                      "2026-10-06T08:01:44Z", "Sources / 來源"):
            self.assertIn(value, text)
        self.assertTrue(all(float(p.mediabox.width) > float(p.mediabox.height) for p in reader.pages))
        fonts = [f.get_object() for p in reader.pages for f in p['/Resources']['/Font'].get_object().values()]
        self.assertTrue(any('/FontDescriptor' in f and '/FontFile2' in f['/FontDescriptor'].get_object()
                            for f in fonts))
        urls = [a.get_object().get('/A', {}).get('/URI') for p in reader.pages
                for a in p.get('/Annots', [])]
        self.assertIn('https://data.gov.tw/dataset/109896', urls)

    def test_long_rows_split_across_pages_without_truncation(self):
        value = report()
        english = "SourceRecordIdentifier" * 60
        chinese = "中文長段落必須保留完整內容並正確分頁。" * 120
        url = "https://data.gov.tw/dataset/109896?record=" + "a" * 500
        value['entity_profiles'][0].update(note=chinese, identifier=english)
        value['sources'][0]['source_url'] = url
        reader = PdfReader(BytesIO(render_report_pdf(value)))
        # Repeated table headers and page footers are not part of the long cell.
        # Remove only known chrome before joining text split over page boundaries.
        pages = []
        for page in reader.pages:
            content = page.extract_text()
            content = content.replace(
                'T.E.I. · Evidence-backed public records / 公開資料與證據', '')
            content = re.sub(r'Page / 頁 \d+', '', content)
            content = re.sub(r'Field / 欄位\s+Value / 內容', '', content)
            pages.append(''.join(content.split()))
        text = ''.join(pages)
        self.assertGreater(len(reader.pages), 1)
        self.assertIn(english, text)
        self.assertIn(chinese, text)
        self.assertIn(url, text)

    def test_pdf_format_preserves_auth_and_calls_same_report_projection(self):
        service = Mock()
        service.entity_report.return_value = report()
        code, data, mime = dispatch_report_api(
            f'/api/v1/reports/entity/{ENTITY}', {'format': ['pdf']}, service=service)
        self.assertEqual((code, mime), (200, 'application/pdf'))
        self.assertTrue(data.startswith(b'%PDF-'))
        code, _, mime = dispatch_report_api(
            f'/api/v1/reports/workspace/{ENTITY}', {'format': ['pdf']}, service=service)
        self.assertEqual((code, mime), (401, None))
        service.workspace_report.assert_not_called()

    def test_wsgi_delivers_binary_attachment_and_head_has_no_body(self):
        binary = render_report_pdf(report())
        with patch('app.dispatch_report_api', return_value=(200, binary, 'application/pdf')):
            for method in ('GET', 'HEAD'):
                captured = []
                chunks = app({'REQUEST_METHOD': method,
                              'PATH_INFO': f'/api/v1/reports/entity/{ENTITY}',
                              'QUERY_STRING': 'format=pdf'},
                             lambda status, headers: captured.append((status, dict(headers))))
                self.assertEqual(b''.join(chunks), binary if method == 'GET' else b'')
                self.assertEqual(captured[0][0], '200 OK')
                headers = captured[0][1]
                self.assertEqual(headers['Content-Type'], 'application/pdf')
                self.assertEqual(headers['Content-Length'], str(len(binary)))
                self.assertIn('.pdf', headers['Content-Disposition'])
                self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_ui_download_is_pdf_but_preview_remains_html(self):
        html = (Path(__file__).resolve().parents[1] / 'web/index.html').read_text()
        self.assertIn("format=download?'pdf':'html'", html)
        self.assertIn("blob.slice(0,5).text())!=='%PDF-'", html)
        self.assertIn('tei-${scope}-${id}.pdf', html)
        self.assertNotIn('tei-${scope}-${id}.html', html)
