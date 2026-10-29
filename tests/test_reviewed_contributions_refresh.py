import unittest

from scripts.publish_reviewed_contributions_dev import review_rows, reviewed_candidates

POLITICIAN = "11111111-1111-4111-8111-111111111111"
COMPANY = "22222222-2222-4222-8222-222222222222"
EVIDENCE = "33333333-3333-4333-8333-333333333333"


class ReviewedContributionRefreshTests(unittest.TestCase):
    def setUp(self):
        self.row = {"序號": "7", "擬參選人／政黨": "測試委員", "選舉名稱": "113年立法委員選舉",
                    "申報序號／年度": "首次申報", "交易日期": "1120801", "收支科目": "營利事業捐贈收入",
                    "捐贈者／支出對象": "測試有限公司", "身分證／統一編號": "12345678", "收入金額": "50000.00",
                    "金錢類": "金錢", "返還/繳庫": ""}
        self.term = {"politician_entity_id": POLITICIAN, "legislator_number": "11001",
                     "constituency": "臺北市第1選舉區", "primary_evidence_id": EVIDENCE}
        self.company = {"id": COMPANY, "name": "測試有限公司", "uniform_number": "12345678", "confidence": "EXACT"}

    def review(self, rows=None, companies=None):
        return review_rows(rows or [self.row], {"測試委員": self.term}, companies or [self.company],
                           {"crosswalks": []}, retrieved_at="2026-10-28T00:00:00+00:00", archive_hash="a" * 64)

    def test_exact_id_and_reviewed_election_context_keep_traceable_source(self):
        bundles, crosswalks, report = self.review()
        self.assertEqual(report["reviewed_publishable_rows"], 1)
        self.assertEqual(crosswalks[0]["review_basis"], "election_term_constituency")
        proof = bundles[0]["evidence"][0]
        self.assertEqual(proof["source_locator"]["csv_row"], 2)
        self.assertEqual(proof["source_locator"]["snapshot_sha256"], "a" * 64)
        self.assertEqual(bundles[0]["relationships"][0]["amount"], "50000.00")
        self.assertNotIn("地址", proof["source_locator"])

    def test_name_alone_never_publishes(self):
        self.row["擬參選人／政黨"] = "同名候選人"
        self.assertEqual(self.review()[2]["reviewed_publishable_rows"], 0)
        self.row["擬參選人／政黨"] = "測試委員"
        self.company["confidence"] = "LOW"
        self.assertEqual(self.review()[2]["reviewed_publishable_rows"], 0)

    def test_returned_or_noncash_contribution_is_not_ordinary_donation(self):
        for updates in ({"返還/繳庫": "已返還"}, {"返還/繳庫": "已繳庫"}, {"金錢類": "非金錢"}):
            row = {**self.row, **updates}
            self.assertEqual(self.review([row])[2]["reviewed_publishable_rows"], 0)

    def test_donor_registry_name_change_requires_separate_review(self):
        self.company["name"] = "名稱變更有限公司"
        self.assertEqual(self.review()[2]["reviewed_publishable_rows"], 0)

    def test_duplicate_source_serial_stops_entire_plan(self):
        with self.assertRaisesRegex(ValueError, "Duplicate official"):
            self.review([self.row, self.row])

    def test_election_must_include_all_eight_unique_districts(self):
        with self.assertRaises(ValueError):
            reviewed_candidates("113年1月19日 第 11 屆立法委員選舉當選人名單 臺北市第1選舉區 測試委員 女 60.01.01 測試黨 100", {})


if __name__ == "__main__":
    unittest.main()
