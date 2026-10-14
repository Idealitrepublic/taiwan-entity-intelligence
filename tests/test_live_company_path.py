import unittest
from unittest.mock import Mock, patch

from src.entities.api import dispatch_entity_api
from src.entities.models import stable_id
from src.live_company_path import CompanyRegistryUnavailable, live_company_path


A = "96979933"
B = "97176270"
A_ID = stable_id("entity", "tw:uniform_number", A)
B_ID = stable_id("entity", "tw:uniform_number", B)


def company(uniform, timeout=12):
    return {"Business_Accounting_NO": uniform,
            "Company_Name": "中華電信股份有限公司" if uniform == A else "台灣大哥大股份有限公司"}


def award(uniform, limit=100, timeout=8):
    record = {"id": f"20260921:{uniform}", "date": "20260921",
              "title": "公共通訊服務採購", "agency": "測試機關",
              "unit_id": "A.47.1.7", "job_number": f"JOB-{uniform}",
              "uniform_number": uniform, "award_role": "winner",
              "source_url": f"https://pcc-api.openfun.app/api/tender?uniform={uniform}",
              "official_search_url": "https://web.pcc.gov.tw/prkms/tender/common/basic/indexTenderBasic"}
    return {"status": "ok", "records": [record], "limited": False}


class LiveCompanyPathTests(unittest.TestCase):
    def test_exact_ids_share_official_agency_with_distinct_source_evidence(self):
        result = live_company_path(A, B, company_lookup=company, award_lookup=award,
                                   index_loader=lambda: {"records": []})
        self.assertTrue(result["found"])
        self.assertEqual(result["depth"], 2)
        self.assertEqual(result["shared_node_type"], "GovernmentAgency")
        first, second = result["segments"]
        self.assertEqual(first["from_entity"]["id"], A_ID)
        self.assertEqual(first["to_entity"]["id"], second["from_entity"]["id"])
        self.assertEqual(second["to_entity"]["id"], B_ID)
        self.assertEqual(second["traversal_direction"], "reverse")
        self.assertNotEqual(first["evidence"]["id"], second["evidence"]["id"])
        self.assertTrue(all(segment["evidence"]["source_url"] and
                            segment["evidence"]["retrieved_at"] and
                            segment["evidence"]["provenance"]
                            for segment in result["segments"]))
        self.assertIn("不代表", result["interpretation"])

    def test_shared_judgment_requires_exact_distinct_official_names(self):
        row = {"jid": "PTDV,115,民,1,20260921,1", "title": "司法院裁判書",
               "companies": ["中華電信股份有限公司", "台灣大哥大股份有限公司"],
               "source_url": "https://judgment.judicial.gov.tw/FJUD/printData.aspx?id=case",
               "retrieved_at": "2026-09-22T00:00:00Z", "date": "2026-09-21"}
        result = live_company_path(A, B, company_lookup=company,
                                   award_lookup=lambda *args, **kwargs: {"status": "partial", "records": []},
                                   index_loader=lambda: {"records": [row]})
        self.assertTrue(result["found"])
        self.assertEqual(result["shared_node_type"], "Judgment")
        self.assertEqual(result["segments"][0]["evidence"]["source_record_id"], row["jid"])
        self.assertEqual(result["segments"][1]["relationship"]["relationship_type"],
                         "RELATED_TO_JUDGMENT")

    def test_same_name_or_substring_is_not_an_identity_match(self):
        def same_name(uniform, timeout=12):
            return {"Business_Accounting_NO": uniform,
                    "Company_Name": "同名股份有限公司"}
        row = {"jid": "case", "companies": ["同名股份有限公司"],
               "source_url": "https://judgment.judicial.gov.tw/FJUD/printData.aspx?id=case"}
        result = live_company_path(A, B, company_lookup=same_name,
                                   award_lookup=lambda *args, **kwargs: {"status": "partial", "records": []},
                                   index_loader=lambda: {"records": [row]})
        self.assertFalse(result["found"])
        row["companies"] = ["疑似同名股份有限公司", "其他企業有限公司"]
        result = live_company_path(A, B, company_lookup=company,
                                   award_lookup=lambda *args, **kwargs: {"status": "partial", "records": []},
                                   index_loader=lambda: {"records": [row]})
        self.assertFalse(result["found"])

    def test_direct_range_does_not_invent_an_edge(self):
        result = live_company_path(A, B, max_depth=1, company_lookup=company,
                                   award_lookup=award, index_loader=lambda: {"records": []})
        self.assertFalse(result["found"])
        self.assertEqual(result["segments"], [])

    def test_missing_or_unavailable_registry_is_not_a_false_empty_path(self):
        self.assertIsNone(live_company_path(
            A, B, company_lookup=lambda uniform, timeout=12: None,
            award_lookup=award, index_loader=lambda: {"records": []}))
        with self.assertRaises(CompanyRegistryUnavailable):
            live_company_path(A, B,
                              company_lookup=lambda uniform, timeout=12: 1 / 0,
                              award_lookup=award, index_loader=lambda: {"records": []})

    def test_live_api_skips_canonical_store_and_rejects_mismatched_id(self):
        repository = Mock()
        query = {"source": [A_ID], "target": [B_ID], "max_depth": ["2"],
                 "company_only": ["1"], "source_uniform": [A], "target_uniform": [B],
                 "live": ["1"]}
        with patch("src.entities.api.live_company_path", return_value={"found": False}) as finder:
            status, payload, _ = dispatch_entity_api("/api/v1/paths", query, repository)
        self.assertEqual(status, 200)
        self.assertFalse(payload["data"]["found"])
        finder.assert_called_once_with(A, B, max_depth=2)
        repository.company_relationship_path.assert_not_called()
        self.assertEqual(dispatch_entity_api("/api/v1/paths", {
            **query, "source": [B_ID]}, repository)[0], 400)

    def test_published_path_precedes_live_fallback(self):
        repository = Mock()
        repository.company_relationship_path.return_value = {"found": True, "depth": 1}
        query = {"source": [A_ID], "target": [B_ID], "max_depth": ["3"],
                 "company_only": ["1"], "source_uniform": [A], "target_uniform": [B]}
        with patch("src.entities.api.live_company_path") as finder:
            status, payload, _ = dispatch_entity_api("/api/v1/paths", query, repository)
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["depth"], 1)
        finder.assert_not_called()

    def test_shorter_live_shared_node_precedes_three_hop_published_path(self):
        repository = Mock()
        repository.company_relationship_path.return_value = {"found": True, "depth": 3}
        query = {"source": [A_ID], "target": [B_ID], "max_depth": ["3"],
                 "company_only": ["1"], "source_uniform": [A], "target_uniform": [B]}
        with patch("src.entities.api.live_company_path", return_value={"found": True, "depth": 2}) as finder:
            status, payload, _ = dispatch_entity_api("/api/v1/paths", query, repository)
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["depth"], 2)
        finder.assert_called_once()


if __name__ == "__main__":
    unittest.main()
