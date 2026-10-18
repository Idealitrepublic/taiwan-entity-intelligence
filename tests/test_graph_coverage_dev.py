import unittest

from scripts.audit_graph_coverage_dev import is_development_target, summarize


class GraphCoverageAuditTests(unittest.TestCase):
    def setUp(self):
        self.counts = {
            "entities": {"Company": 2, "Politician": 121, "Penalty": 1},
            "relationships": {"COMMITTEE_MEMBER": 1026, "RELATED_TO_PENALTY": 1},
            "published_evidence": 911,
            "traceable_edges": 1027,
            "source_records": {"penalties": 80122},
            "labor_identifier_candidates": 1,
            "donor_candidate_ids": {"all": 487, "single_company_label": 454,
                                    "conflicting_labels": 3, "noncompany_form": 30},
        }
        self.judicial_index = {"records": 4231, "generated_at": "2026-09-24T18:23:51+00:00"}

    def test_source_candidates_are_not_published_edges(self):
        report = summarize(self.counts, self.judicial_index)
        self.assertEqual(report["published"]["companies"], 2)
        self.assertEqual(report["published"]["people"], 0)
        self.assertEqual(report["published"]["judgment_edges"], 0)
        self.assertEqual(report["published"]["penalty_edges"], 1)
        self.assertEqual(report["source_only"]["labor_index_rows"], 80122)
        self.assertEqual(report["source_only"]["judicial_company_name_index_rows"], 4231)
        self.assertEqual(report["source_only"]["political_donor_identifier_candidates"]["single_company_label"], 454)
        self.assertEqual(report["published"]["traceable_edges"], 1027)

    def test_rejects_inconsistent_counters(self):
        for field, value in (("traceable_edges", 1028), ("labor_identifier_candidates", 80123)):
            with self.subTest(field=field):
                counts = {**self.counts, field: value}
                with self.assertRaises(ValueError):
                    summarize(counts, self.judicial_index)

    def test_rejects_missing_index_time_and_negative_count(self):
        with self.assertRaises(ValueError):
            summarize(self.counts, {"records": 4231, "generated_at": None})
        counts = {**self.counts, "source_records": {"penalties": -1}}
        with self.assertRaises(ValueError):
            summarize(counts, self.judicial_index)
        counts = {**self.counts, "donor_candidate_ids": {**self.counts["donor_candidate_ids"],
                                                       "single_company_label": 486}}
        with self.assertRaises(ValueError):
            summarize(counts, self.judicial_index)

    def test_connection_must_name_development_project(self):
        self.assertTrue(is_development_target({"PGUSER": "postgres.canqjiokrtcxkwblhmml"}))
        self.assertFalse(is_development_target({"PGUSER": "postgres.rztdbdurkjfrirsrrhtu"}))
        self.assertFalse(is_development_target({"PGHOST": "localhost"}))


if __name__ == "__main__":
    unittest.main()
