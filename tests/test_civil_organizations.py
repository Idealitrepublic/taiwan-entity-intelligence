import tempfile
import unittest
from pathlib import Path

from src.civil_organizations import roster_bundles
from src.civil_roster_sources import SOURCES, official_roster_bundles
from scripts.ingest_civil_organizations_dev import ensure_same_snapshot
from scripts.ingest_nonprofit_tax_dev import profile as tax_profile


HEADER = "SeqNo,Name,Date_of_Establishment,address,Chairman,session\n"
SUBHEADER = "序號,協會名稱,成立日期,地址,理事長,屆次\n"
NOW = "2026-10-24T00:00:00+00:00"


class CivilOrganizationIngestionTests(unittest.TestCase):
    def roster(self, body):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "roster.csv"
        path.write_text(HEADER + SUBHEADER + body, encoding="utf-8-sig")
        return path

    def test_historical_rows_are_source_scoped_and_have_evidence(self):
        path = self.roster("1,同名協會,131010,私有地址,甲某,1\n"
                           "2,同名協會,191010,另一地址,乙某,2\n")
        bundles = list(roster_bundles(path, retrieved_at=NOW, batch_size=1,
                                      publication_status="published"))
        self.assertEqual(len(bundles), 2)
        left, right = bundles
        self.assertNotEqual(left["entities"][0]["id"], right["entities"][0]["id"])
        for bundle in bundles:
            entity, evidence = bundle["entities"][0], bundle["evidence"][0]
            self.assertEqual(entity["entity_type"], "CivilOrganization")
            self.assertEqual(entity["identity_status"], "SOURCE_SCOPED")
            self.assertEqual(bundle["entity_evidence"][0]["entity_id"], entity["id"])
            self.assertEqual(bundle["entity_evidence"][0]["evidence_id"], evidence["id"])
            self.assertIn("historical_roster", evidence["source_locator"]["scope"])
            self.assertNotIn("私有地址", str(bundle))
            self.assertNotIn("乙某", str(bundle))
        again = list(roster_bundles(path, retrieved_at=NOW, batch_size=2))
        self.assertEqual(again[0]["entities"][0]["id"], left["entities"][0]["id"])

    def test_duplicate_sequence_is_rejected_not_name_merged(self):
        path = self.roster("1,協會甲,131010,,,\n1,協會乙,131010,,,\n")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            list(roster_bundles(path, retrieved_at=NOW))

    def test_bad_columns_and_bad_rows_fail_closed(self):
        path = self.roster("not-an-id,協會甲,131010,,,\n")
        with self.assertRaisesRegex(ValueError, "Invalid MOI roster row"):
            list(roster_bundles(path, retrieved_at=NOW))
        path.write_text("Name\n協會甲\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unexpected MOI"):
            list(roster_bundles(path, retrieved_at=NOW))

    def test_search_and_profile_disclose_historical_scope(self):
        html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text()
        self.assertIn('<option value="CivilOrganization">民間團體', html)
        self.assertIn("CivilOrganization:'民間團體 / Civil organization'", html)
        self.assertIn('Official roster observation; current registration and cross-source identity are unverified.', html)
        self.assertIn('Current status and cross-source identity are unverified.', html)
        self.assertIn('dissolution_date_raw', html)

    def test_additional_official_rosters_keep_source_identity_and_redact_contact(self):
        for key, source in SOURCES.items():
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "official.csv"
                if key == "moi_foundations":
                    path.write_text("序號,類型,團體名稱,成立日期,負責人,地址\n"
                                    "1,財團法人,測試基金會,1130101,私人姓名,私人地址\n", encoding="utf-8")
                elif key == "moi_civic_foundations":
                    path.write_text("編號,全國性民政財團法人名稱,許可設立日期,許可設立文號,法人代表,法人代表性別,主事務所地址,聯絡電話\n"
                                    "1,測試基金會,1130101,官方文號,私人姓名,女,私人地址,私人電話\n", encoding="utf-8")
                elif key == "taipei":
                    path.write_text("機關代碼,名稱,地址,電話,成立日期\n"
                                    "A,測試協會,私人地址,私人電話,1130101\n", encoding="utf-8")
                elif key == "tainan":
                    path.write_text("連結網址,團體類別,團體名稱,縣市別代碼,地址-行政區域代碼,會所住址,電話,理事長,成立年月,公告解散年月,立案字號\n"
                                    "https://example.gov.tw,社會團體,測試協會,67,6701,私人地址,私人電話,私人姓名,11301,,官方文號\n", encoding="utf-8")
                elif key == "pingtung":
                    path.write_text("name,address,phone\n測試協會,私人地址,私人電話\n", encoding="utf-8")
                elif key == "mol_foundations":
                    path.write_text("財團法人名稱,許可設立日期及文號,督導單位,負責人姓名\n"
                                    "測試基金會,官方文號,勞動部,私人姓名\n", encoding="utf-8")
                elif key == "moe_foundations":
                    path.write_text("基金會名稱,設立許可文號,基金會狀態,董事長姓名\n"
                                    "測試基金會,官方文號,來源狀態,私人姓名\n", encoding="cp950")
                elif key == "newtaipei_community":
                    path.write_text("seqno,title,county,person_in_charge\n"
                                    "1,測試協會,新北市,私人姓名\n", encoding="utf-8")
                elif key == "taichung_academic":
                    path.write_text("\ufeff\ufeff單位名稱,單位類型,最後更新日期,連絡電話\n"
                                    "測試協會,學術文化,2026-01-01,私人電話\n", encoding="utf-8")
                elif key == "kaohsiung_charity":
                    path.write_text("id,org_name,dataOrg,informtel\n"
                                    "1,測試協會,高雄市政府,私人電話\n", encoding="utf-8")
                else:
                    path.write_text("序號,工會名稱,地址,電話,傳真\n"
                                    "1,測試工會,私人地址,私人電話,私人傳真\n", encoding="utf-8")
                bundle = next(official_roster_bundles(path, key, retrieved_at=NOW,
                                                       publication_status="published"))
                self.assertEqual(bundle["entities"][0]["source"], source["name"])
                self.assertEqual(bundle["entities"][0]["identity_status"], "SOURCE_SCOPED")
                self.assertEqual(bundle["evidence"][0]["source_locator"]["dataset_id"], source["dataset"])
                self.assertNotIn("私人", str(bundle))
                self.assertEqual(len(bundle["entity_evidence"]), 1)
                if key == "moe_foundations":
                    self.assertEqual(bundle["evidence"][0]["source_locator"]["foundation_status_raw"], "來源狀態")

    def test_tax_source_profiles_all_rows_without_entity_merges(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tax.csv"
            path.write_text("統一編號,單位名稱,機關所在縣市,最近異動日期,最近異動原因,原因說明文字\n"
                            "12345678,甲單位,臺北市,1140101,異動,內容\n"
                            "invalid,乙單位,臺中市,1140102,異動,內容\n", encoding="utf-8")
            self.assertEqual(tax_profile(path)["invalid_identifiers"], 1)
            self.assertEqual(tax_profile(path)["source_rows"], 2)
            path.write_text("統一編號,單位名稱,機關所在縣市,最近異動日期,最近異動原因,原因說明文字\n"
                            "12345678,甲單位,,,,\n12345678,乙單位,,,,\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate tax identifier"):
                tax_profile(path)

    def test_local_same_name_rows_stay_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "taipei.csv"
            path.write_text("機關代碼,名稱,地址,電話,成立日期\n"
                            "A,同名協會,私人地址,私人電話,1130101\n"
                            "A,同名協會,另一地址,另一電話,1140101\n", encoding="utf-8")
            bundle = next(official_roster_bundles(path, "taipei", retrieved_at=NOW,
                                                   publication_status="published"))
            left, right = bundle["entities"]
            self.assertNotEqual(left["id"], right["id"])
            self.assertEqual([e["source_locator"]["csv_row"] for e in bundle["evidence"]], [2, 3])
            self.assertNotIn("私人", str(bundle))

    def test_empty_trailing_records_are_not_published(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "newtaipei.csv"
            path.write_text("seqno,title,county,person_in_charge\n"
                            "1,測試協會,新北市,私人姓名\n,, ,\n", encoding="utf-8")
            bundles = list(official_roster_bundles(path, "newtaipei_community",
                                                   retrieved_at=NOW, publication_status="published"))
            self.assertEqual(sum(len(bundle["entities"]) for bundle in bundles), 1)
            self.assertEqual(bundles[0]["evidence"][0]["source_locator"]["csv_row"], 2)

    def test_changed_snapshot_requires_explicit_review(self):
        ensure_same_snapshot("hash-a", [])
        ensure_same_snapshot("hash-a", ["hash-a"])
        with self.assertRaisesRegex(ValueError, "different official snapshot"):
            ensure_same_snapshot("hash-b", ["hash-a"])


if __name__ == "__main__":
    unittest.main()
