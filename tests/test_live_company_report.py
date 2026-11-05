"""Live company PDF contains the same sourced graph categories as the UI."""
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfReader

from src.report_pdf import render_report_pdf
from src.reports import ReportService, ReportValidationError, dispatch_report_api


def company(_uniform):
    source = {"source_name": "經濟部", "source_url": "https://data.gcis.nat.gov.tw/company",
              "source_record_id": "96979933", "retrieved_at": "2026-10-21T00:00:00Z"}
    penalty = {"source_name": "勞動部", "source_url": "https://data.gov.tw/dataset/109896",
               "source_record_id": "labor-1", "retrieved_at": "2026-10-21T00:00:00Z"}
    return {"status": "ok", "uniform_number": "96979933",
            "company_name": "中華電信股份有限公司",
            "company": {"Business_Accounting_NO": "96979933", "Company_Name": "中華電信股份有限公司",
                        "Company_Location": "臺北市"},
            "graph": {"nodes": [
                {"id": "company:96979933", "type": "company", "label": "中華電信股份有限公司",
                 "evidence": source},
                {"id": "penalty:1", "type": "penalty", "label": "勞動基準法第24條",
                 "properties": {"date": "2025-01-02"}, "evidence": penalty}],
                "edges": [{"source": "company:96979933", "target": "penalty:1",
                           "relationship": "labor_penalty", "evidence": penalty}]},
            "judicial_result": {"status": "ok", "limited": False}}


class LiveCompanyReportTests(unittest.TestCase):
    def setUp(self):
        # Source fixtures must never make an implicit remote DB call.
        self.context_patch = patch.object(ReportService, '_company_published_context', return_value=None)
        self.context_patch.start()
        self.addCleanup(self.context_patch.stop)

    def test_official_snapshot_is_not_labelled_as_a_live_lookup(self):
        from src.report_presentation import present_report
        value = company('96979933')
        value['data_mode'] = 'published_registry_snapshot_plus_supabase'
        report = ReportService().company_report('96979933', company_loader=lambda _: value,
            award_loader=lambda _: {'status': 'ok', 'records': []},
            related_loader=lambda _: {'status': 'ok', 'items': []})
        self.assertEqual(report['company_registry'][0]['fetched_at'], '2026-10-21T00:00:00Z')
        section = next(row for row in present_report(report)['sections'] if row['key'] == 'company_registry')
        self.assertIn(('資料狀態 / Data status', '官方歷史快照 / Dated official snapshot'), section['items'][0]['facts'])

    def test_published_political_assets_evidence_and_graph_survive_company_export(self):
        from copy import deepcopy
        company_id = '11111111-1111-4111-8111-111111111111'
        person_id = '22222222-2222-4222-8222-222222222222'
        proof = {'id': '44444444-4444-4444-8444-444444444444', 'title': '公開政治獻金',
                 'source_name': '官方來源', 'source_url': 'https://example.gov.tw/published',
                 'retrieved_at': '2026-10-20T00:00:00Z'}
        context = {'entity': {'id': company_id, 'entity_type': 'Company', 'display_name': '中華電信', 'evidence': []},
                   'graph': {'nodes': [{'id': person_id, 'entity_type': 'Politician', 'display_name': '測試政治人物'}],
                             'edges': [{'id': '33333333-3333-4333-8333-333333333333',
                                        'source': company_id, 'target': person_id,
                                        'source_entity_id': company_id, 'target_entity_id': person_id,
                                        'relationship_type': 'POLITICAL_CONTRIBUTION_TO',
                                        'primary_evidence': proof}], 'has_more': True},
                   'assets': {'items': [{'asset_name': '測試持有', 'declaration_year': 2025,
                                          'company_entity_id': company_id, 'primary_evidence': proof}], 'has_more': True}}
        value = company('96979933')
        value['graph']['nodes'][0]['evidence']['id'] = 'legacy-registry-evidence'
        before = deepcopy(value)
        report = ReportService().company_report('96979933', company_loader=lambda _: value,
            award_loader=lambda _: {'status': 'ok', 'records': []},
            related_loader=lambda _: {'status': 'ok', 'items': []}, published_loader=lambda _: context)
        self.assertEqual(len(report['political_relationships']), 1)
        self.assertEqual(len(report['asset_records']), 1)
        self.assertTrue(report['coverage']['relationship_truncated'])
        self.assertTrue(report['coverage']['asset_truncated'])
        self.assertTrue(any(row.get('id') == proof['id'] for row in report['sources']))
        import json
        source_versions = [(row.get('source_url'), json.dumps(row.get('source_record_id') or row.get('source_locator'),
                           sort_keys=True), row.get('retrieved_at'), row.get('content_hash'))
                           for row in report['sources']]
        self.assertEqual(len(source_versions), len(set(source_versions)), 'same source version must not be listed twice')
        graph = report['relationship_graph']
        ids = {node['id'] for node in graph['nodes']}
        for edge in graph['edges']:
            relationship = edge.get('relationship')
            relationship = relationship if isinstance(relationship, dict) else edge
            for field in ('source', 'target', 'source_entity_id', 'target_entity_id'):
                if relationship.get(field):
                    self.assertIn(relationship[field], ids)
        self.assertEqual(value, before, 'report assembly must not mutate source snapshots')
        text = ''.join(page.extract_text() for page in PdfReader(BytesIO(render_report_pdf(report))).pages)
        self.assertIn('公開政治獻金', text)
        self.assertIn('測試持有', text)

    def test_unavailable_published_index_is_unknown_not_zero_political_records(self):
        from src.entities.repository import EntityStoreUnavailable
        from src.report_presentation import present_report
        def unavailable(_):
            raise EntityStoreUnavailable('test only')
        report = ReportService().company_report('96979933', company_loader=company,
            award_loader=lambda _: {'status': 'ok', 'records': []},
            related_loader=lambda _: {'status': 'ok', 'items': []}, published_loader=unavailable)
        view = present_report(report)
        self.assertEqual(report['coverage']['published_context_status'], 'unavailable')
        self.assertNotIn('政治關係 / Political Relationships', view['empty'])
        self.assertNotIn('財產申報 / Asset Records', view['empty'])
        self.assertTrue(any('Source verification unavailable' in warning for warning in view['warnings']))

    def test_full_available_live_graph_and_sources_in_pdf(self):
        awards = {"status": "ok", "source": "政府電子採購網", "retrieved_at": "2026-10-21T00:00:00Z",
                  "records": [{"id": "award-1", "title": "通信採購", "date": "2025-02-01",
                               "identity_status": "mirror_exact_bidder_id_unconfirmed_official",
                               "source_url": "https://example.gov.tw/award"}]}
        related = {"status": "ok", "items": [{"uniform_number": "12345678", "company_name": "關聯公司",
                    "connection_type": "same_award_notice", "connection_label": "共同得標 / Co-winner",
                    "evidence": {"source_name": "政府電子採購網", "source_record_id": "award-1",
                                 "source_url": "https://example.gov.tw/award",
                                 "retrieved_at": "2026-10-21T00:00:00Z"}}]}
        service = ReportService(clock=lambda: "2026-10-21T00:00:00Z")
        report = service.company_report("96979933", company_loader=company,
                                        award_loader=lambda _: awards,
                                        related_loader=lambda _: related)
        self.assertEqual(len(report["relationship_graph"]["nodes"]), 5)
        self.assertEqual(len(report["relationship_graph"]["edges"]), 4)
        self.assertEqual(len(report["government_contracts"]), 1)
        self.assertIn('官方公告待核', report['government_contracts'][0]['relationship']['source_role'])
        self.assertEqual(len(report["penalties"]), 1)
        self.assertFalse(report["relationship_graph"]["truncated"])
        pdf = render_report_pdf(report)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        text = "".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
        for expected in ("中華電信股份有限公司", "勞動基準法第24條", "通信採購", "關聯公司",
                         "臺北市", "來源 / Sources", "編號 / Ref", "S001"):
            self.assertIn(expected, text)

    def test_director_source_rows_keep_separate_locators(self):
        def with_directors(uniform):
            data = company(uniform)
            for index in (1, 2):
                evidence = {"source_name": "經濟部董監事", "source_url": "https://data.gcis.nat.gov.tw/directors",
                            "source_locator": f"Business_Accounting_NO={uniform};row={index}"}
                node_id = f"person:{index}"
                data["graph"]["nodes"].append({"id": node_id, "type": "person",
                                                 "label": f"測試人物{index}", "evidence": evidence})
                data["graph"]["edges"].append({"source": f"company:{uniform}", "target": node_id,
                                                 "relationship": "董事", "evidence": evidence})
            return data
        report = ReportService().company_report("96979933", company_loader=with_directors,
                                                award_loader=lambda _: {"status": "ok", "records": []},
                                                related_loader=lambda _: {"status": "ok", "items": []})
        locators = {row.get("source_locator") for row in report["sources"]}
        self.assertIn("Business_Accounting_NO=96979933;row=1", locators)
        self.assertIn("Business_Accounting_NO=96979933;row=2", locators)

    def test_scope_is_exact_uniform_and_ui_routes_to_pdf(self):
        service = ReportService()
        with self.assertRaises(ReportValidationError):
            service.company_report("中華電信", company_loader=company)
        class Stub:
            def company_report(self, uniform):
                return {"report_type": "LIVE_COMPANY",
                "uniform_number": uniform, "title": "測試", "methodology": "來源",
                "generated_at": "2026-10-21T00:00:00Z", "coverage": {},
                "entity_profiles": [], "company_registry": [], "key_relationships": [],
                "political_relationships": [], "government_contracts": [], "judgments": [],
                "penalties": [], "asset_records": [], "relationship_graph": {}, "sources": []}
        code, binary, mime = dispatch_report_api('/api/v1/reports/company/96979933',
                {'format': ['pdf']}, service=Stub())
        self.assertEqual((code, mime), (200, 'application/pdf'))
        self.assertTrue(binary.startswith(b'%PDF-'))
        html = (Path(__file__).resolve().parents[1] / 'web/index.html').read_text()
        self.assertIn('data-report-scope="company"', html)
        self.assertIn('預覽雙語 PDF / Preview PDF', html)

    def test_dictionary_locator_survives_report_assembly_and_pdf_download(self):
        def with_locator(uniform):
            data = company(uniform)
            evidence = data['graph']['nodes'][1]['evidence']
            evidence.pop('source_record_id')
            evidence['source_locator'] = {'dataset': 'labor', 'record': 1}
            data['graph']['nodes'][1]['properties'].update(fine='12500.50', currency='TWD',
                                                         identity_status='candidate')
            return data

        report = ReportService().company_report('96979933', company_loader=with_locator,
                                                award_loader=lambda _: {'status': 'ok', 'records': []},
                                                related_loader=lambda _: {'status': 'ok', 'items': []})
        self.assertTrue(any(row.get('source_locator') == {'dataset': 'labor', 'record': 1}
                            for row in report['sources']))
        self.assertEqual(len(report['sources']), 2, 'registry source must not be duplicated')
        binary = render_report_pdf(report)
        self.assertTrue(binary.startswith(b'%PDF-'))
        text = ''.join(page.extract_text() for page in PdfReader(BytesIO(binary)).pages)
        self.assertIn('NT$ 12,500.50', text)
        self.assertIn('來源觀察；身分待核', ''.join(text.split()))
        self.assertIn('身分待核', report['penalties'][0]['relationship']['source_role'])

    def test_distinct_retrieval_versions_of_one_source_remain_in_register(self):
        def versions(uniform):
            data = company(uniform)
            first = data['graph']['nodes'][1]
            data['graph']['nodes'].append({**first, 'id': 'penalty:version2',
                'evidence': {**first['evidence'], 'retrieved_at': '2026-10-22T00:00:00Z'}})
            return data

        report = ReportService().company_report('96979933', company_loader=versions,
                                                award_loader=lambda _: {'status': 'ok', 'records': []},
                                                related_loader=lambda _: {'status': 'ok', 'items': []})
        observed = [row['retrieved_at'] for row in report['sources']
                    if row.get('source_record_id') == 'labor-1']
        self.assertEqual(set(observed), {'2026-10-21T00:00:00Z', '2026-10-22T00:00:00Z'})


if __name__ == "__main__":
    unittest.main()
