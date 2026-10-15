"""Automatic company-graph discovery must use exact IDs and real source records."""
import unittest
from unittest.mock import patch

from app import dispatch
from src.live_related_companies import _juristic_company, related_companies
from src.sources import procurement


def registry(uniform, timeout=6):
    names = {"22099131": "台灣積體電路製造股份有限公司",
             "12345678": "法人甲股份有限公司",
             "87654321": "共同得標乙股份有限公司"}
    return {"Business_Accounting_NO": uniform, "Company_Name": names[uniform]}


def award_notice(other_role="得標廠商", *, same_day_conflict=False):
    row = {"date": "20261015", "filename": "award.xml", "unit_id": "A.1",
           "job_number": "P-1", "brief": {"type": "決標公告", "title": "公開採購案",
           "companies": {"names": ["台灣積體電路製造股份有限公司", "共同得標乙股份有限公司"],
           "id_key": {"22099131": ["投標廠商:投標廠商1:廠商代碼"],
                      "87654321": ["投標廠商:投標廠商2:廠商代碼"]},
           "name_key": {"台灣積體電路製造股份有限公司": ["投標廠商:投標廠商1:廠商名稱",
                                           "決標品項:第1品項:得標廠商1:廠商名稱"],
                        "共同得標乙股份有限公司": ["投標廠商:投標廠商2:廠商名稱",
                                            f"決標品項:第1品項:{other_role}2:廠商名稱"]}}}}
    if same_day_conflict:
        row["brief"]["companies"]["names"].append("第三公司")
    return row


class AutoRelatedCompanyTests(unittest.TestCase):
    def test_exact_corporate_director_and_exact_coaward_have_evidence(self):
        director_rows = [{"Juristic_Person_Name": "法人甲股份有限公司",
                          "Person_Name": "同名人物", "Person_Position_Name": "董事"},
                         {"Juristic_Person_Name": "同名人物",
                          "Person_Name": "同名人物", "Person_Position_Name": "董事"}]
        with patch.object(procurement, "_json_get", return_value={
                "records": [award_notice()], "total_records": 1}):
            result = related_companies(
                "22099131", company_lookup=registry,
                director_lookup=lambda uniform: director_rows,
                name_lookup=lambda name: [{"Business_Accounting_NO": "12345678",
                                           "Company_Name": "法人甲股份有限公司"}]
                if name == "法人甲股份有限公司" else [],
                coaward_lookup=procurement.lookup_co_awardees)
        self.assertEqual([row["uniform_number"] for row in result["items"]],
                         ["12345678", "87654321"])
        self.assertEqual([row["connection_type"] for row in result["items"]],
                         ["corporate_director", "same_award_notice"])
        for row in result["items"]:
            self.assertTrue(row["evidence"]["source_url"].startswith("https://"))
            self.assertTrue(row["evidence"]["source_record_id"])
            self.assertTrue(row["evidence"]["retrieved_at"])
        self.assertEqual(result["items"][0]["evidence"]["locator_type"],
                         "query_locator_not_official_record_id")
        self.assertIn("不代表", result["interpretation"])

    def test_name_only_ambiguous_or_mismatched_identity_is_rejected(self):
        self.assertIsNone(_juristic_company("同名人物", lambda _: []))
        self.assertIsNone(_juristic_company("法人甲股份有限公司", lambda _: [
            {"Business_Accounting_NO": "12345678", "Company_Name": "法人甲股份有限公司"},
            {"Business_Accounting_NO": "99999999", "Company_Name": "法人甲股份有限公司"}]))
        self.assertIsNone(_juristic_company("法人甲股份有限公司", lambda _: [
            {"Business_Accounting_NO": "12345678", "Company_Name": "相似法人甲股份有限公司"}]))
        result = related_companies("22099131", company_lookup=registry,
            director_lookup=lambda _: [{"Juristic_Person_Name": "同名人物"}],
            name_lookup=lambda _: [],
            coaward_lookup=lambda *args, **kwargs: {"status": "ok", "items": [{
                "uniform_number": "87654321", "company_name": "錯誤公司名股份有限公司",
                "notice": {"id": "notice", "source_url": "https://pcc-api.openfun.app/notice"}}],
                "limited": False})
        self.assertEqual(result["items"], [])

    def test_coaward_requires_both_exact_winner_identifiers(self):
        for role in ("未得標廠商", "候選廠商"):
            with patch.object(procurement, "_json_get", return_value={"records": [award_notice(role)]}):
                self.assertEqual(procurement.lookup_co_awardees("22099131")["items"], [])
        row = award_notice()
        del row["brief"]["companies"]["id_key"]["87654321"]
        with patch.object(procurement, "_json_get", return_value={"records": [row]}):
            self.assertEqual(procurement.lookup_co_awardees("22099131")["items"], [])
        with patch.object(procurement, "_json_get", return_value={
                "records": [award_notice(), award_notice(same_day_conflict=True)]}):
            self.assertEqual(procurement.lookup_co_awardees("22099131")["items"], [])

    def test_route_is_bounded_and_read_only(self):
        self.assertEqual(dispatch("/api/company-related/not-an-id", {})[0], 400)
        self.assertEqual(dispatch("/api/company-related/22099131", {}, method="POST")[0], 405)
        with patch("app.related_companies", return_value={"status": "ok", "items": []}) as finder:
            status, payload, _ = dispatch("/api/company-related/22099131", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["items"], [])
        finder.assert_called_once_with("22099131")


if __name__ == "__main__":
    unittest.main()
