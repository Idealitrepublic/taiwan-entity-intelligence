import unittest
from unittest.mock import patch

from src.entities.models import evidence_from_projection, stable_id
from scripts import prepare_reviewed_political_dev as reviewed


class ReviewedPoliticalDevelopmentTests(unittest.TestCase):
    def setUp(self):
        self.row = {"序號": "886", "擬參選人／政黨": "王鴻薇",
                    "選舉名稱": "113年立法委員選舉", "申報序號／年度": "首次申報",
                    "交易日期": "1120801", "收支科目": "營利事業捐贈收入",
                    "捐贈者／支出對象": "都一處有限公司",
                    "身分證／統一編號": "29072066", "收入金額": "50000.00"}
        proof = evidence_from_projection(
            source_name="監察院廉政專刊財產申報資料",
            source_record_id="gazette:319:printed-page-37:huang-shan-shan:vehicle-1",
            source_class="Primary Source", source_url="https://cy.gov.tw/example.pdf",
            source_locator={"declarant_name": "黃珊珊", "office": "立法委員",
                            "declaration_date": "2026-02-01"},
            title="黃珊珊汽車申報", summary="Tesla 汽車",
            observed_at="2026-02-01T00:00:00+08:00",
            retrieved_at="2026-09-23T00:00:00+00:00")
        self.asset = (proof.to_dict(), {
            "id": stable_id("asset_declaration", "fixture", "one"),
            "declaration_key": "a" * 64})

    def prepare(self):
        with patch.object(reviewed, "_moea_rows", return_value=[
                 {"Business_Accounting_NO": "29072066", "Company_Name": "都一處有限公司"}]), \
             patch.object(reviewed, "records", return_value=iter([self.row])), \
             patch.object(reviewed, "asset_extract", return_value=self.asset):
            return reviewed.prepare(wang_master_evidence_id="73afd4ae-180b-5717-a378-9fb954aee973",
                                    huang_master_evidence_id="5fed7a04-25cd-5838-88d9-b5fdc368554b",
                                    reviewed_by="test reviewer",
                                    retrieved_at="2026-09-23T00:00:00+00:00")

    def test_review_requires_exact_company_and_contextual_official_chain(self):
        output = self.prepare()
        self.assertEqual(output["quality"]["name_only_matches"], 0)
        self.assertEqual(output["quality"]["company_exact_uniform_matches"], 1)
        self.assertEqual(output["contribution_bundle"]["relationships"][0]["confidence"], "HIGH")
        self.assertEqual(output["crosswalks"][0]["official_legislator_number"], "00007")
        self.assertEqual(output["crosswalks"][1]["official_legislator_number"], "00082")
        self.assertEqual(output["contribution_bundle"]["evidence"][0]
                         ["source_locator"]["politician_identifier_origin"], "reviewed_crosswalk")

    def test_candidate_name_change_never_auto_merges(self):
        self.row["擬參選人／政黨"] = "同名測試"
        with self.assertRaisesRegex(ValueError, "filing row changed"):
            self.prepare()


if __name__ == "__main__":
    unittest.main()
