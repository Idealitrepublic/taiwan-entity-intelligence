import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.sync_moea_officers_dev import prepare
from src import cloud_company


class OfficerSnapshotTests(unittest.TestCase):
    def test_official_csv_stages_exact_company_id_and_row_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            source, stage = Path(directory) / "official.csv", Path(directory) / "stage.csv"
            with source.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["統一編號", "公司名稱", "職稱", "姓名", "所代表法人", "持有股份數"])
                writer.writeheader()
                writer.writerow({"統一編號": "96979933", "公司名稱": "中華電信股份有限公司", "職稱": "董事", "姓名": "測試人物", "所代表法人": "", "持有股份數": "1"})
                writer.writerow({"統一編號": "invalid", "公司名稱": "同名公司", "職稱": "董事", "姓名": "測試人物", "所代表法人": "", "持有股份數": "1"})
            digest, valid, invalid = prepare(source, stage)
            self.assertEqual((valid, invalid), (1, 1))
            with stage.open(encoding="utf-8", newline="") as stream:
                record = next(csv.reader(stream))
            self.assertEqual(record[1], "96979933")
            self.assertEqual(json.loads(record[2])["_source_row"], 2)
            self.assertIn(digest, record[0])

    def test_missing_official_columns_cannot_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            source, stage = Path(directory) / "bad.csv", Path(directory) / "stage.csv"
            source.write_text("統一編號,姓名\n96979933,某人\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                prepare(source, stage)

    def test_officer_snapshot_does_not_create_cross_company_person_identity(self):
        company = {"Business_Accounting_NO": "96979933", "Company_Name": "中華電信股份有限公司"}
        officer = {"統一編號": "96979933", "姓名": "同名人物", "職稱": "董事", "_source_row": 72}
        file = {"source_url": "https://data.gov.tw/dataset/96731", "downloaded_at": "2026-10-22T00:00:00+00:00"}
        with patch.object(cloud_company, "_moea_rows", side_effect=[TimeoutError(), TimeoutError()]), \
             patch.object(cloud_company, "_published_registry_snapshot", return_value={"company": company, "evidence": {"retrieved_at": "2026-10-20T00:00:00+00:00"}}), \
             patch.object(cloud_company, "_published_officer_snapshot", return_value=([officer], file)), \
             patch.object(cloud_company, "_supabase_evidence", return_value=([], True)), \
             patch.object(cloud_company, "_supabase_company", return_value=None):
            result = cloud_company.build_company("96979933")
        self.assertEqual(result["people"][0]["position"], "董事")
        self.assertEqual(result["officer_snapshot_retrieved_at"], file["downloaded_at"])
        self.assertEqual(result["graph"]["edges"][0]["evidence"]["source_locator"],
                         "Business_Accounting_NO=96979933;row=72")
        self.assertFalse(result["graph"]["edges"][0]["properties"]["live"])
        self.assertEqual(result["graph"]["nodes"][1]["properties"]["identity_status"], "source_scoped_observation")

    def test_public_fallback_queries_latest_complete_file_and_exact_uniform(self):
        files = [{"id": "file-id", "source_url": "https://data.gov.tw/dataset/96731",
                  "downloaded_at": "2026-10-22T00:00:00+00:00"}]
        rows = [{"raw": {"統一編號": "96979933", "姓名": "某人", "職稱": "董事"}}]
        with patch.object(cloud_company, "SUPABASE_KEY", "public-test-key"), \
             patch.object(cloud_company.urllib.request, "urlopen",
                          side_effect=[io.BytesIO(json.dumps(files).encode()),
                                       io.BytesIO(json.dumps(rows, ensure_ascii=False).encode())]) as fetch:
            result, file = cloud_company._published_officer_snapshot("96979933")
        self.assertEqual(result[0]["姓名"], "某人")
        self.assertEqual(file["id"], "file-id")
        self.assertIn("status=eq.indexed", fetch.call_args_list[0].args[0].full_url)
        self.assertIn("uniform_number=eq.96979933", fetch.call_args_list[1].args[0].full_url)
        self.assertNotIn("company_name", fetch.call_args_list[1].args[0].full_url)
