from copy import deepcopy
import unittest

from scripts.refresh_political_master_dev import plan_refresh, transaction
from src.political_master import build_political_master_bundle
from test_political_master import member, committee


class PoliticalMasterRefreshTests(unittest.TestCase):
    def setUp(self):
        self.bundle, _ = build_political_master_bundle([member()], [committee()],
                                                     retrieved_at="2026-10-28T00:00:00+00:00")
        self.before = {key: deepcopy(self.bundle[key]) for key in
                       ("entities", "evidence", "politician_terms", "relationships")}
        for row in self.before["entities"] + self.before["evidence"] + self.before["politician_terms"]:
            row["publication_status"] = "published"
        for row in self.before["relationships"]:
            row["status"] = "published"

    def plan(self, bundle=None, before=None):
        return plan_refresh(bundle or self.bundle, before or self.before,
                            snapshot_hash="a" * 64, retrieved_at="2026-10-28T01:00:00+00:00")

    def test_unchanged_fact_gets_new_provenance_without_rewriting_history(self):
        saved = deepcopy(self.before)
        plan, result = self.plan()
        self.assertEqual(self.before, saved)
        self.assertEqual(result["verified_exact_members"], 1)
        self.assertEqual(plan["relationships"], [])
        self.assertEqual(plan["politician_terms"], [])
        self.assertEqual(len(plan["evidence"]), 1)
        self.assertEqual(len(plan["relationship_evidence"]), 2)
        self.assertEqual(plan["evidence"][0]["source_locator"]["snapshot_sha256"], "a" * 64)

    def test_same_day_same_snapshot_is_idempotent(self):
        plan, _ = self.plan()
        before = deepcopy(self.before)
        before["evidence"].extend(plan["evidence"])
        repeated, _ = self.plan(before=before)
        self.assertEqual(repeated["evidence"], [])
        self.assertEqual(repeated["entity_evidence"], [])

    def test_new_official_session_is_kept_but_unchanged_relationships_are_not_duplicated(self):
        bundle, _ = build_political_master_bundle([member()], [committee(), committee(sessionPeriod="2")],
                                                 retrieved_at="2026-10-28T01:00:00+00:00")
        plan, _ = self.plan(bundle=bundle)
        self.assertEqual(len(plan["relationships"]), 1)
        self.assertEqual(plan["relationships"][0]["relationship_type"], "COMMITTEE_MEMBER")

    def test_changed_published_term_stops_instead_of_silently_correcting(self):
        bundle = deepcopy(self.bundle)
        bundle["politician_terms"][0]["end_date"] = "2026-10-01"
        with self.assertRaisesRegex(ValueError, "reviewed correction"):
            self.plan(bundle=bundle)

    def test_unresolved_members_never_become_published(self):
        bundle, _ = build_political_master_bundle([member(name="缺官方編號")], [],
                                                 retrieved_at="2026-10-28T01:00:00+00:00")
        before = {key: [] for key in self.before}
        plan, result = self.plan(bundle=bundle, before=before)
        self.assertEqual(result["verified_exact_members"], 0)
        self.assertEqual(plan["entities"], [])
        self.assertEqual(plan["relationships"], [])

    def test_transaction_is_bounded_scoped_and_has_no_history_deletion(self):
        plan, _ = self.plan()
        sql = transaction(plan)
        self.assertIn("480000000", sql)
        self.assertIn("SET LOCAL ROLE service_role", sql)
        self.assertIn("WHERE id=ANY", sql)
        self.assertNotIn("DELETE", sql)
        self.assertNotIn("TRUNCATE", sql)


if __name__ == "__main__":
    unittest.main()
