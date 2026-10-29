from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import ingest_civil_organizations_dev as ingest


class DevelopmentIngestCapacityTests(unittest.TestCase):
    def test_capacity_gate_precedes_every_bundle_and_never_cleans_data(self):
        bundle = {"evidence": [{"source_name": "official", "source_locator": {"snapshot_sha256": "a" * 64}}]}
        process = Mock()
        process.wait.return_value = 0
        with patch.object(ingest, "development_environment", return_value={}), \
                patch.object(ingest.subprocess, "run", side_effect=[
                    SimpleNamespace(returncode=0, stdout="1"), SimpleNamespace(returncode=0, stdout="")]), \
                patch.object(ingest.subprocess, "Popen", return_value=process):
            ingest.apply_bundles([bundle, bundle], source_name="official")
        writes = [call.args[0] for call in process.stdin.write.call_args_list]
        positions = [i for i, value in enumerate(writes) if "tei_ingest_bundle" in value]
        self.assertEqual(len(positions), 2)
        for position in positions:
            self.assertEqual(writes[position - 1], ingest.capacity_guard_sql())
        self.assertIn("480000000", "".join(writes))
        self.assertIn("RAISE EXCEPTION", "".join(writes))
        self.assertEqual(writes[-2], ingest.capacity_guard_sql())
        self.assertEqual(writes[-1], "COMMIT;\n")
        self.assertNotIn("DELETE", "".join(writes))
        self.assertNotIn("TRUNCATE", "".join(writes))

    def test_failed_capacity_transaction_is_reported_as_failed(self):
        bundle = {"evidence": [{"source_name": "official", "source_locator": {"snapshot_sha256": "a" * 64}}]}
        process = Mock()
        process.wait.return_value = 3
        with patch.object(ingest, "development_environment", return_value={}), \
                patch.object(ingest.subprocess, "run", side_effect=[
                    SimpleNamespace(returncode=0, stdout="1"), SimpleNamespace(returncode=0, stdout="")]), \
                patch.object(ingest.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(RuntimeError, "transaction failed"):
                ingest.apply_bundles([bundle], source_name="official")


if __name__ == "__main__":
    unittest.main()
