import json
import sqlite3
import unittest

from scripts.build_official_reference_index import AGENCY_URL, BILL_URL, agency_rows, bill_rows, build


class OfficialReferenceIndexTests(unittest.TestCase):
    def test_agency_identifier_is_unique_and_contact_data_is_not_projected(self):
        raw = "OrgName,OID,OrgCode,TEL,Address\n測試機關,2.16.886.1,123,not-retained,not-retained\n".encode()
        rows = agency_rows(raw)
        self.assertEqual(rows, [(2, "2.16.886.1", "測試機關", "123")])
        with self.assertRaises(ValueError):
            agency_rows(raw + raw.splitlines()[1] + b"\n")

    def test_bill_stages_are_preserved_without_guessing_the_latest_status(self):
        raw = json.dumps({"dataList": [{"term": 11, "billNo": "official-1", "billName": "同一議案", "billStatus": status}
                                       for status in ["一讀", "交付審查"]]}).encode()
        rows = bill_rows(raw)
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0][-1], rows[1][-1])
        db = sqlite3.connect(":memory:")
        sources = [("bills", raw, BILL_URL, "2026-10-29T00:00:00+08:00")]
        first, repeated = build(db, sources), build(db, sources)
        self.assertEqual(first, repeated)
        self.assertEqual(first["distinct_official_bill_ids"], 1)
        self.assertEqual(first["canonical_entities_published"], 0)

    def test_bad_term_empty_data_and_unreviewed_source_fail(self):
        for payload in ({"dataList": []}, {"dataList": [{"term": 10, "billNo": "1", "billName": "不在範圍"}]}):
            with self.assertRaises(ValueError):
                bill_rows(json.dumps(payload).encode())
        with self.assertRaises(ValueError):
            build(sqlite3.connect(":memory:"), [("agencies", b"x", AGENCY_URL + "?wrong", "2026-10-29T00:00:00+08:00")])


if __name__ == "__main__":
    unittest.main()
