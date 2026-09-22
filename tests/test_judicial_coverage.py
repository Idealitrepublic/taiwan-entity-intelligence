import unittest
from unittest.mock import patch

from scripts.judicial_coverage import benchmark
from src.sources import judicial
from src.sources.judicial_index import build_index, company_names, records_for_company

JID = "KLDM,111,訴,328,20230428,1"
OTHER = "KLDV,112,訴,364,20231003,1"


class JudicialCoverageTests(unittest.TestCase):
    def test_jlist_accepts_official_case_variants_and_deduplicates(self):
        with patch.object(judicial, "post", return_value=[
            {"DATE": "2026-09-22", "LIST": [JID, JID]},
            {"date": "2026-09-23", "list": [OTHER]}]):
            self.assertEqual(judicial.changed_jids("token"), [JID, OTHER])

    def test_jlist_errors_are_not_empty_success(self):
        for response in ({"error": "驗證失敗"}, {}, [{"date": "2026-09-22"}]):
            with self.subTest(response=response), patch.object(judicial, "post", return_value=response):
                with self.assertRaises((RuntimeError, ValueError)):
                    judicial.changed_jids("token")

    def test_invalid_jid_error_retains_bounded_escaped_diagnostic(self):
        with self.assertRaisesRegex(ValueError, "Invalid judicial JID") as caught:
            judicial.normalize_jid("bad\n" + "x" * 200)
        self.assertLess(len(str(caught.exception)), 150)
        self.assertIn("\\n", str(caught.exception))

    def test_official_jlist_five_part_id_without_final_sequence(self):
        five_part = "JCCC,115,審裁,1234,20260722"
        self.assertEqual(judicial.normalize_jid(five_part), five_part)
        with patch.object(judicial, "post", return_value=[{"LIST": [five_part, JID]}]):
            self.assertEqual(judicial.changed_jids("token"), [five_part, JID])

    def test_case_date_and_wrapped_company_name_normalize(self):
        self.assertEqual(judicial.normalize_jdate("2023-04-28"), "2023-04-28")
        self.assertTrue(any("御首服務事業有限公司" in name for name in
                            company_names("御首服務事業有\n限公司")))
        with self.assertRaises(ValueError):
            judicial.normalize_jdate("2023-02-30")

    def test_jdoc_preserves_official_id_date_provenance_and_corrections(self):
        documents = iter([
            {"JID": JID, "JDATE": "20230428", "JTITLE": "刑事判決",
             "JFULLX": {"JFULLCONTENT": "御首服務事業有限公司"}},
            {"JID": JID, "JDATE": "2023-04-28", "JTITLE": "刑事判決",
             "JFULLX": {"JFULLCONTENT": "御首服務事業有限公司（更正）"}},
        ])
        with patch.object(judicial, "get_token", return_value="token"), \
             patch.object(judicial, "changed_jids", return_value=[JID]), \
             patch.object(judicial, "fetch_judgment", side_effect=lambda *_: next(documents)):
            first = list(judicial.evidence_rows())[0]
            second = list(judicial.evidence_rows())[0]
        self.assertEqual(first["source"]["record_id"], JID)
        self.assertEqual(first["source"]["published_at"], "2023-04-28")
        self.assertIn("printData.aspx", first["source"]["url"])
        self.assertIsNotNone(first["retrieved_at"])
        self.assertNotEqual(first["evidence_id"], second["evidence_id"])
        self.assertNotEqual(first["source"]["content_hash"], second["source"]["content_hash"])

    def test_jdoc_auth_failure_is_not_removal(self):
        with patch.object(judicial, "get_token", return_value="token"), \
             patch.object(judicial, "changed_jids", return_value=[JID]), \
             patch.object(judicial, "fetch_judgment", return_value={"error": "驗證失敗"}):
            with self.assertRaises(RuntimeError):
                list(judicial.evidence_rows())

    def test_jdoc_server_failure_is_reported_without_losing_other_cases(self):
        failures = []
        with patch.object(judicial, "get_token", return_value="token"), \
             patch.object(judicial, "changed_jids", return_value=[JID, OTHER]), \
             patch.object(judicial, "fetch_judgment", side_effect=[
                 {"error": "並未將物件參考設定為物件的執行個體。"},
                 {"JID": OTHER, "JDATE": "20231003", "JTITLE": "判決",
                  "JFULLX": {"JFULLCONTENT": "御首服務事業有限公司"}}]):
            rows = list(judicial.evidence_rows(on_error=lambda jid, exc: failures.append((jid, exc))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"]["record_id"], OTHER)
        self.assertEqual(failures[0][0], JID)

    def test_empty_jdoc_is_not_a_valid_judgment(self):
        with patch.object(judicial, "get_token", return_value="token"), \
             patch.object(judicial, "changed_jids", return_value=[JID]), \
             patch.object(judicial, "fetch_judgment", return_value={"JID": JID}):
            with self.assertRaises(ValueError):
                list(judicial.evidence_rows())

    def test_latest_removal_retracts_from_generated_index(self):
        with patch.object(judicial, "get_token", return_value="token"), \
             patch.object(judicial, "changed_jids", return_value=[JID]), \
             patch.object(judicial, "fetch_judgment", return_value={"error": "已移除"}):
            removed = list(judicial.evidence_rows())[0]
        active = {**removed, "status": "active", "retrieved_at": "2020-01-01T00:00:00Z",
                  "fact": {"type": "court_record", "title": "刑事判決",
                           "summary": "御首服務事業有限公司"}}
        index = build_index([active, removed])
        self.assertEqual(index["records"], [])
        self.assertEqual(index["removed_jids"], [JID])

    def test_verified_historical_cases_are_queryable_with_source(self):
        result = records_for_company("御首服務事業有限公司")
        self.assertEqual(result["status"], "ok")
        self.assertTrue({JID, OTHER}.issubset({row["jid"] for row in result["records"]}))
        self.assertTrue(all(row["source_url"] and row["retrieved_at"]
                            for row in result["records"] if row["jid"] in {JID, OTHER}))
        self.assertEqual(records_for_company("不存在測試股份有限公司")["status"], "partial")

    def test_benchmark_reports_sample_scope_and_no_duplicate(self):
        result = benchmark()
        self.assertEqual(result["verified_case_recall"], 1.0)
        self.assertEqual(result["duplicate_jids"], 0)
        self.assertIn("not nationwide", result["coverage_scope"])


if __name__ == "__main__":
    unittest.main()
