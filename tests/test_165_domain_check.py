"""165 lookup must distinguish an empty Development index from an exact miss."""
from io import BytesIO
import json
import unittest
from unittest.mock import patch

from src import cloud_company


class DomainCheckTests(unittest.TestCase):
    def test_missing_index_is_unavailable_not_a_safety_result(self):
        with patch.object(cloud_company, "SUPABASE", "https://development.invalid"), \
             patch.object(cloud_company, "SUPABASE_KEY", "public-test-key"), \
             patch.object(cloud_company.urllib.request, "urlopen", return_value=BytesIO(b"[]")) as get:
            result = cloud_company.check_domain("https://www.example.tw/path")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["anti_fraud"]["status"], "unavailable")
        self.assertEqual(get.call_count, 1)

    def test_indexed_snapshot_and_exact_match_keep_source(self):
        snapshot = b'[{"id":"one","indexed_at":"2026-10-21T00:00:00Z","metadata":{"row_count":100},"source_url":"https://data.gov.tw/dataset/176455"}]'
        record = json.dumps([{"id": "r1", "title": "165 official",
                              "raw": {"網域": "example.tw"},
                              "source_url": "https://data.gov.tw/dataset/176455"}]).encode()
        with patch.object(cloud_company, "SUPABASE", "https://development.invalid"), \
             patch.object(cloud_company, "SUPABASE_KEY", "public-test-key"), \
             patch.object(cloud_company.urllib.request, "urlopen",
                          side_effect=[BytesIO(snapshot), BytesIO(record)]) as get:
            result = cloud_company.check_domain("www.example.tw")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["anti_fraud"]["matched"], 1)
        self.assertEqual(result["anti_fraud"]["rule"], "exact_domain")
        self.assertEqual(result["anti_fraud"]["records"][0]["source_url"],
                         "https://data.gov.tw/dataset/176455")
        self.assertIn("source_files", get.call_args_list[0].args[0].full_url)
        self.assertIn("domain=eq.example.tw", get.call_args_list[1].args[0].full_url)
        self.assertIn("source_file_id=eq.one", get.call_args_list[1].args[0].full_url)


if __name__ == "__main__":
    unittest.main()
