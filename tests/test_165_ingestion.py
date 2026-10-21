"""Safety and provenance checks for the Development-only official 165 index."""
import csv
import io
import unittest
from unittest.mock import patch

from scripts.ingest_165_domains_dev import database_env, normalize_domain, prepare


class FraudIndexTests(unittest.TestCase):
    def test_normalizes_only_domain_not_company_or_person_identity(self):
        self.assertEqual(normalize_domain("HTTPS://www.Example.COM/path"), "example.com")
        for value in ("", "中華電信", "localhost", "https://user@", "https://example.com:bad"):
            self.assertEqual(normalize_domain(value), "")

    def test_deduplicates_identical_official_rows_but_retains_distinct_records(self):
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=["網域", "網站性質", "民國年月"])
        writer.writeheader()
        for index in range(100):
            writer.writerow({"網域": f"site{index}.example.tw", "網站性質": "涉詐", "民國年月": "11501"})
        writer.writerow({"網域": "site0.example.tw", "網站性質": "涉詐", "民國年月": "11501"})
        count, records = prepare(stream.getvalue().encode())
        self.assertEqual(count, 101)
        self.assertEqual(len(records), 100)
        self.assertTrue(all(key.startswith("165:") for key in records))

    def test_rejects_other_database_without_disclosing_connection(self):
        with patch("scripts.ingest_165_domains_dev.read_local_env", return_value={}):
            with patch.dict("os.environ", {"TEI_DEV_DATABASE_URL":
                             "postgresql://user:secret@db.production.invalid/postgres"}):
                with self.assertRaisesRegex(RuntimeError, "tei-development"):
                    database_env()


if __name__ == "__main__":
    unittest.main()
