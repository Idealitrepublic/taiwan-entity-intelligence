import copy
import json
from pathlib import Path
import unittest

from src.civil_name_review import build_plan

ROOT = Path(__file__).resolve().parents[1]


class CivilNameReviewTests(unittest.TestCase):
    def setUp(self):
        self.review = json.loads((ROOT/'docs/CIVIL_NAME_VERIFICATION_2026-11-20.json').read_text())
        self.baseline = json.loads((ROOT/'docs/CIVIL_NAME_QUALITY_REVIEW_2026-11-20.json').read_text())

    def test_exact_scope_and_historical_hold(self):
        rows = build_plan(self.review, self.baseline)
        self.assertEqual(len(rows), 35)
        self.assertEqual(sum(r['publication_status'] == 'published' for r in rows), 34)
        held = next(r for r in rows if '蔡長' in r['name'])
        self.assertEqual(held['publication_status'], 'draft')
        self.assertEqual(held['evidence']['publication_status'], 'draft')
        self.assertTrue(all(r['evidence']['source_locator']['identity_scope'].startswith('SOURCE_SCOPED') for r in rows))
        self.assertEqual(rows, build_plan(copy.deepcopy(self.review), self.baseline))

    def test_missing_rows_and_duplicate_ids_rejected(self):
        self.review['records'].pop()
        with self.assertRaises(ValueError):
            build_plan(self.review, self.baseline)

    def test_unrelated_name_change_rejected(self):
        self.review['records'][0]['corrected_name'] = '另一個宗親協會'
        with self.assertRaises(ValueError):
            build_plan(self.review, self.baseline)

    def test_nonofficial_or_missing_anchor_rejected(self):
        row = self.review['records'][0]
        for url in ('https://example.com/name', 'https://x.gov.tw@evil.test/name'):
            row['proof']['source_url'] = url
            with self.assertRaises(ValueError):
                build_plan(self.review, self.baseline)
        row['proof']['source_url'] = 'https://sas.miaoli.gov.tw/roster_society'
        row['proof']['anchor_found'] = False
        with self.assertRaises(ValueError):
            build_plan(self.review, self.baseline)

    def test_original_fk_and_namespace_cannot_change(self):
        self.review['records'][0]['source_id'] = 'different-row'
        with self.assertRaises(ValueError):
            build_plan(self.review, self.baseline)

    def test_hold_cannot_be_republished(self):
        row = next(r for r in self.review['records'] if r.get('hold'))
        row['publication_status'] = 'published'
        with self.assertRaises(ValueError):
            build_plan(self.review, self.baseline)


if __name__ == '__main__':
    unittest.main()
