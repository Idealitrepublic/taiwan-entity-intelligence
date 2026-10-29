import csv
import io
import unittest

from scripts.ingest_labor_penalties_dev import indexed_rows, sql_snapshot
from scripts.refresh_labor_snapshots_dev import new_rows


class LaborSnapshotRefreshTests(unittest.TestCase):
    def setUp(self):
        self.row = {"主管機關": "測試市", "處分日期": "20260101", "處分字號": "來源字號1",
                    "事業單位名稱或負責人": "名稱不足以核身", "違法法規法條": "勞動基準法第24條"}

    def payload(self, rows):
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(self.row))
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue().encode()

    def test_incremental_refresh_deduplicates_and_preserves_existing_rows(self):
        payload = self.payload([self.row, self.row])
        additions, report = new_rows("109896", payload, set())
        self.assertEqual(len(additions), 1)
        self.assertEqual(report["duplicate_source_rows"], 1)
        known = {indexed_rows("109896", [self.row])[0][0]}
        repeated, report = new_rows("109896", payload, known)
        self.assertEqual(repeated, [])
        self.assertEqual(report["new_raw_versions"], 0)

    def test_changed_source_is_new_raw_version_not_silent_overwrite(self):
        known = {indexed_rows("109896", [self.row])[0][0]}
        additions, _ = new_rows("109896", self.payload([{**self.row, "處分字號": "來源更正"}]), known)
        self.assertEqual(len(additions), 1)
        sql = sql_snapshot("109896", "https://apiservice.mol.gov.tw/source", b"bytes", additions,
                           downloaded_at="2026-10-28T00:00:00+00:00")
        self.assertNotIn("DELETE", sql)
        self.assertNotIn("relationships", sql)
        self.assertIn("2026-10-28T00:00:00+00:00", sql)

    def test_missing_schema_or_empty_snapshot_stops(self):
        for payload in (b"wrong\nvalue\n", self.payload([])):
            with self.assertRaises(ValueError):
                new_rows("109896", payload, set())


if __name__ == "__main__":
    unittest.main()
