import unittest
import urllib.error
from http.client import RemoteDisconnected
from unittest.mock import patch

from scripts.judicial_coverage import benchmark
from src.sources import judicial
from src.sources.judicial_index import build_index, company_names, records_for_company

JID = "KLDM,111,訴,328,20230428,1"
OTHER = "KLDV,112,訴,364,20231003,1"


class JudicialCoverageTests(unittest.TestCase):
    def test_http_rate_limit_retries_without_logging_token(self):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return b'{"ok":true}'

        limited = urllib.error.HTTPError("https://data.judicial.gov.tw/jdg/api/JDoc",
                                         429, "rate limited", {"Retry-After": "2"}, None)
        with patch.object(judicial.urllib.request, "urlopen", side_effect=[limited, Response()]) as opener, \
             patch.object(judicial.time, "sleep") as sleep:
            payload, meta = judicial.post("/JDoc", {"token": "private-token"}, with_meta=True)
        self.assertTrue(payload["ok"])
        self.assertEqual(meta["http_status"], 200)
        self.assertEqual(meta["attempts"], 2)
        self.assertEqual(opener.call_count, 2)
        sleep.assert_called_once_with(2)
        self.assertNotIn("private-token", str(meta))

    def test_timeout_is_bounded_and_sanitized(self):
        with patch.object(judicial.urllib.request, "urlopen", side_effect=TimeoutError), \
             patch.object(judicial.time, "sleep"):
            with self.assertRaises(judicial.JudicialRequestError) as caught:
                judicial.post("/JDoc", {"token": "private-token"})
        self.assertEqual(caught.exception.diagnostic["error_type"], "timeout")
        self.assertEqual(caught.exception.diagnostic["attempts"], 4)
        self.assertNotIn("private-token", str(caught.exception.diagnostic))

    def test_auth_service_hours_error_is_classified_without_credentials(self):
        with patch.dict("os.environ", {"JUDICIAL_USER": "private-user",
                                       "JUDICIAL_PASSWORD": "private-password"}), \
             patch.object(judicial, "post", return_value=(
                 {"error": "目前非本 API 服務時間。"},
                 {"http_status": 200, "attempts": 1, "elapsed_ms": 40})):
            with self.assertRaises(judicial.JudicialRequestError) as caught:
                judicial.get_token()
        self.assertEqual(caught.exception.diagnostic["error_type"], "service_closed")
        self.assertEqual(caught.exception.diagnostic["request"]["endpoint"], "/Auth")
        self.assertNotIn("private", str(caught.exception.diagnostic))

    def test_jdoc_service_hours_error_is_not_permanent_document_error(self):
        with patch.object(judicial, "post", return_value=(
                 {"error": "目前非本 API 服務時間。"},
                 {"http_status": 200, "attempts": 1})):
            with self.assertRaises(judicial.JudicialRequestError) as caught:
                judicial.fetch_judgment("token", JID)
        self.assertEqual(caught.exception.diagnostic["error_type"], "service_closed")

    def test_remote_disconnect_is_retryable_transport_error(self):
        with patch.object(judicial.urllib.request, "urlopen",
                          side_effect=RemoteDisconnected("closed")), \
             patch.object(judicial.time, "sleep"):
            with self.assertRaises(judicial.JudicialRequestError) as caught:
                judicial.post("/JDoc", {"token": "private-token"})
        self.assertEqual(caught.exception.diagnostic["error_type"], "transport_error")
        self.assertEqual(caught.exception.diagnostic["attempts"], 4)

    def test_repeated_jdoc_body_error_has_safe_fingerprint(self):
        payload = ({"error": "並未將物件參考設定為物件的執行個體。"},
                   {"http_status": 200, "attempts": 1})
        with patch.object(judicial, "post", return_value=payload), \
             patch.object(judicial.time, "sleep"):
            with self.assertRaises(judicial.JudicialRequestError) as caught:
                judicial.fetch_judgment("private-token", JID)
        self.assertEqual(caught.exception.diagnostic["http_status"], 200)
        self.assertEqual(caught.exception.diagnostic["attempts"], 2)
        self.assertEqual(len(caught.exception.diagnostic["response_error_hash"]), 64)
        self.assertNotIn("private-token", str(caught.exception.diagnostic))

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

    def test_transient_jdoc_body_error_is_retried_but_not_hidden(self):
        with patch.object(judicial, "post", side_effect=[
                 ({"error": "並未將物件參考設定為物件的執行個體。"},
                  {"http_status": 200, "attempts": 1}),
                 ({"JID": JID, "JDATE": "20230428", "JFULLX": {"JFULLCONTENT": "test"}},
                  {"http_status": 200, "attempts": 1})]) as post, \
             patch.object(judicial.time, "sleep"):
            self.assertEqual(judicial.fetch_judgment("token", JID)["JID"], JID)
        self.assertEqual(post.call_count, 2)

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

    def test_jdoc_batch_is_bounded_and_reports_progress(self):
        progress = {}
        with patch.object(judicial, "get_token", return_value="token"), \
             patch.object(judicial, "changed_jids", return_value=[JID, OTHER]), \
             patch.object(judicial, "fetch_judgment", return_value={"JID": OTHER, "JDATE": "20231003", "JFULLX": {"JFULLCONTENT": "test"}}) as fetch:
            rows = list(judicial.evidence_rows(batch_index=1, batch_size=1,
                                                on_window=progress.update))
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(rows[0]["source"]["record_id"], OTHER)
        self.assertEqual(progress["total"], 2)
        self.assertEqual(progress["batch_index"], 1)
        self.assertEqual(progress["remaining"], 0)
        self.assertEqual(len(progress["window_id"]), 64)

    def test_jdoc_batch_rejects_unbounded_request(self):
        with self.assertRaises(ValueError):
            list(judicial.evidence_rows(batch_size=501))

    def test_retry_window_uses_fresh_jlist_total(self):
        window = {}
        with patch.object(judicial, "get_token", return_value="token"), \
             patch.object(judicial, "changed_jids", return_value=[JID]), \
             patch.object(judicial, "fetch_judgment", return_value={"JID": JID, "JDATE": "20230428",
                                                                  "JFULLX": {"JFULLCONTENT": "test"}}):
            list(judicial.evidence_rows(retry_jids=[JID], retry_window={"total": 0},
                                        on_window=window.update))
        self.assertEqual(window["total"], 1)
        self.assertTrue(window["retry_only"])

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
