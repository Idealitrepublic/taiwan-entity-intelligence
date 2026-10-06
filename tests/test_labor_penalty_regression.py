import unittest
from unittest.mock import patch

from scripts.ingest_labor_penalties_dev import indexed_rows, official_rows, sql_snapshot
from src.cloud_company import build_company
from src.public_evidence import _dataset_resources
from src.sources.public_records import dataset_meta, resource_urls


class LaborPenaltyRegressionTests(unittest.TestCase):
    def test_official_catalog_nested_result_and_camelcase_resource(self):
        metadata = {"result": {"distribution": [{"resourceFormat": "CSV",
                     "resourceDownloadUrl": "https://apiservice.mol.gov.tw/correct.csv"}]}}
        with patch("src.public_evidence._json", return_value=metadata):
            self.assertEqual(_dataset_resources("109896"),
                             ["https://apiservice.mol.gov.tw/correct.csv"])
        with patch("src.sources.public_records.fetch", return_value=b'{"result":{"distribution":[{"resourceFormat":"CSV","resourceDownloadUrl":"https://example.gov.tw/labor.csv"}]}}'):
            self.assertEqual(dataset_meta("109896")["distribution"][0]["resourceFormat"], "CSV")
            self.assertEqual(resource_urls("109896"), ["https://example.gov.tw/labor.csv"])

    def test_import_retains_actual_official_raw_and_external_provenance(self):
        row = {"主管機關": "臺北市政府", "處分日期": "2026/01/01", "處分字號": "府勞字第1號",
               "事業單位名稱或負責人": "全家便利商店股份有限公司", "違法法規法條": "勞動基準法第24條",
               "違反法規內容": "官方紀錄", "罰鍰金額": "20000"}
        indexed = indexed_rows("109896", [row])
        self.assertEqual(indexed[0][1], row["事業單位名稱或負責人"])
        self.assertIn("府勞字第1號", indexed[0][-1])
        sql = sql_snapshot("109896", "https://example.gov.tw/labor.csv", b"official csv", [row])
        self.assertIn("external_source_only", sql)
        self.assertIn("source_records", sql)
        self.assertIn("ON CONFLICT (id) DO NOTHING", sql)

    def test_import_skips_unrelated_resource_instead_of_publish_false_rows(self):
        unrelated = "年度（西元）,內容/調整金額\n2026,100\n".encode()
        official = ("主管機關,處分日期,處分字號,事業單位名稱或負責人,違法法規法條\n"
                    "臺北市政府,20260101,府勞字第1號,全家便利商店股份有限公司,勞動基準法第24條\n").encode()
        with patch("scripts.ingest_labor_penalties_dev._dataset_resources", return_value=["wrong", "correct"]), \
             patch("scripts.ingest_labor_penalties_dev._get", side_effect=[unrelated, official]):
            url, _, rows = official_rows("109896")
        self.assertEqual(url, "correct")
        self.assertEqual(len(rows), 1)

    def test_company_api_projection_restores_penalty_evidence_and_graph(self):
        base = {"status": "ok", "uniform_number": "23060248", "company_name": "全家便利商店股份有限公司",
                "website_url": None, "evidence": [], "evidence_status": {},
                "graph": {"nodes": [], "edges": []}}
        record = {"id": "mol:abc", "dataset": "penalties", "company_name": base["company_name"],
                  "uniform_number": None, "title": "勞動基準法第24條", "summary": "官方紀錄",
                  "source_url": "https://data.gov.tw/dataset/109896", "source_file_id": "official-snapshot",
                  "indexed_at": "2026-01-02T00:00:00Z",
                  "raw": {"處分字號": "府勞字第1號", "處分日期": "2026/01/01"}}
        judicial = {"records": [], "status": "ok", "matched": 0,
                    "coverage_note": "索引", "interpretation": "非法律結論", "match_rule": "exact"}
        with patch("src.cloud_company._base_company", return_value=base), \
             patch("src.cloud_company.indexed_records", return_value=[record]), \
             patch("src.cloud_company.records_for_company", return_value=judicial):
            result = build_company("23060248")
        self.assertEqual(result["evidence_status"]["裁罰"]["matched"], 1)
        self.assertEqual(result["labor_penalties"][0]["_retrieved_at"], record["indexed_at"])
        self.assertEqual(result["graph"]["edges"][0]["properties"]["match_rule"],
                         "exact_company_name_candidate")
        self.assertEqual(result["evidence"][0]["source_url"], record["source_url"])
        self.assertEqual(result["evidence"][0]["source_record_id"], "府勞字第1號")


if __name__ == "__main__":
    unittest.main()
