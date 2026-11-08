import copy
import unittest

from scripts.sync_judicial_window import verify_unavailable_receipts


class JudicialUnavailableReceiptTests(unittest.TestCase):
    def setUp(self):
        self.jid = "CCEV,115,潮小,480,20261022,1"
        metadata = {"list_date": "2026-10-29", "position": 268,
                    "source_url": "https://data.judicial.gov.tw/jdg/api/JList"}
        self.snapshot = {"metadata": {self.jid: metadata}}
        self.item = {"source": "judicial", "jid": self.jid,
                     "classification": "permanent-source-error", "http_status": 200,
                     "error_type": "upstream_document_error", "failure_runs": 2,
                     "response_error_hash": "a" * 64, "jlist_metadata": metadata,
                     "request": {"method": "POST", "endpoint": "/JDoc"},
                     "first_seen": "2026-11-04T16:41:38+00:00",
                     "last_seen": "2026-11-04T17:59:42+00:00",
                     "provenance": {"source_name": "Judicial Yuan JList/JDoc",
                                    "source_url": metadata["source_url"],
                                    "retrieved_at": "2026-11-04T17:59:42+00:00"}}

    def test_repeated_official_error_is_accounted_without_network_or_mutation(self):
        before = copy.deepcopy(self.item)
        self.assertEqual(verify_unavailable_receipts({self.jid: self.item}, self.snapshot), 1)
        self.assertEqual(self.item, before)

    def test_lone_error_timeout_or_missing_fingerprint_cannot_clear_gate(self):
        for patch in ({"failure_runs": 1}, {"http_status": 429},
                      {"error_type": "timeout"}, {"response_error_hash": ""},
                      {"jid": "other"}, {"last_seen": "2020-01-01T00:00:00+00:00"},
                      {"first_seen": "2026-01-01"}):
            with self.subTest(patch=patch), self.assertRaises(RuntimeError):
                verify_unavailable_receipts({self.jid: {**self.item, **patch}}, self.snapshot)

    def test_changed_jlist_or_unofficial_provenance_is_rejected(self):
        for patch in ({"jlist_metadata": {}}, {"provenance": {}},
                      {"request": {"method": "POST", "endpoint": "/JDoc", "token": "redacted"}}):
            with self.subTest(patch=patch), self.assertRaises(RuntimeError):
                verify_unavailable_receipts({self.jid: {**self.item, **patch}}, self.snapshot)


if __name__ == "__main__":
    unittest.main()
