from copy import deepcopy
import unittest
from scripts.development_gap_report import report_markdown


class DevelopmentGapReportTests(unittest.TestCase):
    def setUp(self):
        self.counts = {'database_bytes':475196563, 'entities':{'Company':462,'Judgment':0},
                       'relationships':1390,'untraceable_relationships':0,
                       'companies_without_exact_id':0,'duplicate_exact_company_ids':0,
                       'source_records':{'penalties':81033},
                       'freshness':[{'source_name':'官方來源','records':10,'oldest':'2025-01-01',
                                     'newest':'2026-10-30','older_30_days':9}]}

    def test_counts_do_not_become_national_coverage_or_zero_data_claims(self):
        text = report_markdown(self.counts)
        for value in ('公司 | 462', '裁判 | 0', '未知', '不代表其紀錄為零',
                      '4,803,437 bytes', '最新一筆不能代表整個來源都已更新', '2025-01-01'):
            self.assertIn(value, text)

    def test_missing_failed_or_inconsistent_measurement_never_defaults_to_zero(self):
        for changes in ({'database_bytes':None}, {'relationships':-1},
                        {'untraceable_relationships':1391}, {'entities':{'Company':-1}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                report_markdown({**self.counts, **changes})
        original=deepcopy(self.counts)
        report_markdown(self.counts)
        self.assertEqual(self.counts, original)
