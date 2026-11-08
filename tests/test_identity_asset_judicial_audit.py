import unittest

from scripts.audit_identity_asset_judicial_dev import summarize


class IdentityAssetJudicialAuditTests(unittest.TestCase):
    def baseline(self):
        return ({key: 0 for key in ('identifier_conflicts', 'unsafe_accepted_candidates',
                'broken_published_relationships', 'broken_published_assets',
                'asset_link_identifier_mismatches')} | {'assets': []},
                {'pending_jids': 0, 'completed_batches': 1, 'total_batches': 1,
                 'upstream_unavailable_jids': 0})

    def test_integrity_pass_does_not_hide_unresolved_company_or_source_gap(self):
        data, checkpoint = self.baseline()
        data['assets'] = [{'company_name': '同名公司', 'company_entity_id': None,
                           'asset_type': 'STOCK'}]
        result = summarize(data, checkpoint, snapshot_hashes={})
        self.assertEqual((result['integrity'], result['task_completion']), ('PASS', 'PARTIAL'))
        self.assertEqual(result['asset_summary']['unresolved'], 1)
        data['assets'] = []
        checkpoint['upstream_unavailable_jids'] = 1
        self.assertEqual(summarize(data, checkpoint, snapshot_hashes={})['task_completion'], 'PARTIAL')

    def test_fk_conflict_pending_or_missing_measurement_is_failure(self):
        for name in ('broken_published_assets', 'asset_link_identifier_mismatches', 'identifier_conflicts'):
            data, checkpoint = self.baseline()
            data[name] = 1
            self.assertEqual(summarize(data, checkpoint, snapshot_hashes={})['integrity'], 'FAIL')
            del data[name]
            self.assertEqual(summarize(data, checkpoint, snapshot_hashes={})['integrity'], 'FAIL')
        data, checkpoint = self.baseline()
        checkpoint['pending_jids'] = 1
        self.assertEqual(summarize(data, checkpoint, snapshot_hashes={})['integrity'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
