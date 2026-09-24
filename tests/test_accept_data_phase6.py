import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import accept_data_phase6 as gate
from src.data_health import SOURCES


class DataPhase6AcceptanceTests(unittest.TestCase):
    def test_complete_window_and_fresh_health_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jid = "KLDM,111,訴,328,20230428,1"
            now = datetime(2026, 9, 25, 2, tzinfo=timezone.utc)
            checkpoint = {"jlist_jids": 1, "total_batches": 1,
                          "completed_batches": 1, "attempted_batches": 1,
                          "pending_jids": 0, "ingested_jids": 1,
                          "upstream_unavailable_jids": 0}
            (root / "state.json").write_text(json.dumps({"judicial_pending": {},
                                                        "judicial_source_unavailable": {},
                                                        "last_attempt": now.isoformat()}))
            (root / "snapshot.json").write_text(json.dumps({"jids": [jid]}))
            (root / "evidence.jsonl").write_text(json.dumps({
                "evidence_id": "proof", "source": {"type": "judicial", "record_id": jid,
                "name": "司法院", "url": "https://judgment.judicial.gov.tw/example",
                "content_hash": "hash"}, "retrieved_at": now.isoformat(),
                "fact": {"type": "court_record"}, "raw": {"JID": jid}}) + "\n")
            health = {"generated_at": now.isoformat(),
                      "metrics": [{"source": name, "severity": "OK"} for name in SOURCES],
                      "judicial_window_quality": {"jlist_total": 1, "completed_batches": 1,
                                                   "pending_jids": 0, "ingested_jids": 1,
                                                   "upstream_unavailable_jids": 0}}
            with patch.object(gate, "inspect_checkpoint", return_value=checkpoint), \
                 patch.object(gate.sync, "STATE", root / "state.json"), \
                 patch.object(gate.sync, "JUDICIAL_SNAPSHOT", root / "snapshot.json"), \
                 patch.object(gate.sync, "EVIDENCE", root / "evidence.jsonl"):
                self.assertTrue(gate.evaluate(health, now=now)["accepted"])
                incomplete = {**checkpoint, "completed_batches": 0}
                with patch.object(gate, "inspect_checkpoint", return_value=incomplete):
                    self.assertFalse(gate.evaluate(health, now=now)["accepted"])
                stale = {**health, "generated_at": "2026-09-23T00:00:00Z"}
                self.assertIn("Data Health report stale or predates latest sync",
                              gate.evaluate(stale, now=now)["issues"])


if __name__ == "__main__":
    unittest.main()
