import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import sync_public_sources as sync
from src.sources import judicial
from src.sources.judicial import JudicialRequestError


class JudicialSyncBatchTests(unittest.TestCase):
    def test_snapshot_retry_never_refetches_jlist(self):
        jid = "KLDM,111,訴,328,20230428,1"
        windows = []
        with patch.object(judicial, "get_token", return_value="local-test-token"), \
             patch.object(judicial, "changed_jids", side_effect=AssertionError("JList called")), \
             patch.object(judicial, "fetch_judgment", return_value={"JID": jid}), \
             patch.object(judicial, "_document_evidence", return_value={"evidence_id": "test"}):
            rows = list(judicial.evidence_rows(
                retry_jids=[jid], batch_size=1, on_window=windows.append,
                retry_window={"snapshot": True, "window_id": "fixed",
                              "selected_metadata": {jid: {"source_url": "official"}}}))
        self.assertEqual(rows, [{"evidence_id": "test"}])
        self.assertEqual(windows[0]["window_id"], "fixed")

    def test_unavailable_classification_requires_same_official_error_and_jlist(self):
        previous = {"response_error_hash": "a" * 64, "failure_runs": 1}
        detail = {"error_type": "upstream_document_error", "http_status": 200,
                  "response_error_hash": "a" * 64}
        metadata = {"source_url": "https://data.judicial.gov.tw/jdg/api/JList"}
        self.assertTrue(sync.verified_upstream_document_error(previous, detail, metadata))
        self.assertFalse(sync.verified_upstream_document_error(previous, {**detail,
                                                                          "response_error_hash": "b" * 64}, metadata))
        self.assertFalse(sync.verified_upstream_document_error(previous, {**detail,
                                                                          "http_status": 429}, metadata))
        self.assertFalse(sync.verified_upstream_document_error(previous, detail, None))

    def test_non_judicial_source_failure_is_recorded_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def government(on_error):
                yield {"evidence_id": "good"}
                on_error("penalty:example", RuntimeError("upstream timeout"))
            with patch.object(sync, "EVIDENCE", root / "evidence.jsonl"), \
                 patch.object(sync, "STATE", root / "state.json"), \
                 patch.object(sync, "STATUS", root / "status.json"), \
                 patch.object(sync, "JUDICIAL_INDEX", root / "index.json"), \
                 patch.object(sync, "public_rows", side_effect=government):
                self.assertEqual(sync.main(["--source", "government"]), 1)
            status = json.loads((root / "status.json").read_text())
            self.assertEqual(status["evidence_count"], 1)
            self.assertEqual(status["errors"][0]["dataset"], "penalty:example")

    def test_two_batches_resume_without_early_index_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def batch(*, batch_index, batch_size, on_window, **_):
                self.assertEqual(batch_size, 1)
                on_window({"total": 2, "selected": 1, "batch_index": batch_index,
                           "batch_size": 1, "window_id": "a" * 64, "remaining": 1 - batch_index})
                yield {"evidence_id": f"row-{batch_index}"}

            with patch.object(sync, "EVIDENCE", root / "evidence.jsonl"), \
                 patch.object(sync, "STATE", root / "state.json"), \
                 patch.object(sync, "STATUS", root / "status.json"), \
                 patch.object(sync, "JUDICIAL_INDEX", root / "index.json"), \
                 patch.object(sync, "judicial_rows", side_effect=batch), \
                 patch.object(sync, "build_index", return_value={"records": ["ok"]}), \
                 patch.dict("os.environ", {"JUDICIAL_USER": "test", "JUDICIAL_PASSWORD": "test"}):
                self.assertEqual(sync.main(["--source", "judicial", "--judicial-batch-size", "1"]), 1)
                self.assertFalse((root / "index.json").exists())
                self.assertEqual(sync.main(["--source", "judicial", "--judicial-batch-size", "1",
                                            "--judicial-batch-index", "1"]), 0)
            state = json.loads((root / "state.json").read_text())
            self.assertEqual(state["judicial_progress"]["completed_batches"], [0, 1])
            self.assertEqual(state["last_judicial_status"], "ok")
            self.assertEqual(json.loads((root / "index.json").read_text())["records"], ["ok"])

    def test_failed_jid_is_sanitized_and_retried_without_refetching_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []

            def batch(*, on_error, on_success, on_window, retry_jids, **_):
                calls.append(retry_jids)
                on_window({"total": 2, "selected": len(retry_jids) if retry_jids else 2,
                           "batch_index": 0, "batch_size": 2, "window_id": "b" * 64,
                           "remaining": 0})
                if retry_jids is None:
                    on_error("KLDM,111,訴,328,20230428,1",
                             JudicialRequestError("upstream_document_error", path="/JDoc",
                                                  http_status=200, attempts=4))
                    yield {"evidence_id": "good"}
                else:
                    on_success(retry_jids[0])
                    yield {"evidence_id": "retried"}

            with patch.object(sync, "EVIDENCE", root / "evidence.jsonl"), \
                 patch.object(sync, "STATE", root / "state.json"), \
                 patch.object(sync, "STATUS", root / "status.json"), \
                 patch.object(sync, "JUDICIAL_INDEX", root / "index.json"), \
                 patch.object(sync, "judicial_rows", side_effect=batch), \
                 patch.object(sync, "build_index", return_value={"records": ["ok"]}), \
                 patch.dict("os.environ", {"JUDICIAL_USER": "secret-user",
                                                "JUDICIAL_PASSWORD": "secret-password"}):
                self.assertEqual(sync.main(["--source", "judicial", "--judicial-batch-size", "2"]), 1)
                failed = json.loads((root / "status.json").read_text())
                self.assertEqual(failed["errors"][0]["http_status"], 200)
                self.assertEqual(failed["errors"][0]["request"]["endpoint"], "/JDoc")
                self.assertNotIn("secret", (root / "status.json").read_text())
                self.assertFalse((root / "index.json").exists())
                self.assertEqual(sync.main(["--source", "judicial", "--judicial-batch-size", "2",
                                            "--judicial-retry-failed"]), 0)
            self.assertEqual(len(calls[1]), 1)
            self.assertEqual(json.loads((root / "status.json").read_text())["judicial_pending"], 0)
            self.assertEqual(json.loads((root / "index.json").read_text())["records"], ["ok"])

    def test_repeated_official_document_error_isolated_and_recheckable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jid = "KLDM,111,訴,328,20230428,1"
            calls = []

            def batch(*, on_error, on_success, on_window, retry_jids, **_):
                calls.append(retry_jids)
                on_window({"total": 1, "selected": 1, "batch_index": 0,
                           "batch_size": 1, "window_id": "c" * 64, "remaining": 0,
                           "selected_metadata": {jid: {"list_date": "2026-09-23",
                                                       "source_url": "https://data.judicial.gov.tw/jdg/api/JList",
                                                       "position": 0}}})
                if len(calls) < 3:
                    on_error(jid, JudicialRequestError("upstream_document_error", path="/JDoc",
                                                       http_status=200, attempts=4,
                                                       response_error_hash="d" * 64))
                else:
                    on_success(jid)
                    yield {"evidence_id": "recovered"}

            with patch.object(sync, "EVIDENCE", root / "evidence.jsonl"), \
                 patch.object(sync, "STATE", root / "state.json"), \
                 patch.object(sync, "STATUS", root / "status.json"), \
                 patch.object(sync, "JUDICIAL_INDEX", root / "index.json"), \
                 patch.object(sync, "judicial_rows", side_effect=batch), \
                 patch.object(sync, "build_index", return_value={"records": []}), \
                 patch.dict("os.environ", {"JUDICIAL_USER": "test", "JUDICIAL_PASSWORD": "test"}):
                self.assertEqual(sync.main(["--source", "judicial", "--judicial-batch-size", "1"]), 1)
                self.assertEqual(sync.main(["--source", "judicial", "--judicial-batch-size", "1",
                                            "--judicial-retry-failed"]), 0)
                status = json.loads((root / "status.json").read_text())
                self.assertEqual(status["judicial_status"], "upstream_unavailable")
                self.assertEqual(status["judicial_pending"], 0)
                self.assertEqual(status["judicial_source_unavailable"][0]["classification"],
                                 "permanent-source-error")
                self.assertEqual(sync.main(["--source", "judicial", "--judicial-batch-size", "1",
                                            "--judicial-recheck-unavailable"]), 0)
            self.assertEqual(json.loads((root / "status.json").read_text())["judicial_source_unavailable"], [])
            self.assertEqual(json.loads((root / "state.json").read_text())["judicial_progress"]["completed_batches"], [0])

    def test_explicit_retry_selection_reaches_later_pending_jid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jids = [f"KLDM,111,訴,{number},20230428,1" for number in (1, 2)]
            (root / "state.json").write_text(json.dumps({
                "judicial_progress": {"window_id": "d" * 64, "batch_size": 1,
                                      "total_batches": 2, "completed_batches": []},
                "judicial_pending": {jid: {"jid": jid, "batch_index": index}
                                     for index, jid in enumerate(jids)}}))
            (root / "snapshot.json").write_text(json.dumps({
                "window_id": "d" * 64, "jids": jids,
                "metadata": {jid: {"source_url": "official"} for jid in jids}}))
            seen = []

            def batch(*, on_window, retry_jids, on_error, **_):
                seen.extend(retry_jids)
                on_window({"total": 2, "selected": 1, "batch_size": 1,
                           "window_id": "d" * 64, "batch_index": 0})
                on_error(retry_jids[0], JudicialRequestError("timeout", path="/JDoc"))
                return iter(())

            with patch.object(sync, "EVIDENCE", root / "evidence.jsonl"), \
                 patch.object(sync, "STATE", root / "state.json"), \
                 patch.object(sync, "STATUS", root / "status.json"), \
                 patch.object(sync, "JUDICIAL_SNAPSHOT", root / "snapshot.json"), \
                 patch.object(sync, "JUDICIAL_INDEX", root / "index.json"), \
                 patch.object(sync, "judicial_rows", side_effect=batch), \
                 patch.dict("os.environ", {"JUDICIAL_USER": "test", "JUDICIAL_PASSWORD": "test"}):
                sync.main(["--source", "judicial", "--judicial-batch-size", "1",
                           "--judicial-retry-failed"], emit_status=False,
                          retry_selection=[jids[1]])
            self.assertEqual(seen, [jids[1]])
            self.assertEqual(json.loads((root / "status.json").read_text())["judicial_window"]["total"], 2)


if __name__ == "__main__":
    unittest.main()
