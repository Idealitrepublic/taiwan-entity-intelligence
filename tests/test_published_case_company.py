import copy
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

from src import cloud_company
from src.entities.models import stable_id
from src.entities.repository import EntityStoreUnavailable


UNIFORM = '59066479'
COMPANY = stable_id('entity', 'tw:uniform_number', UNIFORM)
CASE = '11111111-1111-4111-8111-111111111111'
EDGE = '22222222-2222-4222-8222-222222222222'
EVIDENCE = '33333333-3333-4333-8333-333333333333'


class PublishedCaseCompanyTests(unittest.TestCase):
    def repository(self):
        repo = Mock()
        repo.transport.return_value = [{'entity_id': COMPANY, 'value': UNIFORM}]
        repo.graph_neighbors.return_value = {
            'nodes': [{'id': COMPANY, 'entity_type': 'Company', 'identity_status': 'EXACT'},
                      {'id': CASE, 'entity_type': 'Judgment', 'display_name': '裁判結果公告'}],
            'edges': [{'id': EDGE, 'source_entity_id': COMPANY, 'target_entity_id': CASE,
                       'relationship_type': 'RELATED_TO_JUDGMENT', 'status': 'published',
                       'confidence': 'HIGH', 'source_role': '法院公告當事法人 / Corporate party',
                       'start_date': '2022-07-29', 'primary_evidence': {
                           'id': EVIDENCE, 'source_url': 'https://www.judicial.gov.tw/test',
                           'source_name': '法院角色證據', 'source_record_id': 'notice:1',
                           'source_locator': {'notice_id': '1', 'event_date': '2022-07-29'},
                           'title': '角色證據', 'summary': '僅案件角色，不推論關聯者有罪',
                           'status': 'active', 'retrieved_at': '2026-11-01T00:00:00Z'}}],
            'has_more': False,
        }
        return repo

    def test_bounded_exact_identifier_read_preserves_real_role_without_fake_jid(self):
        repo = self.repository()
        rows, status = cloud_company._published_case_evidence(UNIFORM, repo)
        self.assertEqual(status, {'status': 'ok', 'matched': 1, 'limited': False})
        repo.graph_neighbors.assert_called_once_with(COMPANY, limit=12, relationship_type='RELATED_TO_JUDGMENT')
        record = rows[0]['_published_case_record']
        self.assertNotIn('jid', record)
        self.assertEqual(record['relationship_id'], EDGE)
        self.assertEqual(record['party_role'], '法院公告當事法人 / Corporate party')

    def test_wrong_identifier_never_uses_a_name_fallback(self):
        repo = self.repository()
        repo.transport.return_value = [{'entity_id': CASE, 'value': UNIFORM}]
        rows, status = cloud_company._published_case_evidence(UNIFORM, repo)
        self.assertFalse(rows)
        self.assertEqual(status['status'], 'not_indexed')
        repo.graph_neighbors.assert_not_called()

    def test_low_confidence_draft_missing_role_or_inactive_evidence_cannot_be_promoted(self):
        for key, value in [('confidence', 'LOW'), ('status', 'draft'), ('source_role', ''),
                           ('source_entity_id', CASE), ('relationship_type', 'OFFICER_OF')]:
            with self.subTest(key=key):
                repo = self.repository()
                repo.graph_neighbors.return_value['edges'][0][key] = value
                self.assertEqual(cloud_company._published_case_evidence(UNIFORM, repo)[0], [])
        repo = self.repository()
        repo.graph_neighbors.return_value['edges'][0]['primary_evidence']['status'] = 'retracted'
        self.assertEqual(cloud_company._published_case_evidence(UNIFORM, repo)[0], [])

    def test_source_failure_is_unknown_not_verified_zero(self):
        repo = self.repository()
        repo.graph_neighbors.side_effect = EntityStoreUnavailable('not logged')
        rows, status = cloud_company._published_case_evidence(UNIFORM, repo)
        self.assertFalse(rows)
        self.assertEqual(status, {'status': 'partial', 'matched': None})

    def test_canonical_data_survives_unavailable_legacy_evidence_table(self):
        expected, state = cloud_company._published_case_evidence(UNIFORM, self.repository())
        with patch.object(cloud_company, 'SUPABASE_KEY', 'test-public-only'), \
             patch('urllib.request.urlopen', side_effect=URLError('offline')), \
             patch.object(cloud_company, '_published_case_evidence', return_value=(expected, state)):
            rows, connected = cloud_company._supabase_evidence(UNIFORM)
        self.assertTrue(connected)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.case_status['matched'], 1)

    def run_company(self, evidence, case_status=None):
        base = {'status': 'ok', 'uniform_number': UNIFORM, 'company_name': '測試法人',
                'evidence': copy.deepcopy(evidence), 'evidence_status': {},
                'graph': {'nodes': [], 'edges': []},
                'published_case_status': case_status or {'status': 'ok'}}
        local = {'records': [], 'status': 'partial', 'matched': 0,
                 'coverage_note': 'limited local index', 'interpretation': 'name mentions only',
                 'match_rule': 'exact_full_name_mention_only'}
        with patch.object(cloud_company, '_base_company', return_value=base), \
             patch.object(cloud_company, 'indexed_records', return_value=[]), \
             patch.object(cloud_company, 'records_for_company', return_value=local), \
             patch.object(cloud_company, 'verified_website', return_value=None):
            return cloud_company.build_company(UNIFORM)

    def test_default_company_projection_contains_case_graph_and_evidence_once(self):
        evidence, status = cloud_company._published_case_evidence(UNIFORM, self.repository())
        result = self.run_company(evidence, status)
        self.assertEqual(len(result['judicial_records']), 1)
        self.assertEqual(result['judicial_result']['indexed_matched'], 0)
        self.assertEqual(result['judicial_result']['published_role_matched'], 1)
        self.assertEqual(len(result['evidence']), 1)
        self.assertEqual(result['graph']['edges'][0]['properties']['relationship_id'], EDGE)
        self.assertEqual(result['graph']['nodes'][0]['evidence']['id'], EVIDENCE)
        self.assertNotIn('jid', result['graph']['nodes'][0]['properties'])
        self.assertFalse(result['graph']['edges'][0]['properties']['legal_conclusion'])

    def test_partial_canonical_read_keeps_failure_disclosure(self):
        result = self.run_company([], {'status': 'partial', 'matched': None})
        self.assertEqual(result['judicial_result']['status'], 'partial')
        self.assertIn('不能視為零筆', result['judicial_result']['coverage_note'])

    def test_more_rows_are_disclosed_as_bounded_partial_read(self):
        repo = self.repository()
        repo.graph_neighbors.return_value['has_more'] = True
        _, status = cloud_company._published_case_evidence(UNIFORM, repo)
        self.assertEqual(status, {'status': 'partial', 'matched': 1, 'limited': True})


if __name__ == '__main__':
    unittest.main()
