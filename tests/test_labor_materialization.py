import unittest
from src.labor_materialization import build_penalty_bundle, explicit_company_identifier


def record():
    return {"id": "mol:official-disposition", "source_file_id": "11111111-1111-4111-8111-111111111111",
            "source_url": "https://data.gov.tw/dataset/109896", "indexed_at": "2026-10-06T00:00:00Z",
            "raw": {"事業單位名稱或負責人": "大魯閣實業股份有限公司 ( 林曼麗)\t04690983",
                    "處分日期": "20240717", "處分字號": "府勞動字第1130101133號",
                    "主管機關": "新竹市", "罰鍰金額": "50000", "違法法規法條": "勞基法第36條第2項第3款",
                    "違反法規內容": "每二周中未有二日之休息作為例假。"}}


REGISTRY = {"Business_Accounting_NO": "04690983", "Company_Name": "大魯閣實業股份有限公司"}


class LaborMaterializationTests(unittest.TestCase):
    def test_explicit_identifier_chain_preserves_source_and_exact_evidence(self):
        source = record()
        bundle = build_penalty_bundle(source, REGISTRY, registry_retrieved_at="2026-10-06T00:00:00Z")
        company, penalty = bundle["entities"]
        edge = bundle["relationships"][0]
        evidence = bundle["evidence"][1]
        self.assertEqual(bundle["identifiers"][0]["value"], "04690983")
        self.assertEqual((edge["source_entity_id"], edge["target_entity_id"]), (company["id"], penalty["id"]))
        self.assertEqual(edge["primary_evidence_id"], evidence["id"])
        self.assertEqual((edge["confidence"], edge["amount"], edge["start_date"]), ("EXACT", 50000, "2024-07-17"))
        self.assertEqual(evidence["source_record_id"], source["id"])
        self.assertEqual(evidence["source_locator"]["source_file_id"], source["source_file_id"])
        self.assertEqual(evidence["retrieved_at"], "2026-10-06T00:00:00+00:00")
        self.assertIn({"entity_id": company["id"], "evidence_id": evidence["id"], "fact_type": "PENALTY"}, bundle["entity_evidence"])

    def test_retries_are_idempotent_and_existing_identifier_identity_is_reused(self):
        first = build_penalty_bundle(record(), REGISTRY, registry_retrieved_at="2026-10-06T00:00:00Z")
        second = build_penalty_bundle(record(), REGISTRY, registry_retrieved_at="2026-10-07T00:00:00Z")
        self.assertEqual([v["id"] for v in first["evidence"]], [v["id"] for v in second["evidence"]])
        self.assertEqual(first["relationships"], second["relationships"])
        existing = "22222222-2222-4222-8222-222222222222"
        reused = build_penalty_bundle(record(), REGISTRY, registry_retrieved_at="2026-10-06T00:00:00Z", company_entity_id=existing)
        self.assertEqual(reused["relationships"][0]["source_entity_id"], existing)
        self.assertFalse(any(v["entity_type"] == "Company" for v in reused["entities"]))

    def test_name_only_html_entities_and_case_numbers_never_become_identifiers(self):
        for label in ("大魯閣實業股份有限公司", "台灣人壽(凌&#2013268209;寶)", "府勞字第1130101133號"):
            source = record()
            source["raw"]["事業單位名稱或負責人"] = label
            self.assertIsNone(explicit_company_identifier(source))
            with self.assertRaises(ValueError):
                build_penalty_bundle(source, REGISTRY, registry_retrieved_at="2026-10-06T00:00:00Z")

    def test_conflicting_ids_names_and_missing_provenance_require_review(self):
        source = record()
        source["uniform_number"] = "23060248"
        self.assertIsNone(explicit_company_identifier(source))
        for change in ({"Company_Name": "另一公司"}, {"Business_Accounting_NO": "23060248"}):
            with self.assertRaises(ValueError):
                build_penalty_bundle(record(), {**REGISTRY, **change}, registry_retrieved_at="2026-10-06T00:00:00Z")
        source = record()
        source.pop("source_file_id")
        with self.assertRaises(ValueError):
            build_penalty_bundle(source, REGISTRY, registry_retrieved_at="2026-10-06T00:00:00Z")
