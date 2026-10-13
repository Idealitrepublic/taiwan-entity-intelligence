"""Regression checks for source projections; never connect to a database."""
import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from src import cloud_company
from src.sources import procurement
from src.sources.judicial_index import normalized_dates


def notice(role, date='20261001', job='A'):
    return {'date': date, 'filename': role, 'unit_id': 'agency', 'job_number': job,
            'brief': {'type': '決標公告', 'companies': {
                'names': ['目標公司', '其他公司'],
                'id_key': {'96979933': ['投標廠商:投標廠商2:廠商代碼']},
                'name_key': {'目標公司': ['投標廠商:投標廠商2:廠商名稱',
                                      f'決標品項:第1品項:{role}2:廠商名稱'],
                             '其他公司': ['投標廠商:投標廠商1:廠商名稱',
                                      '決標品項:第1品項:得標廠商1:廠商名稱']}}}}


class CompanyAuditRepairs(unittest.TestCase):
    def test_transient_retry_is_bounded_and_permission_error_not_retried(self):
        with patch('urllib.request.urlopen', side_effect=[TimeoutError(), io.StringIO('[]'), io.StringIO('[]'), io.StringIO('[]')]) as request, patch('time.sleep'):
            self.assertEqual(cloud_company.indexed_records('96979933', '中華電信股份有限公司'), [])
            self.assertEqual(request.call_count, 4)
        for error in (TimeoutError(), urllib.error.HTTPError('https://example.invalid', 403, 'Denied', {}, None)):
            with patch('urllib.request.urlopen', side_effect=error) as request, patch('time.sleep'):
                with self.assertRaises(type(error)):
                    cloud_company.indexed_records('96979933', '中華電信股份有限公司')
                self.assertEqual(request.call_count, 1 if isinstance(error, urllib.error.HTTPError) else 2)

    def test_identifier_path_not_other_bidder_or_position(self):
        self.assertEqual(procurement.award_role(notice('未得標廠商'), '96979933'), 'nonwinner')
        self.assertEqual(procurement.award_role(notice('得標廠商'), '96979933'), 'winner')
        self.assertEqual(procurement.award_role(notice('得標廠商'), '00000000'), 'unresolved')
        row = procurement._normalize(notice('得標廠商'), '96979933')
        self.assertEqual(row['awardee_names'], ['目標公司'])
        self.assertIn('unit_id=agency', row['source_url'])

    def test_correction_retracts_prior_award_and_duplicate_is_not_counted(self):
        rows = [notice('得標廠商'), notice('未得標廠商', '20261002'),
                notice('得標廠商', job='B'), notice('得標廠商', job='B')]
        with patch.object(procurement, '_json_get', return_value={'records': rows, 'total_records': 150}):
            result = procurement.lookup_awards('96979933')
        self.assertEqual(result['matched'], 1)
        self.assertEqual(result['nonwinner_count'], 1)
        self.assertTrue(result['limited'])

    def test_same_day_conflicting_corrections_are_unresolved(self):
        with patch.object(procurement, '_json_get', return_value={'records': [notice('得標廠商'), notice('未得標廠商')]}):
            result = procurement.lookup_awards('96979933')
        self.assertEqual(result['matched'], 0)
        self.assertEqual(result['unresolved_count'], 1)

    def test_date_projection_preserves_publication_and_invalid_jid(self):
        row = normalized_dates({'jid': 'MLDV,113,苗簡,537,20250731,2', 'date': '2025-10-31'})
        self.assertEqual(row['date'], '2025-07-31')
        self.assertEqual(row['source_published_at'], '2025-10-31')
        self.assertTrue(row['date_conflict'])
        self.assertEqual(normalized_dates(row), row)
        for value in ('20250230', '202511', 'n/a'):
            self.assertIsNone(normalized_dates({'jid': f'C,1,T,1,{value},1'})['date'])

    def test_labor_suffix_is_candidate_not_other_company_or_conflicting_id(self):
        rows = [{'id': '1', 'company_name': '中華電信股份有限公司(簡志誠)', 'uniform_number': None},
                {'id': '2', 'company_name': '中華電信股份有限公司服務分公司', 'uniform_number': None},
                {'id': '3', 'company_name': '中華電信股份有限公司(鄭優)', 'uniform_number': '12345678'}]
        responses = [[], [], rows]
        with patch('urllib.request.urlopen', side_effect=[io.StringIO(json.dumps(r)) for r in responses]):
            result = cloud_company.indexed_records('96979933', '中華電信股份有限公司')
        self.assertEqual([row['id'] for row in result], ['1'])


if __name__ == '__main__':
    unittest.main()
