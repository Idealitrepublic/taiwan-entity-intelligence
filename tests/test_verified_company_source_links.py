"""Exact company website and source-linking regressions."""
from io import BytesIO
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src import cloud_company
from src.company_website_crosswalk import reviewed_websites, verified_website
from scripts.build_official_company_websites import safe_website, probed_https_website, make_snapshot, SOURCES
from src.sources import judicial_index, procurement


class VerifiedCompanySourceLinksTests(unittest.TestCase):
    def test_crosswalk_has_unique_official_proofs_and_requires_name_and_id(self):
        sites = reviewed_websites()
        self.assertGreaterEqual(len(sites), 500)
        self.assertEqual(sites["04231910"]["domain"], "cathaybk.com.tw")
        self.assertIn("cathaybk.com.tw", sites["04231910"]["identity_source_url"])
        self.assertIsNone(verified_website("04231910", "國泰世華證券股份有限公司"))
        self.assertIsNone(verified_website("00000000", "國泰世華商業銀行股份有限公司"))
        self.assertEqual(sites["04541302"]["source_class"], "official_issuer_disclosure")
        self.assertEqual(sites["04541302"]["domain"], "honhai.com")
        self.assertIsNone(verified_website("04541302", "同名企業股份有限公司"))

    def test_official_feed_requires_safe_https_and_exact_identity(self):
        for value in ("http://example.com", "https://user@example.com", "https://example.com:bad",
                      "https://example.com/path with space", "https://localhost", "https://127.0.0.1",
                      "https://company.internal"):
            with self.subTest(value=value):
                self.assertIsNone(safe_website(value))
        self.assertEqual(safe_website("https://example.com/path"), "https://example.com/path")
        feeds = {source[1]: [{} for _ in range(100)] for source in SOURCES}
        feeds[SOURCES[0][1]][0] = {"營利事業統一編號": "12345678", "公司名稱": "同名公司股份有限公司",
                                  "網址": "https://example.com", "公司代號": "1234"}
        snapshot = make_snapshot(feeds, [], "2026-10-22T00:00:00+00:00")
        self.assertEqual(len(snapshot["records"]), 1)
        self.assertEqual(snapshot["records"][0]["source_record_id"], "1234")
        with self.assertRaises(ValueError):
            make_snapshot(feeds, [{"uniform_number": "12345678", "company_name": "其他公司股份有限公司",
                                   "website_url": "https://example.com"}], "2026-10-22T00:00:00+00:00")

    def test_unqualified_issuer_url_requires_reachable_same_host_https(self):
        with patch("scripts.build_official_company_websites.subprocess.run", return_value=SimpleNamespace(
                returncode=0, stdout="200 https://www.example.com/")):
            self.assertEqual(probed_https_website("http://www.example.com/"), "https://www.example.com/")
        with patch("scripts.build_official_company_websites.subprocess.run", return_value=SimpleNamespace(
                returncode=0, stdout="200 https://other.example.com/")):
            self.assertIsNone(probed_https_website("www.example.com"))
        feeds = {source[1]: [{} for _ in range(100)] for source in SOURCES}
        feeds[SOURCES[0][1]][0] = {"營利事業統一編號": "12345678", "公司名稱": "同名公司股份有限公司",
                                  "網址": "www.example.com", "公司代號": "1234"}
        result = make_snapshot(feeds, [], "2026-10-22T00:00:00+00:00",
                               focus_ids={"12345678"}, probe=lambda _: "https://www.example.com")
        self.assertEqual(result["records"][0]["reported_website_url"], "www.example.com")

    def test_cathay_official_site_is_checked_with_provenance(self):
        base = {"status": "ok", "uniform_number": "04231910",
                "company_name": "國泰世華商業銀行股份有限公司", "website_url": None,
                "website_host": None, "evidence": [], "evidence_status": {},
                "graph": {"nodes": [], "edges": []}}
        judicial = {"records": [], "status": "partial", "matched": 0,
                    "coverage_note": "partial", "interpretation": "not a conclusion",
                    "match_rule": "full_name_mention"}
        with patch.object(cloud_company, "_base_company", return_value=base), \
             patch.object(cloud_company, "indexed_records", return_value=[]), \
             patch.object(cloud_company, "records_for_company", return_value=judicial), \
             patch.object(cloud_company, "check_domain", return_value={
                 "status": "ok", "domain": "cathaybk.com.tw",
                 "anti_fraud": {"matched": 0, "records": []}}) as check:
            result = cloud_company.build_company("04231910")
        check.assert_called_once_with("cathaybk.com.tw")
        self.assertEqual(result["evidence_status"]["165"]["status"], "ok")
        self.assertEqual(result["website_crosscheck"]["website_verified_on"], "2026-10-22")
        self.assertEqual(result["website_crosscheck"]["website_source_url"],
                         reviewed_websites()["04231910"]["identity_source_url"])

    def test_registry_domain_conflict_does_not_auto_check(self):
        base = {"status": "ok", "uniform_number": "04231910",
                "company_name": "國泰世華商業銀行股份有限公司",
                "website_url": "https://unrelated.example/", "website_host": "unrelated.example",
                "evidence": [], "evidence_status": {}, "graph": {"nodes": [], "edges": []}}
        judicial = {"records": [], "status": "partial", "matched": 0,
                    "coverage_note": "partial", "interpretation": "not a conclusion",
                    "match_rule": "full_name_mention"}
        with patch.object(cloud_company, "_base_company", return_value=base), \
             patch.object(cloud_company, "indexed_records", return_value=[]), \
             patch.object(cloud_company, "records_for_company", return_value=judicial), \
             patch.object(cloud_company, "check_domain") as check:
            result = cloud_company.build_company("04231910")
        check.assert_not_called()
        self.assertEqual(result["website_verification"], "conflict_requires_review")
        self.assertEqual(result["evidence_status"]["165"]["status"], "not_checked")

    def test_labor_name_candidate_with_conflicting_raw_id_is_excluded(self):
        candidate = {"id": "mol:wrong", "company_name": "國泰世華商業銀行股份有限公司",
                     "uniform_number": None,
                     "raw": {"統一編號": "23060248", "事業單位名稱或負責人": "國泰世華商業銀行股份有限公司"}}
        safe = {"id": "mol:name-only", "company_name": candidate["company_name"],
                "uniform_number": None, "raw": {"事業單位名稱或負責人": candidate["company_name"]}}
        responses = [BytesIO(b"[]"), BytesIO(json.dumps([candidate, safe], ensure_ascii=False).encode()),
                     BytesIO(b"[]")]
        with patch.object(cloud_company, "SUPABASE", "https://development.invalid"), \
             patch.object(cloud_company, "SUPABASE_KEY", "public-test-key"), \
             patch.object(cloud_company.urllib.request, "urlopen", side_effect=responses):
            result = cloud_company.indexed_records("04231910", candidate["company_name"])
        self.assertEqual([row["id"] for row in result], ["mol:name-only"])

    def test_judicial_short_name_does_not_match_longer_company(self):
        row = {"jid": "TEST,115,訴,1,20260101,1", "title": "裁判",
               "companies": ["國泰世華商業銀行股份有限公司"],
               "source_url": "https://judgment.judicial.gov.tw/FJUD/printData.aspx?id=one"}
        with patch.object(judicial_index, "load_index", return_value={
                "records": [row], "source": "official JDoc", "generated_at": "2026-10-22"}):
            self.assertEqual(judicial_index.records_for_company("國泰世華商業銀行股份有限公司")["matched"], 1)
            self.assertEqual(judicial_index.records_for_company("世華商業銀行股份有限公司")["matched"], 0)

    def test_procurement_mixed_roles_for_same_name_are_unresolved(self):
        row = {"brief": {"companies": {"id_key": {"04231910": ["投標廠商:投標廠商1:廠商代碼"]},
            "name_key": {"國泰世華商業銀行股份有限公司": [
                "投標廠商:投標廠商1:廠商名稱", "決標品項:第1品項:得標廠商1:得標廠商",
                "投標廠商:未得標廠商2:廠商名稱"]}}}}
        self.assertEqual(procurement.award_role(row, "04231910"), "unresolved")
        projection = procurement._normalize(row, "04231910")
        self.assertEqual(projection["awardee_names"], [])
        self.assertEqual(projection["publication_status"], "source_candidate")

    def test_procurement_same_name_other_bidder_winner_is_unresolved(self):
        row = {"brief": {"companies": {"id_key": {
            "04231910": ["投標廠商:未得標廠商2:廠商代碼"],
            "23060248": ["決標品項:第1品項:得標廠商1:廠商代碼"],
        }, "name_key": {"同名公司股份有限公司": [
            "投標廠商:未得標廠商2:廠商名稱",
            "決標品項:第1品項:得標廠商1:廠商名稱",
        ]}}}}
        self.assertEqual(procurement.award_role(row, "04231910"), "unresolved")
        self.assertEqual(procurement.award_role(row, "23060248"), "unresolved")


if __name__ == "__main__":
    unittest.main()
