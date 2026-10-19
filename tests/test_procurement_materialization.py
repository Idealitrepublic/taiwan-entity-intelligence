import copy
import unittest

from src.procurement_materialization import build_contract_bundle, build_official_award_bundle
from scripts.build_procurement_award_bundle import latest_notice


COMPANY_ID = "11111111-1111-4111-8111-111111111111"
UNIFORM = "04690983"
NAME = "大魯閣實業股份有限公司"


def notice():
    return {
        "date": 20260824, "filename": "BDM-1-71265329",
        "unit_id": "3.80.41", "job_number": "115034",
        "brief": {"type": "決標公告", "companies": {
            "id_key": {UNIFORM: ["投標廠商:投標廠商1:廠商代碼"]},
            "name_key": {NAME + " (TRK Corporation)": [
                "投標廠商:投標廠商1:廠商名稱",
                "決標品項:第1品項:得標廠商1:得標廠商"]}}},
        "detail": {
            "已公告資料:標案案號": "115034", "機關資料:機關代碼": "3.80.41",
            "已公告資料:標案名稱": "桃園市親子及樂齡運動科技館委託營運管理案",
            "機關資料:機關名稱": "桃園市政府體育局",
            "決標資料:決標日期": "115/08/21",
            "投標廠商:投標廠商1:廠商代碼": UNIFORM,
            "投標廠商:投標廠商1:廠商名稱": NAME + " (TRK Corporation)",
            "投標廠商:投標廠商1:是否得標": "是",
            "投標廠商:投標廠商1:決標金額": "450,000元",
        },
    }


def bundle(row=None, retrieved="2026-10-18T00:00:00+08:00"):
    return build_contract_bundle(row or notice(), company_entity_id=COMPANY_ID,
                                 company_uniform=UNIFORM, company_name=NAME,
                                 retrieved_at=retrieved)


def official_row():
    return {"source_url": "https://web.pcc.gov.tw/tps/atm/AtmAwardWithoutSso/QueryAtmAwardDetailHist?fkPmsMainHist=OTcxMTg4NjM=",
            "unit_id": "3.80.41", "job_number": "115034",
            "notice_filename": "BDM-1-71265329", "notice_date": "2026-08-24",
            "award_date": "2026-08-21", "bidder_uniform_number": UNIFORM,
            "bidder_name": NAME + " (TRK Corporation)", "winner": True,
            "amount": 450000, "title": "桃園市親子及樂齡運動科技館委託營運管理案",
            "agency": "桃園市政府體育局"}


class ProcurementMaterializationTests(unittest.TestCase):
    def test_official_alphanumeric_agency_code_is_supported(self):
        row = notice()
        row["unit_id"] = "A.47.1.7"
        row["detail"]["機關資料:機關代碼"] = "A.47.1.7"
        result = bundle(row)
        self.assertEqual(result["evidence"][0]["source_locator"]["unit_id"], "A.47.1.7")

    def test_agency_code_rejects_unsafe_characters(self):
        for code in ("A..47", "A/47", "A?47", "A.47 "):
            row = notice()
            row["unit_id"] = code
            row["detail"]["機關資料:機關代碼"] = code
            with self.subTest(code=code), self.assertRaises(ValueError):
                bundle(row)

    def test_official_row_creates_distinct_primary_evidence_and_published_edge(self):
        result = build_official_award_bundle(
            notice(), official=official_row(), company_entity_id=COMPANY_ID,
            company_uniform=UNIFORM, company_name=NAME,
            retrieved_at="2026-10-18T00:00:00+08:00")
        draft = bundle()
        proof, edge = result["evidence"][0], result["relationships"][0]
        self.assertEqual((proof["source_class"], proof["publication_status"]),
                         ("Primary Source", "published"))
        self.assertNotEqual(proof["id"], draft["evidence"][0]["id"])
        self.assertNotEqual(edge["id"], draft["relationships"][0]["id"])
        self.assertEqual(edge["primary_evidence_id"], proof["id"])
        self.assertEqual(edge["status"], "published")
        self.assertEqual(result["entities"][0]["publication_status"], "published")
        self.assertEqual(proof["source_locator"]["mirror_url"], draft["evidence"][0]["source_url"])

    def test_official_row_rejects_wrong_identity_role_amount_or_url(self):
        for key, value in (("bidder_uniform_number", "99999999"),
                           ("winner", False), ("amount", 400000),
                           ("notice_filename", "wrong"), ("job_number", "another"),
                           ("source_url", "https://example.com/QueryAtmAwardDetailHist?id=1")):
            reviewed = official_row()
            reviewed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_official_award_bundle(
                    notice(), official=reviewed, company_entity_id=COMPANY_ID,
                    company_uniform=UNIFORM, company_name=NAME,
                    retrieved_at="2026-10-18T00:00:00+08:00")

    def test_exact_award_preserves_provenance_and_uses_actual_award_day(self):
        result = bundle()
        contract = result["entities"][0]
        edge = result["relationships"][0]
        proof = result["evidence"][0]
        self.assertEqual(contract["entity_type"], "Contract")
        self.assertEqual((edge["source_entity_id"], edge["target_entity_id"]),
                         (COMPANY_ID, contract["id"]))
        self.assertEqual((edge["start_date"], edge["amount"], edge["confidence"]),
                         ("2026-08-21", 450000, "HIGH"))
        self.assertEqual(edge["primary_evidence_id"], proof["id"])
        self.assertEqual((contract["publication_status"], edge["status"],
                          proof["publication_status"]), ("draft", "draft", "draft"))
        self.assertEqual(proof["source_locator"]["notice_date"], "2026-08-24")
        self.assertEqual(proof["source_locator"]["bidder_uniform_number"], UNIFORM)
        self.assertEqual(proof["source_class"], "Derived Data")
        self.assertIn("mirror_warning", proof["source_locator"])

    def test_retry_is_idempotent_despite_retrieval_time(self):
        first = bundle()
        second = bundle(retrieved="2026-10-19T00:00:00+08:00")
        self.assertEqual(first["entities"], second["entities"])
        self.assertEqual(first["relationships"], second["relationships"])
        self.assertEqual(first["evidence"][0]["id"], second["evidence"][0]["id"])

    def test_rejects_name_only_bidder_or_nonwinner(self):
        for mutation in (
            lambda row: row["brief"]["companies"]["id_key"].clear(),
            lambda row: row["detail"].update({"投標廠商:投標廠商1:廠商代碼": ""}),
            lambda row: row["detail"].update({"投標廠商:投標廠商1:是否得標": "否"}),
            lambda row: row["detail"].update({"投標廠商:投標廠商1:廠商名稱": "其他公司"}),
            lambda row: row["brief"].update({"type": "無法決標公告"}),
        ):
            row = copy.deepcopy(notice())
            mutation(row)
            with self.subTest(row=row), self.assertRaises(ValueError):
                bundle(row)

    def test_rejects_mismatched_case_and_ambiguous_bidder(self):
        for mutation in (
            lambda row: row["detail"].update({"已公告資料:標案案號": "another"}),
            lambda row: row["detail"].update({"決標資料:決標日期": "unknown"}),
            lambda row: row["detail"].update({"投標廠商:投標廠商2:廠商代碼": UNIFORM}),
            lambda row: row.update({"filename": ""}),
        ):
            row = copy.deepcopy(notice())
            mutation(row)
            with self.subTest(row=row), self.assertRaises(ValueError):
                bundle(row)

    def test_latest_notice_rejects_stale_or_ambiguous_versions(self):
        older = copy.deepcopy(notice())
        older["date"] = 20260820
        older["filename"] = "older-award"
        self.assertEqual(latest_notice({"records": [notice(), older]},
                                       "BDM-1-71265329")["filename"],
                         "BDM-1-71265329")
        with self.assertRaises(ValueError):
            latest_notice({"records": [notice(), older]}, "older-award")
        conflicting = copy.deepcopy(notice())
        conflicting["filename"] = "other-award"
        with self.assertRaises(ValueError):
            latest_notice({"records": [notice(), conflicting]}, "BDM-1-71265329")


if __name__ == "__main__":
    unittest.main()
