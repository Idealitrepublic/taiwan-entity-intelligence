import unittest
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.ops_health import evaluate, update_alert_history
from scripts.ops_backup import database_environment, validate_destination
from scripts.ops_health import main as ops_main


NOW = datetime(2026, 9, 25, 3, 0, tzinfo=timezone.utc)


def iso(hours=0):
    return (NOW - timedelta(hours=hours)).isoformat()


def healthy():
    state = {"last_attempt": iso(1), "last_sync": iso(1),
             "judicial_progress": {"total_batches": 2, "completed_batches": [0, 1]},
             "judicial_batch_stats": {"0": {}, "1": {}},
             "judicial_pending": {}, "judicial_source_unavailable": {"jid": {}}}
    status = {"judicial_status": "upstream_unavailable", "errors": []}
    health = {"generated_at": iso(1), "metrics": [{"source": "judiciary", "severity": "Medium"}]}
    return status, health, state


class OpsHealthTests(unittest.TestCase):
    def test_completed_window_with_upstream_gap_is_medium(self):
        result = evaluate(*healthy(), now=NOW)
        self.assertEqual(result["high_count"], 0)
        self.assertEqual([row["code"] for row in result["alerts"]], ["judicial_upstream_unavailable"])

    def test_stalled_cursor_pending_and_stale_health_block(self):
        status, health, state = healthy()
        state["judicial_progress"]["completed_batches"] = [0]
        state["judicial_pending"] = {"case": {"error_type": "timeout"}}
        state["last_attempt"] = iso(4)
        state["last_sync"] = iso(40)
        health["generated_at"] = iso(26)
        result = evaluate(status, health, state, now=NOW)
        codes = {row["code"] for row in result["alerts"]}
        self.assertTrue({"data_health_stale", "judicial_cursor_stalled", "judicial_pending",
                         "judicial_sync_stale"} <= codes)

    def test_expected_service_closure_does_not_page(self):
        status, health, state = healthy()
        status["judicial_status"] = "error"
        status["errors"] = [{"source": "judicial", "error_type": "service_closed"}]
        self.assertEqual(evaluate(status, health, state, now=NOW)["high_count"], 0)

    def test_quality_mismatch_is_high_and_missing_provenance_is_medium(self):
        status, health, state = healthy()
        health["judicial_window_quality"] = {"completed_batches": 1, "attempted_batches": 2,
                                             "pending_jids": 0, "upstream_unavailable_jids": 1}
        health["metrics"].append({"source": "procurement", "severity": "Medium",
                                  "provenance_rate": 0.0, "duplicate_rate": 0.0})
        result = evaluate(status, health, state, now=NOW)
        by_code = {row["code"]: row["severity"] for row in result["alerts"]}
        self.assertEqual(by_code["health_checkpoint_mismatch"], "High")
        self.assertEqual(by_code["provenance:procurement"], "Medium")

    def test_runtime_5xx_429_and_latency(self):
        status, health, state = healthy()
        events = [{"event": "request_complete", "status": 200, "duration_ms": 9000}
                  for _ in range(17)]
        events += [{"event": "request_complete", "status": 429, "duration_ms": 9000} for _ in range(2)]
        events += [{"event": "request_complete", "status": 502, "duration_ms": 9000}]
        codes = {row["code"] for row in evaluate(status, health, state, now=NOW,
                                                  runtime_events=events)["alerts"]}
        self.assertTrue({"runtime_5xx", "runtime_429", "runtime_p95"} <= codes)

    def test_alert_dedup_and_recovery(self):
        first = {"alerts": [{"code": "x", "severity": "High", "source": "judiciary",
                             "message": "failure"}]}
        history = update_alert_history({}, first, NOW)
        repeated = update_alert_history(history, first, NOW + timedelta(minutes=5))
        self.assertEqual(repeated["alerts"]["x"]["repeat_count"], 2)
        cleared = update_alert_history(repeated, {"alerts": []}, NOW + timedelta(minutes=10))
        self.assertEqual(cleared["alerts"]["x"]["status"], "resolved")
        self.assertIsNotNone(cleared["alerts"]["x"]["resolved_at"])

    def test_database_url_rejects_production_and_missing_password(self):
        with self.assertRaises(ValueError):
            database_environment("postgresql://postgres:secret@db.rztdbdurkjfrirsrrhtu.supabase.co/postgres")
        with self.assertRaises(ValueError):
            database_environment("postgresql://postgres@db.canqjiokrtcxkwblhmml.supabase.co/postgres")
        result = database_environment("postgresql://postgres:secret@db.canqjiokrtcxkwblhmml.supabase.co/postgres")
        self.assertEqual(result["PGHOST"], "db.canqjiokrtcxkwblhmml.supabase.co")

    def test_backup_cannot_target_repository_or_home(self):
        from scripts.ops_backup import ROOT
        with self.assertRaises(ValueError):
            validate_destination(ROOT)
        with self.assertRaises(ValueError):
            validate_destination(Path.home())

    def test_cli_alert_then_recovery_writes_private_dashboard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status, health, state = healthy()
            old = "2020-01-01T00:00:00Z"
            health["generated_at"] = old
            status_path, health_path, state_path = (root / name for name in
                                                    ("status.json", "health.json", "state.json"))
            output, alerts, dashboard = (root / name for name in
                                         ("ops.json", "alerts.json", "ops.md"))
            arguments = ["--status", str(status_path), "--health", str(health_path),
                         "--state", str(state_path), "--output", str(output),
                         "--alert-state", str(alerts), "--markdown", str(dashboard), "--check"]
            status_path.write_text(json.dumps(status))
            state_path.write_text(json.dumps(state))
            health_path.write_text(json.dumps(health))
            self.assertEqual(ops_main(arguments), 2)
            self.assertEqual(output.stat().st_mode & 0o077, 0)
            self.assertEqual(alerts.stat().st_mode & 0o077, 0)
            recent = datetime.now(timezone.utc).isoformat()
            health["generated_at"] = recent
            state["last_attempt"] = recent
            state["last_sync"] = recent
            health_path.write_text(json.dumps(health))
            state_path.write_text(json.dumps(state))
            self.assertEqual(ops_main(arguments), 0)
            history = json.loads(alerts.read_text())
            self.assertEqual(history["alerts"]["data_health_stale"]["status"], "resolved")


if __name__ == "__main__":
    unittest.main()
