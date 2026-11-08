"""Published company report context must not be inferred from a company name."""
import unittest
from unittest.mock import patch

from src.entities.repository import EntityRepository

COMPANY = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'


class CompanyReportContextTests(unittest.TestCase):
    def test_only_one_exact_official_identifier_can_select_the_company(self):
        calls = []
        def transport(table, params):
            calls.append((table, params))
            return [{'entity_id': COMPANY, 'value': '96979933'}]
        repository = EntityRepository(transport)
        with patch.object(repository, 'entity', return_value={
                'id': COMPANY, 'entity_type': 'Company', 'identity_status': 'EXACT'}) as get:
            self.assertEqual(repository.company_for_uniform('96979933')['id'], COMPANY)
            get.assert_called_once_with(COMPANY)
        params = calls[0][1]
        self.assertEqual(params['namespace'], 'eq.tw:uniform_number')
        self.assertEqual(params['value'], 'eq.96979933')
        self.assertNotIn('name', params)

    def test_ambiguous_or_wrong_identifier_never_selects_a_same_name_company(self):
        for rows in ([], [{'entity_id': COMPANY, 'value': '12345678'}],
                     [{'entity_id': COMPANY, 'value': '96979933'}, {'entity_id': OTHER, 'value': '96979933'}]):
            repository = EntityRepository(lambda *_: rows)
            with patch.object(repository, 'entity') as get:
                self.assertIsNone(repository.company_for_uniform('96979933'))
                get.assert_not_called()

    def test_unresolved_identity_is_not_exported_as_a_matched_company(self):
        repository = EntityRepository(lambda *_: [{'entity_id': COMPANY, 'value': '96979933'}])
        with patch.object(repository, 'entity', return_value={
                'id': COMPANY, 'entity_type': 'Company', 'identity_status': 'UNRESOLVED'}):
            self.assertIsNone(repository.company_for_uniform('96979933'))

    def test_asset_context_uses_company_fk_and_visible_primary_evidence(self):
        calls = []
        def transport(table, params):
            calls.append((table, params))
            return [{'id': str(index)} for index in range(26)]
        result = EntityRepository(transport).company_asset_declarations(COMPANY)
        self.assertEqual(len(result['items']), 25)
        self.assertTrue(result['has_more'])
        table, params = calls[0]
        self.assertEqual(table, 'asset_declarations')
        self.assertEqual(params['company_entity_id'], 'eq.' + COMPANY)
        self.assertIn('!inner(', params['select'])
        self.assertIn('company_identity_evidence:evidence_records', params['select'])
        self.assertIn('company_identity_evidence_id', params['select'])
        self.assertEqual(params['primary_evidence.publication_status'], 'eq.published')
        self.assertEqual(params['primary_evidence.status'], 'eq.active')

    def test_company_entity_report_retains_asset_records_and_limit_warning(self):
        from unittest.mock import Mock
        from src.reports import ReportService
        repository = Mock()
        repository.entity.return_value = {'id': COMPANY, 'entity_type': 'Company', 'evidence': []}
        repository.graph_neighbors.return_value = None
        repository.company_registry_for_entity.return_value = None
        repository.company_asset_declarations.return_value = {'items': [
            {'asset_name': '已發布投資', 'company_entity_id': COMPANY}], 'has_more': True}
        report = ReportService(repository).entity_report(COMPANY)
        self.assertEqual(report['asset_records'][0]['asset_name'], '已發布投資')
        self.assertTrue(report['coverage']['asset_truncated'])
