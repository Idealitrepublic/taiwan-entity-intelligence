"""Regression contracts for the public operations remediation."""
import unittest
import json
from pathlib import Path
from unittest.mock import Mock, patch
from io import BytesIO
from pypdf import PdfReader
import app
from src.report_pdf import render_report_pdf


class FullAuditRemediation(unittest.TestCase):
    def test_counts_request_exact_totals_without_transferring_rows(self):
        reply = Mock()
        reply.__enter__ = Mock(return_value=reply)
        reply.__exit__ = Mock(return_value=False)
        reply.headers = {'Content-Range': '*/67134'}
        with patch('app.urllib.request.urlopen', return_value=reply) as request:
            self.assertEqual(app.db_count('evidence_records'), 67134)
            self.assertEqual(request.call_args.args[0].get_header('Prefer'), 'count=exact')
            self.assertEqual(request.call_args.kwargs['timeout'], 3)
            self.assertIn('limit=0', request.call_args.args[0].full_url)
        with patch('app.urllib.request.urlopen', return_value=reply) as request:
            app.db_count('entities', entity_type='eq.Company')
            self.assertEqual(request.call_args.args[0].get_header('Prefer'), 'count=exact')

    def test_verified_snapshot_is_scoped_dated_and_preserved_on_timeout(self):
        app.STATUS_CACHE.clear()
        snapshot=json.loads((Path(__file__).resolve().parents[1]/'src/public_database_counts.json').read_text())['supabase']
        with patch('app.core.SUPABASE', 'https://canqjiokrtcxkwblhmml.supabase.co'), patch('app.core.SUPABASE_KEY', 'anon-test'), patch('app.Thread') as thread:
            code, body, _ = app.database_status()
            try:
                self.assertEqual(code, 200)
                self.assertFalse(body['supabase']['connected'])
                self.assertTrue(body['supabase']['snapshot_available'])
                self.assertGreater(snapshot['canonical']['evidence_records'],0)
                self.assertEqual(body['supabase']['canonical']['evidence_records'], snapshot['canonical']['evidence_records'])
                self.assertEqual(body['supabase']['counts_checked_at'],snapshot['counts_checked_at'])
                thread.assert_called_once()
            finally:
                # Mock threads never execute their real lock-release callback.
                if thread.called:
                    app.STATUS_BACKGROUND_LOCK.release()
            with patch('app.db_count', side_effect=TimeoutError), patch('app.log_event'):
                # Keep the same cache identity while simulating exact count failure.
                key = (app.core.SUPABASE, id(app.db_count))
                app.STATUS_CACHE[key] = (0, (code, body))
                refreshed = app._refresh_database_status()[1]['supabase']
                self.assertEqual(refreshed['canonical']['evidence_records'], snapshot['canonical']['evidence_records'])
                self.assertIn('canonical.evidence_records', refreshed['stale_metrics'])
        with patch('app.core.SUPABASE', 'https://different.supabase.co'):
            self.assertIsNone(app.verified_count_snapshot())
        app.STATUS_CACHE.clear()

    def test_report_assembly_preserves_job_number_detail_fields_and_provenance(self):
        from src.reports import ReportService
        from tests.test_live_company_report import company
        award = {'id': 'notice', 'title': '測試公告', 'date': '2026-11-18',
                 'job_number': '0630800011', 'unit_id': '3.1', 'notice_filename': 'BDM-test',
                 'source_url': 'https://example.gov.tw/award',
                 'key_award_detail': {'status': 'ok', 'retrieved_at': '2026-11-18T14:00:00Z',
                 'source_url': 'https://example.gov.tw/detail', 'summary': [
                    {'label': '預算金額 / Budget', 'value': '0元 原因：收入性質', 'source_field': '已公告資料:預算金額'},
                    {'label': '招標方式 / Tender method', 'value': '公開招標', 'source_field': '已公告資料:招標方式'}]}}
        report = ReportService().company_report('96979933', company_loader=company,
            award_loader=lambda _: {'status': 'ok', 'source': '採購網', 'records': [award]},
            related_loader=lambda _: {'items': []}, published_loader=lambda _: None)
        row = report['government_contracts'][0]
        self.assertEqual(row['relationship']['案號 / Job no.'], '0630800011')
        self.assertEqual(row['relationship']['招標方式 / Tender method'], '公開招標')
        self.assertEqual(row['evidence']['source_locator']['detail_source_url'], 'https://example.gov.tw/detail')
        self.assertTrue(any((s.get('source_locator') or {}).get('job_number') == '0630800011' for s in report['sources']))
        text = ''.join(p.extract_text() or '' for p in PdfReader(BytesIO(render_report_pdf(report))).pages)
        for word in ('案號', '0630800011', '公開招標', '收入性質'):
            self.assertIn(word, text)

    def test_pdf_contains_new_contract_fields_dual_years_and_no_165_section(self):
        evidence = {'source_name': '官方來源', 'source_url': 'https://example.gov.tw/notice', 'retrieved_at': '2026-11-18T14:00:00Z'}
        report = {'report_type': 'LIVE_COMPANY', 'public_graph_scope': True, 'title': '標案測試', 'methodology':'來源核對 / Source verification','generated_at':'2026-11-18T14:00:00Z',
                  'government_contracts': [{'source_entity': {'display_name': '公司'},
                   'target_entity': {'display_name': '測試標案'}, 'evidence': evidence,
                   'relationship': {'relationship_type': 'CONTRACT_WITH', 'start_date': '2026-11-18',
                                    '案號 / Job no.': '0630800011', '預算金額 / Budget': '0元 原因：收入性質',
                                    '決標日期 / Award date': '109/06/03', '招標方式 / Tender method': '公開招標'}}],
                  'sources': [evidence], 'anti_fraud_checks': [{'domain': 'example.com'}]}
        text = ''.join(p.extract_text() or '' for p in PdfReader(BytesIO(render_report_pdf(report))).pages)
        for word in ('0630800011', '公開招標', '收入性質', '民國109年', '民國115年'):
            self.assertIn(word, text)
        self.assertNotIn('165 網域', text)
