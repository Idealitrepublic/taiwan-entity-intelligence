import json
import unittest

from src.political_master import (
    LEGISLATOR_NUMBER_NAMESPACE,
    build_political_master_bundle,
    political_master_batches,
)


def member(**updates):
    row = {
        "term": "11",
        "name": "測試委員",
        "party": "測試政黨",
        "areaName": "臺北市第1選舉區",
        "onboardDate": "2024/02/01",
        "leaveDate": None,
        "leaveFlag": "否",
        "tel": "02-0000-0000",
        "addr": "不應進入 Evidence",
    }
    row.update(updates)
    return row


def committee(**updates):
    row = {
        "term": "11",
        "sessionPeriod": "1",
        "lgno": "110001",
        "name": "測試委員",
        "committee": "內政委員會",
        "isCoChairman": "Y",
    }
    row.update(updates)
    return row


class PoliticalMasterTests(unittest.TestCase):
    def build(self, members, committees):
        return build_political_master_bundle(
            members, committees, retrieved_at="2026-09-23T10:00:00+08:00")

    def test_exact_lgno_links_terms_without_name_based_cross_term_merge(self):
        bundle, report = self.build(
            [member(), member(term="10", onboardDate="2020/02/01")],
            [committee(), committee(term="10", sessionPeriod="8")])
        politicians = [item for item in bundle["entities"]
                       if item["entity_type"] == "Politician"]
        self.assertEqual(len(politicians), 1)
        self.assertEqual(len(bundle["politician_terms"]), 2)
        self.assertEqual({item["politician_entity_id"]
                          for item in bundle["politician_terms"]}, {politicians[0]["id"]})
        self.assertEqual(bundle["identifiers"], [{
            "entity_id": politicians[0]["id"],
            "namespace": LEGISLATOR_NUMBER_NAMESPACE,
            "value": "110001",
        }])
        self.assertEqual(report["quality"]["exact_identifier_rate"], 1.0)
        self.assertEqual(sum(item["relationship_type"] == "COMMITTEE_MEMBER"
                             for item in bundle["relationships"]), 2)

    def test_ambiguous_same_name_never_creates_exact_identifier_or_committee_edge(self):
        bundle, report = self.build(
            [member()],
            [committee(lgno="110001"), committee(lgno="110099",
                                                  committee="外交及國防委員會")])
        politician = next(item for item in bundle["entities"]
                          if item["entity_type"] == "Politician")
        self.assertEqual(politician["identity_status"], "SOURCE_SCOPED")
        self.assertEqual(bundle["identifiers"], [])
        self.assertFalse(any(item["relationship_type"] == "COMMITTEE_MEMBER"
                             for item in bundle["relationships"]))
        self.assertTrue(any(item["type"] == "ambiguous_legislator_number"
                            for item in report["quality_issues"]))

    def test_fields_are_typed_evidence_backed_draft_and_private_contact_is_redacted(self):
        bundle, report = self.build([member()], [committee()])
        term = bundle["politician_terms"][0]
        self.assertEqual((term["term_number"], term["constituency_type"]), (11, "district"))
        self.assertEqual((term["start_date"], term["end_date"]), ("2024-02-01", None))
        self.assertEqual(term["publication_status"], "draft")
        self.assertTrue(all(item["publication_status"] == "draft"
                            for item in bundle["entities"] + bundle["evidence"]))
        self.assertTrue(all(item["status"] == "draft" for item in bundle["relationships"]))
        serialized = json.dumps(bundle, ensure_ascii=False)
        self.assertNotIn("02-0000-0000", serialized)
        self.assertNotIn("不應進入 Evidence", serialized)
        self.assertEqual(report["matching_strategy"], "exact_lgno_or_source_scoped_record")

    def test_invalid_rows_are_skipped_and_output_is_deterministic(self):
        rows = [member(), member(name="", onboardDate="bad")]
        committees = [committee(), committee(lgno="name-only")]
        first, report = self.build(rows, committees)
        second, _ = self.build(rows, committees)
        self.assertEqual(first, second)
        self.assertEqual(len(report["skipped"]), 2)
        self.assertEqual(report["counts"]["politician_terms"], 1)

    def test_large_projection_is_split_into_dependency_complete_rpc_batches(self):
        members = []
        committees = []
        for number in range(110001, 110121):
            name = f"委員{number}"
            members.append(member(name=name))
            for session in range(1, 4):
                committees.append(committee(name=name, lgno=str(number),
                                              sessionPeriod=str(session)))
        bundle, _ = self.build(members, committees)
        batches = political_master_batches(bundle, max_bytes=120_000)
        self.assertGreater(len(batches), 1)
        for batch in batches:
            self.assertLessEqual(len(batch["entities"]), 200)
            self.assertLessEqual(len(batch["relationships"]), 200)
            self.assertLessEqual(len(batch["evidence"]), 400)
            self.assertLessEqual(len(batch["politician_terms"]), 200)
            entity_ids = {item["id"] for item in batch["entities"]}
            evidence_ids = {item["id"] for item in batch["evidence"]}
            for relationship in batch["relationships"]:
                self.assertIn(relationship["source_entity_id"], entity_ids)
                self.assertIn(relationship["target_entity_id"], entity_ids)
                self.assertIn(relationship["primary_evidence_id"], evidence_ids)


if __name__ == "__main__":
    unittest.main()
