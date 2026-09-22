import unittest
from datetime import datetime, timezone

from src.data_health import age_hours, metric, severity
from scripts.sync_public_sources import should_publish_judicial_index


class DataHealthTests(unittest.TestCase):
    def test_unknown_denominator_is_not_zero(self):
        item = metric("judiciary", observed=3, expected=None, scope="known cases")
        self.assertIsNone(item["coverage"])
        self.assertEqual(severity(item), "Unknown")

    def test_duplicate_and_provenance(self):
        rows = [
            {"id": "a", "source_url": "https://official.test/1", "retrieved_at": "2026-01-01T00:00:00Z", "provenance": "official"},
            {"id": "a", "source_url": "https://official.test/2", "retrieved_at": "2026-01-01T00:00:00Z"},
        ]
        item = metric("procurement", observed=2, expected=2, rows=rows, identity="id", scope="sample")
        self.assertEqual(item["duplicate_rate"], 0.5)
        self.assertEqual(item["provenance_rate"], 0.5)
        self.assertEqual(severity(item), "Medium")

    def test_error_overrides_full_sample_coverage(self):
        item = metric("labor_penalties", observed=3, expected=3, errors=1, scope="sample")
        self.assertEqual(severity(item), "High")

    def test_invalid_or_naive_freshness_is_unknown(self):
        now = datetime(2026, 9, 23, tzinfo=timezone.utc)
        self.assertIsNone(age_hours("2026-09-22", now))
        self.assertEqual(age_hours("2026-09-22T00:00:00Z", now), 24)

    def test_failed_or_empty_judicial_window_never_replaces_index(self):
        self.assertFalse(should_publish_judicial_index("error"))
        self.assertFalse(should_publish_judicial_index("empty_window"))
        self.assertTrue(should_publish_judicial_index("ok"))


if __name__ == "__main__":
    unittest.main()
