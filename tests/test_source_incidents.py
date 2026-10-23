import unittest
from datetime import datetime, timedelta, timezone

from src.source_incidents import active_source_notices


TAIWAN = timezone(timedelta(hours=8))


class SourceIncidentTests(unittest.TestCase):
    def test_notice_only_during_verified_official_window(self):
        before = datetime(2026, 10, 23, 18, 59, tzinfo=TAIWAN)
        during = datetime(2026, 10, 24, 12, 0, tzinfo=TAIWAN)
        after = datetime(2026, 10, 27, 0, 0, tzinfo=TAIWAN)
        self.assertEqual(active_source_notices(before), [])
        self.assertEqual(len(active_source_notices(during)), 1)
        self.assertEqual(active_source_notices(after), [])
        self.assertIn("gcis.nat.gov.tw/mainNew", active_source_notices(during)[0]["source_url"])
        self.assertIn("data.gcis.nat.gov.tw/ns/news/detail", active_source_notices(during)[0]["notice_url"])

    def test_naive_time_rejected(self):
        with self.assertRaises(ValueError):
            active_source_notices(datetime(2026, 10, 24))
