import unittest
import urllib.error
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
        person = next(node for node in data["graph"]["nodes"] if node["type"] == "person")
        self.assertEqual(person["properties"]["identity_status"], "source_scoped_observation")
        self.assertEqual(person["evidence"]["source_locator_type"],
                         "query_row_not_official_person_id")
        self.assertEqual(data["graph"]["edges"][0]["evidence"], person["evidence"])
        self.assertIn("Business_Accounting_NO+eq+87654321", person["evidence"]["source_url"])
        self.assertNotIn("source_record_id", person["evidence"])

    def test_empty_moea_response_is_not_found_not_invalid_json(self):
        response = unittest.mock.Mock()
        response.read.return_value = b""
        response.__enter__ = unittest.mock.Mock(return_value=response)
        response.__exit__ = unittest.mock.Mock(return_value=False)
        with patch("src.cloud_company.urllib.request.urlopen", return_value=response), \
             patch.object(api_index, "_published_registry_snapshot", return_value=None):
            data = api_index.build_company("88597586")
        self.assertEqual(data["status"], "not_found")

    def test_published_snapshot_requires_exact_official_identity_evidence(self):
        identity = {"id": "evidence-1", "source_name": "MOEA/GCI",
                    "source_record_id": "96979933", "source_url": "https://data.gcis.nat.gov.tw/example",
                    "retrieved_at": "2026-10-18T00:00:00+00:00",
                    "source_locator": {"uniform_number": "96979933",
                                       "company_name": "中華電信股份有限公司",
                                       "company_status": "核准設立"}}
        profile = {"entity_type": "Company", "identity_status": "EXACT",
                   "display_name": "中華電信股份有限公司",
                   "evidence": [{"fact_type": "IDENTITY", "evidence": identity}]}
        with patch("src.cloud_company.EntityRepository.entity", return_value=profile):
            snapshot = api_index._published_registry_snapshot("96979933")
        self.assertEqual(snapshot["company"]["Business_Accounting_NO"], "96979933")
        self.assertEqual(snapshot["evidence"]["retrieved_at"], "2026-10-18T00:00:00+00:00")
        for wrong in ({"source_record_id": "00000000"},
                      {"source_locator": {**identity["source_locator"], "uniform_number": "00000000"}},
                      {"source_name": "unverified source"}):
            invalid = {**profile, "evidence": [{"fact_type": "IDENTITY", "evidence": {**identity, **wrong}}]}
            with patch("src.cloud_company.EntityRepository.entity", return_value=invalid):
                self.assertIsNone(api_index._published_registry_snapshot("96979933"))

    def test_registry_outage_uses_dated_published_snapshot_without_people(self):
        snapshot = {"company": {"Business_Accounting_NO": "96979933",
                                "Company_Name": "中華電信股份有限公司",
                                "Company_Status_Desc": "核准設立"},
                    "evidence": {"id": "evidence-1", "source_name": "MOEA/GCI",
                                 "source_url": "https://data.gcis.nat.gov.tw/example",
                                 "source_record_id": "96979933",
                                 "source_locator": {"uniform_number": "96979933"},
                                 "retrieved_at": "2026-10-18T00:00:00+00:00"}}
        with patch.object(api_index, "_moea_rows", side_effect=TimeoutError), \
             patch.object(api_index, "_published_registry_snapshot", return_value=snapshot), \
             patch.object(api_index, "_supabase_evidence", return_value=([], False)), \
             patch.object(api_index, "_supabase_company", return_value=None):
            data = api_index.build_company("96979933")
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["data_mode"], "published_registry_snapshot_plus_supabase")
        self.assertEqual(data["evidence_status"]["公司登記"]["status"], "partial")
        self.assertEqual(data["people"], [])
        self.assertEqual(data["evidence"][0]["retrieved_at"], "2026-10-18T00:00:00+00:00")
        self.assertEqual(data["graph"]["nodes"][0]["evidence"]["data_status"], "published_snapshot_not_live")

    def test_registry_outage_without_exact_snapshot_stays_unavailable(self):
        with patch.object(api_index, "_moea_rows", side_effect=urllib.error.URLError("unavailable")), \
             patch.object(api_index, "_published_registry_snapshot", return_value=None):
            with self.assertRaises(urllib.error.URLError):
                api_index.build_company("00000000")


if __name__ == "__main__":
    unittest.main()
