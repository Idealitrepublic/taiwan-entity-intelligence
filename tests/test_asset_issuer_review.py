import copy
import json
import unittest

from src.asset_issuer_review import MANIFEST, build_review_bundle
from src.entities.models import stable_id
from scripts.review_asset_issuers_dev import publication_sql


class AssetIssuerReviewTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text())
        self.politician = stable_id('entity', 'tw:legislative_yuan:legislator_number', '00082')
        self.assets = {row['asset_id']: {
            'id': row['asset_id'], 'politician_id': self.politician,
            'publication_status': 'published', 'asset_type': row['asset_type'],
            'company_name': row['company_name'], 'primary_evidence_id': row['declaration_evidence_id'],
            'pdf_sha256': self.manifest['filing_sha256'], 'source_url': 'https://www-ws.cy.gov.tw/Download.ashx',
        } for row in self.manifest['rows']}
        self.snapshots = {issuer['value']: {'row': {
            'Business_Accounting_NO': issuer['value'], 'Company_Name': issuer['official_name']},
            'sha256': 'a' * 64, 'source_url': 'https://data.gcis.nat.gov.tw/od/data/api/test'}
            for issuer in self.manifest['issuers'] if issuer['namespace'] == 'tw:uniform_number'}

    def build(self, retrieved_at='2026-11-08T05:00:00+00:00'):
        return build_review_bundle(self.manifest, self.assets, politician_id=self.politician,
                                   retrieved_at=retrieved_at, registry_snapshots=self.snapshots)

    def test_all_twelve_rows_have_distinct_reviews_and_nine_registered_identities(self):
        bundle = self.build()
        self.assertEqual(len(bundle['evidence']), 21)
        reviews = [e for e in bundle['evidence'] if e['source_class'] == 'Derived Data']
        self.assertEqual(len({e['source_locator']['asset_declaration_id'] for e in reviews}), 12)
        self.assertEqual(sum(e['source_locator']['role'] == 'insurance_provider' for e in reviews), 6)
        self.assertEqual(sum(e['source_locator']['role'] == 'stock_issuer' for e in reviews), 6)
        self.assertTrue(all(e['source_locator']['identifier_present_in_declaration'] is False for e in reviews))
        self.assertTrue(all(e['source_locator']['security_class'] is None for e in reviews))
        self.assertEqual(len({e['source_locator']['register_evidence_id'] for e in reviews}), 9)

    def test_issuer_identity_never_changes_holdings_or_creates_graph_edges(self):
        before = copy.deepcopy(self.assets)
        bundle = self.build()
        for key in ('entities', 'identifiers', 'relationships', 'relationship_evidence'):
            self.assertEqual(bundle[key], [])
        self.assertEqual(self.assets, before)
        sql = publication_sql(bundle, self.assets).lower()
        self.assertNotIn('update public.asset_declarations', sql)
        self.assertNotIn('update public.relationships', sql)
        self.assertNotIn('insert into public.entities', sql)

    def test_missing_changed_withdrawn_or_different_declarant_fails_closed(self):
        row = next(iter(self.assets.values()))
        for key, value in (('company_name', '相似但不同公司'), ('politician_id', 'another-person'),
                           ('pdf_sha256', 'b' * 64), ('publication_status', 'withdrawn')):
            old = row[key]
            row[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.build()
            row[key] = old

    def test_insurance_cannot_be_reclassified_as_equity(self):
        issuer = next(i for i in self.manifest['issuers'] if i['role'] == 'insurance_provider')
        issuer['role'] = 'stock_issuer'
        with self.assertRaisesRegex(ValueError, 'roles'):
            self.build()

    def test_foreign_id_cannot_be_taiwan_uniform_or_parent_with_another_cik(self):
        issuer = next(i for i in self.manifest['issuers'] if i['jurisdiction'] == 'us')
        issuer['value'] = '0000000001'
        with self.assertRaisesRegex(ValueError, 'SEC'):
            self.build()

    def test_independent_alias_and_exact_registry_proof_required(self):
        issuer = next(i for i in self.manifest['issuers'] if i['source_label'] == '聯嘉投控')
        issuer.pop('alias_source_url')
        with self.assertRaisesRegex(ValueError, 'alias'):
            self.build()
        self.setUp()
        self.snapshots['03374707']['row']['Company_Name'] = '國泰金融控股股份有限公司'
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            self.build()

    def test_rerun_is_idempotent_and_foreign_bulk_403_not_claimed_as_download(self):
        first = self.build()
        second = self.build('2026-11-08T06:00:00+00:00')
        self.assertEqual([e['id'] for e in first['evidence']], [e['id'] for e in second['evidence']])
        for evidence in first['evidence']:
            locator = evidence['source_locator']
            if locator.get('identifier_namespace') == 'us:sec:cik' and evidence['source_class'] == 'Official Registry':
                self.assertEqual(locator['direct_bulk_api_status'], 403)
                self.assertIsNone(locator['raw_download_sha256'])

    def test_different_company_registry_page_or_unofficial_alias_is_rejected(self):
        issuer = next(i for i in self.manifest['issuers'] if i['source_label'] == '聯嘉投控')
        issuer['source_url'] = 'https://findbiz.nat.gov.tw/fts/company/12345678'
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            self.build()
        self.setUp()
        issuer = next(i for i in self.manifest['issuers'] if i['source_label'] == '聯嘉投控')
        issuer['alias_source_url'] = 'https://example.com/unverified'
        with self.assertRaisesRegex(ValueError, 'official stock exchange'):
            self.build()


if __name__ == '__main__':
    unittest.main()
