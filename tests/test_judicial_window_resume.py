import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts import sync_judicial_window as window

JID = "KLDM,111,訴,328,20230428,1"


class JudicialWindowResumeTests(unittest.TestCase):
    def test_official_service_window_uses_taipei_time(self):
        taipei = ZoneInfo("Asia/Taipei")
        self.assertTrue(window.in_service_window(datetime(2026, 9, 24, 0, 1, tzinfo=taipei)))
        self.assertFalse(window.in_service_window(datetime(2026, 9, 24, 6, 0, tzinfo=taipei)))

    def test_resume_skips_attempted_batch_with_pending_jid(self):
        snapshot = {"window_id": "abc", "jids": [JID]}
        state = {"judicial_progress": {"completed_batches": []},
                 "judicial_batch_stats": {"0": {"window_id": "abc", "selected": 1,
                                                "pending": 1}}}
        self.assertTrue(window.batch_already_attempted(0, state, snapshot, 1))
        self.assertFalse(window.batch_already_attempted(0, state, {**snapshot,
                                                                   "window_id": "changed"}, 1))

    def test_snapshot_matches_checkpoint_and_skips_saved_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = hashlib.sha256(JID.encode()).hexdigest()
            (root / "state.json").write_text(json.dumps({"judicial_progress": {
                "window_id": digest, "batch_size": 1, "completed_batches": [0]}}))
            (root / "evidence.jsonl").write_text(json.dumps({
                "source": {"type": "judicial", "record_id": JID}}) + "\n")
            with patch.object(window.sync, "JUDICIAL_SNAPSHOT", root / "snapshot.json"), \
                 patch.object(window.sync, "STATE", root / "state.json"), \
                 patch.object(window.sync, "EVIDENCE", root / "evidence.jsonl"), \
                 patch.object(window, "get_token", return_value="token"), \
                 patch.object(window, "changed_jids", return_value=[JID]):
                snapshot = window.ensure_snapshot()
                known = window.verify_completed(snapshot, 1)
                window.backfill_batch_stats(snapshot, 1, known)
                saved = json.loads((root / "state.json").read_text())
            self.assertEqual(snapshot["window_id"], digest)
            self.assertEqual(snapshot["jids"], [JID])
            self.assertEqual(saved["judicial_batch_stats"]["0"]["fetched_initial"], 1)

    def test_changed_jlist_cannot_reset_completed_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "state.json").write_text(json.dumps({"judicial_progress": {
                "window_id": "wrong", "completed_batches": [0]}}))
            with patch.object(window.sync, "JUDICIAL_SNAPSHOT", root / "snapshot.json"), \
                 patch.object(window.sync, "STATE", root / "state.json"), \
                 patch.object(window, "get_token", return_value="token"), \
                 patch.object(window, "changed_jids", return_value=[JID]):
                with self.assertRaisesRegex(RuntimeError, "differs from checkpoint"):
                    window.ensure_snapshot()
            self.assertFalse((root / "snapshot.json").exists())

    def test_offline_checkpoint_inspection_never_uses_api(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = hashlib.sha256(JID.encode()).hexdigest()
            (root / "snapshot.json").write_text(json.dumps({
                "window_id": digest, "jids": [JID], "metadata": {JID: {"source_url": "official"}}}))
            (root / "state.json").write_text(json.dumps({
                "judicial_progress": {"window_id": digest, "batch_size": 1,
                                      "total_batches": 1, "completed_batches": [0]},
                "judicial_batch_stats": {"0": {"window_id": digest, "selected": 1,
                                                 "fetched_initial": 1, "pending": 0,
                                                 "upstream_unavailable": 0, "recovered": 0,
                                                 "completed": True}}}))
            (root / "evidence.jsonl").write_text(json.dumps({
                "source": {"type": "judicial", "record_id": JID}}) + "\n")
            with patch.object(window.sync, "JUDICIAL_SNAPSHOT", root / "snapshot.json"), \
                 patch.object(window.sync, "STATE", root / "state.json"), \
                 patch.object(window.sync, "EVIDENCE", root / "evidence.jsonl"), \
                 patch.object(window, "get_token", side_effect=AssertionError("API called")), \
                 patch.object(window, "changed_jids", side_effect=AssertionError("API called")):
                report = window.inspect_checkpoint()
                self.assertEqual(report["completed_batches"], 1)
                self.assertEqual(report["ingested_jids"], 1)
                changed = json.loads((root / "snapshot.json").read_text())
                changed["window_id"] = "wrong"
                (root / "snapshot.json").write_text(json.dumps(changed))
                with self.assertRaisesRegex(RuntimeError, "disagree"):
                    window.inspect_checkpoint()


if __name__ == "__main__":
    unittest.main()
