from copy import deepcopy
import hashlib
import json
import unittest

from scripts.data_health import with_source_file_provenance


class LaborHealthProvenanceTests(unittest.TestCase):
    def setUp(self):
        raw = {"處分字號": "測試字號", "違法法規法條": "勞動基準法第24條"}
        digest = hashlib.sha256(("109896|" + json.dumps(raw, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()
        self.row = {"id": "mol:" + digest, "dataset": "penalties", "source_file_id": "snapshot",
                    "source_url": "https://data.gov.tw/dataset/109896", "raw": raw,
                    "source_files": {"id": "snapshot", "dataset": "penalties", "sha256": "a" * 64,
                                     "source_url": "https://apiservice.mol.gov.tw/OdService/download/official",
                                     "downloaded_at": "2026-10-06T00:00:00+00:00",
                                     "metadata": {"dataset_id": "109896", "external_source_only": True}}}

    def test_actual_snapshot_chain_is_reported_without_claiming_raw_file_retention(self):
        row = with_source_file_provenance([self.row])[0]
        self.assertEqual(row["retrieved_at"], "2026-10-06T00:00:00+00:00")
        self.assertIsNone(row["provenance"]["original_file_retained"])
        self.assertEqual(row["provenance"]["source_record_id"], self.row["id"])

    def test_missing_or_wrong_file_does_not_become_complete_provenance(self):
        for updates in ({"source_files": {}}, {"source_file_id": "wrong"}, {"id": "mol:wrong"}, {"raw": {}}):
            row = with_source_file_provenance([{**self.row, **updates}])[0]
            self.assertNotIn("provenance", row)

    def test_malformed_hash_date_or_unofficial_download_is_rejected(self):
        for updates in ({"sha256": "bad"}, {"downloaded_at": "not-a-date"}, {"source_url": "https://example.org/"}):
            row = deepcopy(self.row)
            row["source_files"].update(updates)
            self.assertNotIn("provenance", with_source_file_provenance([row])[0])


if __name__ == "__main__":
    unittest.main()
