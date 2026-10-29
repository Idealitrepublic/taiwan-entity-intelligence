import json
import unittest

from scripts.ingest_official_lobby_observations_dev import build


class LobbyObservationTests(unittest.TestCase):
    def build(self, text):
        return build([text], source_url="https://ws.moi.gov.tw/Download.ashx?source=official",
                     source_title="115年度總表", snapshot_hash="a" * 64, retrieved_at="2026-10-29T00:00:00+08:00")[0]

    def test_source_row_has_exact_locator_without_organization_person_merge(self):
        bundle = self.build("遊說者申請登記事項\n1 115 年 第2季 財團法人測試基金會 部長 測試人 113年11月20日台內政風字第1130001號 終止遊說")
        self.assertEqual(bundle["entities"][0]["entity_type"], "LobbyingRecord")
        self.assertEqual(bundle["relationships"], [])
        locator = bundle["evidence"][0]["source_locator"]
        self.assertEqual(locator["table_row"], 1)
        self.assertEqual(locator["approval_date"], "2024-11-20")
        self.assertTrue(locator["termination_mentioned_in_source"])

    def test_natural_person_list_is_not_projected_as_people(self):
        bundle = self.build("遊說者申請登記事項\n1 115年第2季 甲某、乙某、丙某 部長 測試人 113年11月20日 登記")
        self.assertNotIn("甲某", json.dumps(bundle, ensure_ascii=False))
        self.assertEqual(bundle["identifiers"], [])

    def test_bad_row_sequence_and_incomplete_fields_stop(self):
        for text in ("遊說者申請登記事項\n2 115年第2季 缺少欄位", "遊說者申請登記事項\n1 115年第2季 缺少欄位"):
            with self.assertRaises(ValueError):
                self.build(text)


if __name__ == "__main__":
    unittest.main()
