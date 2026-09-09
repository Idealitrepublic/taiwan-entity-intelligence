import unittest
from unittest.mock import patch

from src import cloud_company as api_index


class VercelCoreTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(api_index, "indexed_records", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_core_company_uses_dict_rows_and_fails_open_on_director_error(self):
        def fake_filter(api, value, top):
            if api == api_index.COMPANY_API:
                return [{
                    "Business_Accounting_NO": value,
                    "Company_Name": "測試股份有限公司",
                }]
            raise RuntimeError("director upstream unavailable")

        with patch.object(api_index, "_moea_rows", side_effect=fake_filter), \
             patch.object(api_index, "_supabase_evidence", return_value=([], False)), patch.object(api_index, "_supabase_company", return_value=None):
            data = api_index.build_company("12345678")

        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["company_name"], "測試股份有限公司")
        self.assertEqual(data["people"], [])
        self.assertEqual(data["graph"]["edges"], [])
        self.assertEqual(data["evidence_status"]["董監事"]["status"], "partial")

    def test_core_company_does_not_call_public_evidence_collector(self):
        calls = {"company": 0, "director": 0}

        def fake_filter(api, value, top):
            if api == api_index.COMPANY_API:
                calls["company"] += 1
                return [{"Company_Name": "隔離測試公司"}]
            calls["director"] += 1
            return [{"Person_Name": "測試董事", "Person_Position_Name": "董事"}]

        with patch.object(api_index, "_moea_rows", side_effect=fake_filter), \
             patch.object(api_index, "_supabase_evidence", return_value=([], False)), patch.object(api_index, "_supabase_company", return_value=None):
            data = api_index.build_company("87654321")

        self.assertEqual(data["company_name"], "隔離測試公司")
        self.assertEqual(calls, {"company": 1, "director": 1})
        self.assertEqual(len(data["people"]), 1)


if __name__ == "__main__":
    unittest.main()
