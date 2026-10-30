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
    def test_compact_workspace_retains_all_facts_without_a_page_per_saved_item(self):
        from copy import deepcopy
        value = report()
        value['report_type'] = 'WORKSPACE'
        value['workspace_items'] = [
            {'item_type':kind, 'title':f'收藏{kind}', 'created_at':'2026-10-30T00:00:00Z',
             **({'note_text':'中英文筆記完整保留 / Full note retained'} if kind=='NOTE' else {})}
            for kind in ('ENTITY','GRAPH','RELATIONSHIP','EVIDENCE','SOURCE','NOTE')]
        value['saved_evidence'] = [{'title':'已收藏官方證據', **value['sources'][0]}]
        original=deepcopy(value)
        reader=PdfReader(BytesIO(render_report_pdf(value)))
        text=''.join(page.extract_text() for page in reader.pages)
        for token in ('大魯閣實業股份有限公司','50,000','府勞動字第1130101133號',
                      '已收藏官方證據','Full note retained','來源 / Sources',
                      '關係圖 / Relationship Graph'):
            self.assertIn(token,text)
        self.assertLessEqual(len(reader.pages),5)
        self.assertEqual(value,original)

    def test_source_rows_keep_citations_together_and_known_provider_is_bilingual(self):
        value=report()
        value['sources']=[{'title':f'官方來源{i}', 'source_name':'MOL/penalties',
                          'source_url':f'https://example.gov.tw/record/{i}',
                          'source_locator':{'violation':('公開公告內容，不自行判定。' * 32)},
                          'retrieved_at':'2026-10-30T00:00:00Z'} for i in range(7)]
        reader=PdfReader(BytesIO(render_report_pdf(value)))
        text=''.join(page.extract_text() for page in reader.pages)
        self.assertIn('勞動部裁罰 / MOL penalties',text)
        self.assertNotIn('MOL/penalties',text)
        for i in range(7):
            self.assertIn(f'官方來源{i}',text)
        # A source header may repeat on the next page, never twice on one page.
        for page in reader.pages:
            self.assertLessEqual(page.extract_text().count('來源 / Sources · 7 筆'),1)

    def test_real_landscape_pdf_embeds_chinese_font_and_source_link(self):
        data = render_report_pdf(report())
        self.assertTrue(data.startswith(b"%PDF-"))
        reader = PdfReader(BytesIO(data))
        text = "".join(page.extract_text() for page in reader.pages)
        for value in ("大魯閣實業股份有限公司", "府勞動字第1130101133號", "50,000",
                      "2026-10-06 16:01:44", "來源 / Sources"):
            self.assertIn(value, text)
        self.assertTrue(all(float(p.mediabox.width) > float(p.mediabox.height) for p in reader.pages))
        fonts = [f.get_object() for p in reader.pages for f in p['/Resources']['/Font'].get_object().values()]
        self.assertTrue(any('/FontDescriptor' in f and '/FontFile2' in f['/FontDescriptor'].get_object()
                            for f in fonts))
        urls = [a.get_object().get('/A', {}).get('/URI') for p in reader.pages
                for a in p.get('/Annots', [])]
        self.assertIn('https://data.gov.tw/dataset/109896', urls)

    def test_pdf_draws_every_loaded_relationship_with_bilingual_type(self):
        value = report()
        value['relationship_graph'] = {
            'nodes': [{'id': 'a', 'display_name': '中華電信', 'entity_type': 'Company'},
                      {'id': 'b', 'display_name': '採購機關', 'entity_type': 'GovernmentAgency'},
                      {'id': 'c', 'display_name': '關係人', 'entity_type': 'Person'}],
            'edges': [
                {'relationship': {'source_entity_id': 'a', 'target_entity_id': 'b',
                                  'relationship_type': 'CONTRACT_WITH'},
                 'source_entity': {'display_name': '中華電信'},
                 'target_entity': {'display_name': '採購機關'}},
                {'relationship': {'source_entity_id': 'a', 'target_entity_id': 'c',
                                  'relationship_type': 'CORPORATE_DIRECTOR_LINK'},
                 'source_entity': {'display_name': '中華電信'},
                 'target_entity': {'display_name': '關係人'}}]}
        pdf = PdfReader(BytesIO(render_report_pdf(value)))
        text = ''.join(page.extract_text() for page in pdf.pages)
        self.assertIn('採購機關', text)
        self.assertIn('關係人', text)
        self.assertIn('政府標案 / Government contract', text)
        self.assertIn('法人董監事代表 / Corporate director link', text)

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
            content = re.sub(r'欄位 / Field\s+內容 / Value', '', content)
            pages.append(''.join(content.split()))
        text = ''.join(pages)
        self.assertGreater(len(reader.pages), 1)
        self.assertIn(english, text)
        self.assertIn(chinese, text)
        self.assertIn(url, text)

    def test_structured_source_locator_and_distinct_record_refs_render_safely(self):
        value = report()
        value['sources'] = [
            {'title': '官方一號紀錄', 'source_url': 'https://example.gov.tw/records',
             'source_locator': {'dataset': 'labor', 'record': 1},
             'retrieved_at': '2026-10-06T08:01:44Z'},
            {'title': '官方二號紀錄', 'source_url': 'https://example.gov.tw/records',
             'source_locator': {'dataset': 'labor', 'record': 2},
             'retrieved_at': '2026-10-06T08:01:44Z'},
        ]
        reader = PdfReader(BytesIO(render_report_pdf(value)))
        text = ''.join(page.extract_text() for page in reader.pages)
        for token in ('S001', 'S002', '官方一號紀錄', '官方二號紀錄', '2026-10-06 16:01:44'):
            self.assertIn(token, text)

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

    def test_ui_preview_and_download_are_actual_pdf(self):
        html = (Path(__file__).resolve().parents[1] / 'web/index.html').read_text()
        self.assertIn('?format=pdf', html)
        self.assertNotIn("format=download?'pdf':'html'", html)
        self.assertIn("blob.slice(0,5).text())!=='%PDF-'", html)
        self.assertIn('tei-${scope}-${id}.pdf', html)
        self.assertNotIn('tei-${scope}-${id}.html', html)
