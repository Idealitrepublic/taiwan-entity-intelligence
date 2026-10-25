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
            if key.startswith(("catalog_", "penghu_1669")) or key in ("keelung_ods", "yilan_20260930", "yunlin_20260713", "hsinchu_city_20261025", "hsinchu_county_20261005", "miaoli_society_20261025", "changhua_society_20261025", "kinmen_society_20261025", "tainan_social_foundations_json"):
                continue
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

    def test_catalog_manifest_is_curated_and_source_scoped(self):
        catalog = {key: source for key, source in SOURCES.items() if key.startswith("catalog_")}
        self.assertGreaterEqual(len(catalog), 60)
        with tempfile.TemporaryDirectory() as directory:
            for key, source in catalog.items():
                with self.subTest(key=key):
                    import csv
                    path = Path(directory) / f"{key}.csv"
                    name = source["name_column"]
                    columns = list(source["columns"]) + ["私人聯絡人"]
                    with path.open("w", encoding=source["encoding"], newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=columns)
                        writer.writeheader()
                        writer.writerow({name: "同名團體", "私人聯絡人": "甲某"})
                        writer.writerow({name: "同名團體", "私人聯絡人": "乙某"})
                    bundles = list(official_roster_bundles(path, key, retrieved_at=NOW,
                                                           publication_status="published"))
                    entities = [item for bundle in bundles for item in bundle["entities"]]
                    evidence = [item for bundle in bundles for item in bundle["evidence"]]
                    self.assertEqual(len(entities), 2)
                    self.assertNotEqual(entities[0]["id"], entities[1]["id"])
                    self.assertEqual(evidence[0]["source_locator"]["dataset_id"], source["dataset"])
                    self.assertNotIn("甲某", str(bundles))

    def test_ods_conversion_retains_original_hash_and_sheet_location(self):
        from scripts.convert_official_civil_ods import convert, TABLE, TEXT
        import hashlib
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.ods"
            output = Path(directory) / "converted.csv"
            xml = (f'<document xmlns:table="{TABLE}" xmlns:text="{TEXT}">'
                   '<table:table table:name="團體">'
                   '<table:table-row><table:table-cell><text:p>團體名稱</text:p></table:table-cell></table:table-row>'
                   '<table:table-row><table:table-cell><text:p>甲協會</text:p></table:table-cell></table:table-row>'
                   '</table:table></document>')
            with zipfile.ZipFile(source, "w") as package:
                package.writestr("content.xml", xml)
            self.assertEqual(convert(source, output), 1)
            bundle = next(official_roster_bundles(output, "keelung_ods", retrieved_at=NOW))
            locator = bundle["evidence"][0]["source_locator"]
            self.assertEqual(locator["ods_sheet"], "團體")
            self.assertEqual(locator["ods_row"], "2")
            self.assertEqual(locator["ods_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())

    def test_yilan_official_roster_keeps_category_and_not_contact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "yilan.csv"
            path.write_text("序號,人民團體名冊,團體類別,聯絡人\n"
                            "1,宜蘭縣測試協會,社會團體,私人姓名\n", encoding="utf-8")
            bundle = next(official_roster_bundles(path, "yilan_20260930", retrieved_at=NOW))
            locator = bundle["evidence"][0]["source_locator"]
            self.assertEqual(locator["團體類別"], "社會團體")
            self.assertNotIn("私人姓名", str(bundle))

    def test_yunlin_xlsx_projection_keeps_source_location_and_excludes_contacts(self):
        from scripts.convert_yunlin_civil_xlsx import convert, NS
        import hashlib
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.xlsx"
            output = Path(directory) / "projected.csv"
            workbook = (f'<workbook xmlns="{NS[1:-1]}"><sheets>'
                        '<sheet name="人民團體" sheetId="1"/></sheets></workbook>')
            rows = [
                (1, ("編號", "團體類別", "團體名稱", "會所地址", "理事長", "協會電話")),
                (2, ("1", "社會服務團體", "測試協會", "私人地址", "私人姓名", "私人電話")),
                (3, ("1", "體育團體", "另一協會", "私人地址", "私人姓名", "私人電話")),
            ]
            sheet_rows = []
            for number, values in rows:
                cells = "".join(f'<c r="{chr(65 + i)}{number}" t="inlineStr"><is><t>{value}</t></is></c>'
                                for i, value in enumerate(values))
                sheet_rows.append(f'<row r="{number}">{cells}</row>')
            sheet = f'<worksheet xmlns="{NS[1:-1]}"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
            with zipfile.ZipFile(source, "w") as package:
                package.writestr("xl/workbook.xml", workbook)
                package.writestr("xl/worksheets/sheet1.xml", sheet)
            self.assertEqual(convert(source, output), 2)
            bundles = list(official_roster_bundles(output, "yunlin_20260713", retrieved_at=NOW))
            entities = [entity for bundle in bundles for entity in bundle["entities"]]
            evidence = [item for bundle in bundles for item in bundle["evidence"]]
            self.assertEqual(len(entities), 2)
            self.assertNotEqual(entities[0]["id"], entities[1]["id"])
            self.assertEqual(evidence[0]["source_locator"]["xlsx_row"], "2")
            self.assertEqual(evidence[0]["source_locator"]["xlsx_sha256"],
                             hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertNotIn("私人", str(bundles))

    def test_hsinchu_html_categories_require_complete_sequential_pages(self):
        from scripts.convert_hsinchu_civil_json import convert, OFFICIAL_PAGE
        import json
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            output = Path(directory) / "projected.csv"
            categories = [{"category": f"分類{i}", "url": OFFICIAL_PAGE +
                           f"&mcustomize=formdata_list1.jsp&mclassno={i:012d}",
                           "date": "115-10-16", "expected": 1,
                           "rows": [{"seq": 1, "name": f"測試協會{i}"}]}
                          for i in range(12)]
            source.write_text(json.dumps({"source_page": OFFICIAL_PAGE,
                                          "categories": categories}, ensure_ascii=False))
            self.assertEqual(convert(source, output), 12)
            bundles = list(official_roster_bundles(output, "hsinchu_city_20261025",
                                                   retrieved_at=NOW))
            evidence = [item for bundle in bundles for item in bundle["evidence"]]
            self.assertEqual(evidence[0]["source_locator"]["官方序號"], "1")
            self.assertIn("json_sha256", evidence[0]["source_locator"])
            categories[0]["expected"] = 2
            source.write_text(json.dumps({"source_page": OFFICIAL_PAGE,
                                          "categories": categories}, ensure_ascii=False))
            with self.assertRaisesRegex(ValueError, "Incomplete official category"):
                convert(source, output)

    def test_miaoli_ods_keeps_filing_date_and_excludes_officer_contact(self):
        from scripts.convert_miaoli_civil_ods import convert
        from scripts.convert_official_civil_ods import TABLE, TEXT
        import hashlib
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "official.ods"
            output = Path(directory) / "projected.csv"
            def row(*values):
                cells = "".join(f'<table:table-cell><text:p>{value}</text:p></table:table-cell>'
                                for value in values)
                return f'<table:table-row>{cells}</table:table-row>'
            xml = (f'<document xmlns:table="{TABLE}" xmlns:text="{TEXT}">'
                   '<table:table table:name="Worksheet">' + row("名冊資料") +
                   row("團體類別", "團體名稱", "立案日期", "理事長", "會址") +
                   row("社會服務", "測試協會", "115/01/01", "私人姓名", "私人地址") +
                   '</table:table></document>')
            with zipfile.ZipFile(source, "w") as package:
                package.writestr("content.xml", xml)
            self.assertEqual(convert(source, output), 1)
            bundle = next(official_roster_bundles(output, "miaoli_society_20261025", retrieved_at=NOW))
            locator = bundle["evidence"][0]["source_locator"]
            self.assertEqual(locator["立案日期"], "115/01/01")
            self.assertEqual(locator["ods_row"], "3")
            self.assertEqual(locator["ods_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertNotIn("私人", str(bundle))

    def test_changhua_ods_preserves_official_id_without_officer_address(self):
        from scripts.convert_changhua_civil_ods import convert
        from scripts.convert_official_civil_ods import TABLE, TEXT
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "official.ods"
            output = Path(directory) / "projected.csv"
            def row(*values):
                cells = "".join(f'<table:table-cell><text:p>{value}</text:p></table:table-cell>'
                                for value in values)
                return f'<table:table-row>{cells}</table:table-row>'
            xml = (f'<document xmlns:table="{TABLE}" xmlns:text="{TEXT}">'
                   '<table:table table:name="社團立案名冊">' +
                   row("C001", "自由職業", "測試教育會", "私人姓名", "私人地址") +
                   '</table:table></document>')
            with zipfile.ZipFile(source, "w") as package:
                package.writestr("content.xml", xml)
            self.assertEqual(convert(source, output), 1)
            bundle = next(official_roster_bundles(output, "changhua_society_20261025",
                                                  retrieved_at=NOW))
            locator = bundle["evidence"][0]["source_locator"]
            self.assertEqual(locator["官方編號"], "C001")
            self.assertEqual(locator["ods_row"], "1")
            self.assertNotIn("私人", str(bundle))

    def test_kinmen_xlsx_preserves_dates_without_contacts(self):
        from scripts.convert_kinmen_civil_xlsx import convert, NS
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.xlsx"
            output = Path(directory) / "projected.csv"
            workbook = (f'<workbook xmlns="{NS[1:-1]}"><sheets>'
                        '<sheet name="金門縣社會團體" sheetId="1"/></sheets></workbook>')
            rows = [
                (1, ("資源彙整機關", "編號", "社會團體名稱", "會址", "聯絡電話", "成立日期", "最後更新時間")),
                (2, ("金門縣政府社會處", "B0001", "測試社團", "私人地址", "私人電話", "115/01/01", "20261025")),
            ]
            sheet_rows = []
            for number, values in rows:
                cells = "".join(f'<c r="{chr(65 + i)}{number}" t="inlineStr"><is><t>{value}</t></is></c>'
                                for i, value in enumerate(values))
                sheet_rows.append(f'<row r="{number}">{cells}</row>')
            sheet = f'<worksheet xmlns="{NS[1:-1]}"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
            with zipfile.ZipFile(source, "w") as package:
                package.writestr("xl/workbook.xml", workbook)
                package.writestr("xl/worksheets/sheet1.xml", sheet)
            self.assertEqual(convert(source, output), 1)
            bundle = next(official_roster_bundles(output, "kinmen_society_20261025",
                                                  retrieved_at=NOW))
            locator = bundle["evidence"][0]["source_locator"]
            self.assertEqual(locator["官方編號"], "B0001")
            self.assertEqual(locator["成立日期"], "115/01/01")
            self.assertNotIn("私人", str(bundle))

    def test_penghu_category_projection_skips_contact_continuations(self):
        from scripts.convert_penghu_civil_csv import convert
        from unittest.mock import patch
        key = "penghu_166901_20261025"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "official.csv"
            output = Path(directory) / "projected.csv"
            source.write_text("編號,團體名稱,理事長及主要人員,會社址,人數,電話\n"
                              "1,測試協會,私人姓名,私人地址,20,私人電話\n"
                              ",,,,,私人電話\n", encoding="utf-8")
            with patch.dict(SOURCES[key], {"expected_rows": 1}):
                self.assertEqual(convert(source, output, key), 1)
            bundle = next(official_roster_bundles(output, key, retrieved_at=NOW))
            locator = bundle["evidence"][0]["source_locator"]
            self.assertEqual(locator["csv_row"], "2")
            self.assertEqual(locator["官方編號"], "1")
            self.assertNotIn("私人", str(bundle))

    def test_hsinchu_county_xlsx_keeps_category_and_redacts_personal_fields(self):
        from scripts.convert_hsinchu_county_civil_xlsx import convert, NS
        from unittest.mock import patch
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.xlsx"
            output = Path(directory) / "projected.csv"
            workbook = (f'<workbook xmlns="{NS[1:-1]}"><sheets>'
                        '<sheet name="完成" sheetId="1"/></sheets></workbook>')
            rows = [
                (1, ("一、新竹縣人民團體名冊（工商職業團體）",)),
                (2, ("編號", "團體名稱", "負責人姓名", "會址", "電話", "成立年月日")),
                (3, ("1", "測試團體", "私人姓名", "私人地址", "私人電話", "115.10.05")),
            ]
            sheet_rows = []
            for number, values in rows:
                cells = "".join(f'<c r="{chr(65 + i)}{number}" t="inlineStr"><is><t>{value}</t></is></c>'
                                for i, value in enumerate(values))
                sheet_rows.append(f'<row r="{number}">{cells}</row>')
            sheet = f'<worksheet xmlns="{NS[1:-1]}"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
            with zipfile.ZipFile(source, "w") as package:
                package.writestr("xl/workbook.xml", workbook)
                package.writestr("xl/worksheets/sheet1.xml", sheet)
            with patch.dict(SOURCES["hsinchu_county_20261005"],
                            {"expected_rows": 1, "category_counts": {"工商職業團體": 1}}):
                self.assertEqual(convert(source, output), 1)
            bundle = next(official_roster_bundles(output, "hsinchu_county_20261005",
                                                  retrieved_at=NOW))
            locator = bundle["evidence"][0]["source_locator"]
            self.assertEqual(locator["團體類別"], "工商職業團體")
            self.assertEqual(locator["xlsx_row"], "3")
            self.assertNotIn("私人", str(bundle))

    def test_tainan_json_conversion_retains_original_hash_and_rejects_failed_response(self):
        from scripts.convert_tainan_foundation_json import convert
        import hashlib
        import json
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            output = Path(directory) / "converted.csv"
            source.write_text(json.dumps({"success": True, "data": [{"基金會名稱": "測試基金會",
                                                    "董事長": "私人姓名"}]}, ensure_ascii=False))
            self.assertEqual(convert(source, output), 1)
            bundle = next(official_roster_bundles(output, "tainan_social_foundations_json",
                                                  retrieved_at=NOW))
            locator = bundle["evidence"][0]["source_locator"]
            self.assertEqual(locator["json_row"], "1")
            self.assertEqual(locator["json_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertNotIn("私人姓名", str(bundle))
            source.write_text('{"success": false, "data": []}')
            with self.assertRaisesRegex(ValueError, "Unexpected official JSON"):
                convert(source, output)

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
