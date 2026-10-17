import unittest

from scripts.audit_graph_integrity_dev import validate


class GraphIntegrityAuditTests(unittest.TestCase):
    def setUp(self):
        self.counts = {
            "published_companies": 2,
            "verified_company_ids": 2,
            "company_registry_evidence": 2,
            "published_people": 0,
            "published_politicians": 121,
            "politicians_with_official_ids": 121,
            "politician_edges": 1025,
            "politician_edges_with_matching_official_id": 1025,
            "published_edges": 1027,
            "invalid_edges": 0,
            "duplicate_edges": 0,
        }

    def test_verified_published_scope_passes(self):
        self.assertEqual(validate(self.counts), self.counts)

    def test_missing_official_identifier_fails(self):
        self.counts["verified_company_ids"] = 1
        with self.assertRaises(ValueError):
            validate(self.counts)

    def test_unsupported_edge_fails(self):
        self.counts["invalid_edges"] = 1
        with self.assertRaises(ValueError):
            validate(self.counts)


if __name__ == "__main__":
    unittest.main()
