import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
from scripts import sync_judicial_window as window


class WindowRotationTests(unittest.TestCase):
    def setup_files(self, root, stack):
        old = "old-jid"
        digest = hashlib.sha256(old.encode()).hexdigest()
        paths = {
            "STATE": "state.json",
            "JUDICIAL_SNAPSHOT": "snapshot.json",
            "STATUS": "status.json",
        }
        for attr, name in paths.items():
            stack.enter_context(patch.object(window.sync, attr, root / name))
        (root / "state.json").write_text(
            json.dumps(
                {
                    "last_sync": "2026-09-24T00:00:00Z",
                    "evidence_ids": ["retained"],
                    "judicial_progress": {"window_id": digest},
                    "judicial_source_unavailable": {
                        "old-jid": {"error_type": "upstream"}
                    },
                }
            )
        )
        (root / "snapshot.json").write_text(
            json.dumps({"jids": [old], "window_id": digest})
        )
        (root / "status.json").write_text("{}")
        stack.enter_context(
            patch.object(
                window,
                "inspect_checkpoint",
                return_value={
                    "completed_batches": 1,
                    "total_batches": 1,
                    "pending_jids": 0,
                },
            )
        )
        stack.enter_context(
            patch.object(window, "in_service_window", return_value=True)
        )
        stack.enter_context(patch.object(window, "get_token", return_value="test-only"))

    def test_rotation_archives_and_does_not_fake_freshness(self):
        with tempfile.TemporaryDirectory() as d, ExitStack() as stack:
            root = Path(d)
            self.setup_files(root, stack)

            def feed(token, on_metadata):
                on_metadata({"new-jid": {"source_url": "official"}})
                return ["new-jid"]

            stack.enter_context(patch.object(window, "changed_jids", side_effect=feed))
            self.assertTrue(window.prepare_new_window(batch_size=25))
            state = json.loads((root / "state.json").read_text())
            self.assertEqual(state["last_sync"], "2026-09-24T00:00:00Z")
            self.assertEqual(state["evidence_ids"], ["retained"])
            self.assertEqual(state["judicial_progress"]["completed_batches"], [])
            self.assertEqual(state["judicial_source_unavailable"], {})
            archived = list((root / "judicial_window_history").glob("*/state.json"))
            self.assertEqual(len(archived), 1)
            self.assertIn(
                "old-jid",
                json.loads(archived[0].read_text())["judicial_source_unavailable"],
            )
            self.assertEqual((root / "state.json").stat().st_mode & 0o077, 0)

    def test_invalid_feed_preserves_pair(self):
        with tempfile.TemporaryDirectory() as d, ExitStack() as stack:
            root = Path(d)
            self.setup_files(root, stack)
            before = (root / "state.json").read_bytes()
            stack.enter_context(patch.object(window, "changed_jids", return_value=[]))
            with self.assertRaises(RuntimeError):
                window.prepare_new_window()
            self.assertEqual((root / "state.json").read_bytes(), before)
            self.assertFalse((root / "judicial_window_history").exists())

    def test_closed_window_does_not_contact_api(self):
        with (
            patch.object(window, "in_service_window", return_value=False),
            patch.object(window, "get_token") as token,
        ):
            with self.assertRaises(RuntimeError):
                window.prepare_new_window()
            token.assert_not_called()

    def test_interruption_journal_can_recover_offline(self):
        with tempfile.TemporaryDirectory() as d, ExitStack() as stack:
            root = Path(d)
            self.setup_files(root, stack)

            def feed(token, on_metadata):
                on_metadata({"new-jid": {"source_url": "official"}})
                return ["new-jid"]

            stack.enter_context(patch.object(window, "changed_jids", side_effect=feed))
            with patch.object(
                window, "recover_window_transition", side_effect=OSError("interrupted")
            ):
                with self.assertRaises(OSError):
                    window.prepare_new_window()
            with patch.object(
                window, "get_token", side_effect=AssertionError("network")
            ):
                window.recover_window_transition()
            self.assertEqual(
                json.loads((root / "snapshot.json").read_text())["jids"], ["new-jid"]
            )
            self.assertFalse((root / "judicial_window_transition.json").exists())

    def test_incomplete_checkpoint_cannot_rotate(self):
        with tempfile.TemporaryDirectory() as d, ExitStack() as stack:
            self.setup_files(Path(d), stack)
            with (
                patch.object(
                    window,
                    "inspect_checkpoint",
                    return_value={
                        "completed_batches": 0,
                        "total_batches": 1,
                        "pending_jids": 1,
                    },
                ),
                patch.object(window, "get_token") as token,
            ):
                with self.assertRaises(RuntimeError):
                    window.prepare_new_window()
                token.assert_not_called()
