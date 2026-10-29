from copy import deepcopy
import unittest

from scripts.data_health import verified_term_freshness


class PoliticalHealthFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.term = {"primary_evidence_id": "original", "legislator_number": "00007", "term_number": 11,
                     "retrieved_at": "2026-09-22T00:00:00+00:00", "source_url": "https://data.ly.gov.tw/getds.action?id=16"}
        self.proof = {"source_url": self.term["source_url"], "retrieved_at": "2026-10-28T00:00:00+00:00",
                      "source_locator": {"verified_evidence_id": "original", "legislator_number": "00007", "term": 11,
                                         "snapshot_sha256": "a" * 64, "match_method": "unchanged_fact_exact_official_identifier"}}

    def test_exact_original_proof_can_be_rechecked_without_rewriting_term(self):
        before = deepcopy(self.term)
        self.assertEqual(verified_term_freshness([self.term], [self.proof]), (self.proof["retrieved_at"], 1))
        self.assertEqual(self.term, before)

    def test_unrelated_recent_source_never_refreshes_an_old_fact(self):
        proof = deepcopy(self.proof)
        proof["source_locator"]["verified_evidence_id"] = "different"
        self.assertEqual(verified_term_freshness([self.term], [proof]), (self.term["retrieved_at"], 0))

    def test_one_fresh_member_does_not_hide_stale_members(self):
        old = {**self.term, "primary_evidence_id": "other"}
        self.assertEqual(verified_term_freshness([self.term, old], [self.proof]), (self.term["retrieved_at"], 1))

    def test_latest_verification_uses_timezones_not_string_order(self):
        later = {**self.proof, "retrieved_at": "2026-10-27T23:00:00-08:00"}
        earlier = {**self.proof, "retrieved_at": "2026-10-28T01:00:00+00:00"}
        self.assertEqual(verified_term_freshness([self.term], [earlier, later]), (later["retrieved_at"], 1))

    def test_invalid_or_missing_original_time_is_unknown_until_exact_recheck(self):
        for value in (None, "invalid", "2026-09-22T00:00:00"):
            term = {**self.term, "retrieved_at": value}
            self.assertEqual(verified_term_freshness([self.term, term], []), (None, 0))
            self.assertEqual(verified_term_freshness([term], [self.proof]), (self.proof["retrieved_at"], 1))


if __name__ == "__main__":
    unittest.main()
