import unittest

from src.company_registry_materialization import (build_registry_company_bundle,
                                                  build_official_registry_identity_bundle)
from src.entities.models import stable_id


REGISTRY = {
    "Business_Accounting_NO": "22099131",
    "Company_Name": "台灣積體電路製造股份有限公司",
    "Company_Status_Desc": "核准設立",
    "Change_Of_Approval_Data": "1150821",
}


class CompanyRegistryMaterializationTests(unittest.TestCase):
    def test_exact_official_identity_publishes_entity_and_evidence_only(self):
        bundle = build_registry_company_bundle(
            REGISTRY, uniform="22099131", expected_name=REGISTRY["Company_Name"],
            retrieved_at="2026-10-18T13:00:00+00:00")
        entity = bundle["entities"][0]
        evidence = bundle["evidence"][0]
        self.assertEqual(entity["id"], stable_id("entity", "tw:uniform_number", "22099131"))
        self.assertEqual(entity["publication_status"], "published")
        self.assertEqual(evidence["publication_status"], "published")
        self.assertEqual(evidence["observed_at"], "2026-08-21T00:00:00+08:00")
        self.assertIn("22099131", evidence["source_url"])
        self.assertEqual(bundle["entity_evidence"][0]["fact_type"], "IDENTITY")
        self.assertNotIn("relationships", bundle)

    def test_invalid_id_name_or_status_cannot_publish(self):
        cases = [
            (dict(REGISTRY), "22099130", REGISTRY["Company_Name"]),
            (dict(REGISTRY), "22099131", "台積電機有限公司"),
            ({**REGISTRY, "Company_Status_Desc": "解散"}, "22099131", REGISTRY["Company_Name"]),
        ]
        for row, uniform, expected in cases:
            with self.subTest(uniform=uniform, expected=expected), self.assertRaises(ValueError):
                build_registry_company_bundle(row, uniform=uniform, expected_name=expected,
                                              retrieved_at="2026-10-18T13:00:00+00:00")

    def test_evidence_identity_stays_stable_across_retrievals(self):
        earlier = build_registry_company_bundle(
            REGISTRY, uniform="22099131", expected_name=REGISTRY["Company_Name"],
            retrieved_at="2026-10-18T13:00:00+00:00")
        later = build_registry_company_bundle(
            REGISTRY, uniform="22099131", expected_name=REGISTRY["Company_Name"],
            retrieved_at="2026-10-19T13:00:00+00:00")
        self.assertEqual(earlier["evidence"][0]["id"], later["evidence"][0]["id"])

    def test_invalid_official_change_date_keeps_retrieval_time(self):
        bundle = build_registry_company_bundle(
            {**REGISTRY, "Change_Of_Approval_Data": "1151332"},
            uniform="22099131", expected_name=REGISTRY["Company_Name"],
            retrieved_at="2026-10-18T13:00:00+00:00")
        self.assertEqual(bundle["evidence"][0]["observed_at"],
                         "2026-10-18T13:00:00+00:00")

    def test_historical_official_identity_is_not_reported_as_active(self):
        bundle = build_official_registry_identity_bundle(
            {**REGISTRY, "Company_Status_Desc": "解散"}, uniform="22099131",
            retrieved_at="2026-10-18T13:00:00+00:00")
        self.assertEqual(bundle["evidence"][0]["source_locator"]["company_status"], "解散")
        self.assertIn("解散", bundle["evidence"][0]["summary"])
        self.assertNotIn("relationships", bundle)


if __name__ == "__main__":
    unittest.main()
