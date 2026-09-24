import unittest
from datetime import datetime, timezone

from src.data_health import age_hours, metric, severity
from scripts.sync_public_sources import should_publish_judicial_index
from scripts.data_health import markdown, with_primary_provenance


class DataHealthTests(unittest.TestCase):
    def test_published_fact_provenance_comes_from_primary_evidence(self):
        rows = with_primary_provenance([{"id": "fact", "evidence_records": {
            "source_url": "https://official.test/row", "retrieved_at": "2026-09-23T00:00:00Z",
            "source_name": "official", "source_record_id": "one"}}])
        self.assertEqual(rows[0]["source_record_id"], "one")
        self.assertEqual(metric("asset_declarations", observed=1, expected=None,
                                rows=rows, identity="id", scope="sample")["provenance_rate"], 1)

    def test_unknown_denominator_is_not_zero(self):
        item = metric("judiciary", observed=3, expected=None, scope="known cases")
        self.assertIsNone(item["coverage"])
        self.assertEqual(severity(item), "Unknown")

    def test_duplicate_and_provenance(self):
        rows = [
            {"id": "a", "source_url": "https://official.test/1", "retrieved_at": "2026-01-01T00:00:00Z", "provenance": "official"},
            {"id": "a", "source_url": "https://official.test/2", "retrieved_at": "2026-01-01T00:00:00Z"},
        ]
        item = metric("procurement", observed=2, expected=2, rows=rows, identity="id", scope="sample")
        self.assertEqual(item["duplicate_rate"], 0.5)
        self.assertEqual(item["provenance_rate"], 0.5)
        self.assertEqual(severity(item), "Medium")

    def test_error_overrides_full_sample_coverage(self):
        item = metric("labor_penalties", observed=3, expected=3, errors=1, scope="sample")
        self.assertEqual(severity(item), "High")

    def test_unprocessed_jlist_batches_are_high_even_without_ingestion_errors(self):
        item = metric("judiciary", observed=3, expected=3, errors=0, scope="known cases")
        item["unprocessed_batches"] = 722
        self.assertEqual(item["error_count"], 0)
        self.assertEqual(severity(item), "High")

    def test_verified_upstream_gap_is_medium_not_ingestion_failure(self):
        item = metric("judiciary", observed=3, expected=3, errors=0, scope="known cases")
        item["upstream_unavailable_rate"] = 0.1504
        self.assertEqual(severity(item), "Medium")
        item["error_count"] = 1
        self.assertEqual(severity(item), "High")

    def test_completed_window_uses_cumulative_judicial_counts(self):
        report = {"generated_at": "2026-09-24T00:00:00Z", "metrics": [],
                  "judicial_sync": {"judicial_fetched": 0,
                                    "judicial_progress": {"completed_batches": 724, "total_batches": 724}},
                  "judicial_window_quality": {"ingested_jids": 15362, "pending_jids": 0,
                                              "attempted_batches": 724, "jlist_total": 18082}}
        output = markdown(report)
        self.assertIn("15362 documents ingested across the window", output)
        self.assertIn("724 attempted", output)
        self.assertIn("completed window has source-side document gaps", output)

    def test_zero_real_data_is_high_without_invented_denominator(self):
        item = metric("asset_declarations", observed=0, expected=None,
                      required_data=True, scope="public")
        self.assertIsNone(item["coverage"])
        self.assertEqual(severity(item), "High")

    def test_invalid_or_naive_freshness_is_unknown(self):
        now = datetime(2026, 9, 23, tzinfo=timezone.utc)
        self.assertIsNone(age_hours("2026-09-22", now))
        self.assertEqual(age_hours("2026-09-22T00:00:00Z", now), 24)

    def test_failed_or_empty_judicial_window_never_replaces_index(self):
        self.assertFalse(should_publish_judicial_index("error"))
        self.assertFalse(should_publish_judicial_index("empty_window"))
        self.assertTrue(should_publish_judicial_index("ok"))

    def test_report_separates_public_probe_from_all_state_sql_audit(self):
        report = {"generated_at": "2026-09-22T00:00:00Z", "metrics": []}
        audit = {"audited_at": "2026-09-22T01:00:00Z", "project_ref": "example",
                 "all_states_counts": {"politician_entities": 0},
                 "missing_migration_versions": ["123"]}
        output = markdown(report, audit)
        self.assertIn("separate snapshot", output)
        self.assertIn("`politician_entities`: 0", output)
        self.assertIn("123", output)

    def test_report_describes_latest_local_judicial_failure(self):
        report = {"generated_at": "2026-09-23T18:00:00Z", "metrics": [],
                  "judicial_sync": {"last_attempt": "2026-09-23T17:59:00Z",
                                    "judicial_status": "error", "judicial_fetched": 18,
                                    "judicial_failed": 7, "judicial_pending": 7,
                                    "judicial_window": {"batch_index": 0, "total": 18082}},
                  "judicial_failures": [{"jid": "KLDM,111,訴,328,20230428,1",
                                          "http_status": 200,
                                          "error_type": "upstream_document_error",
                                          "request": {"method": "POST", "endpoint": "/JDoc"},
                                          "attempts": 4, "elapsed_ms": 10640}]}
        output = markdown(report)
        self.assertIn("18 documents fetched, 7 document failures", output)
        self.assertIn("7 pending retries", output)
        self.assertIn("latest batch 0, 18082 changed JIDs", output)
        self.assertIn("POST /JDoc | 4 | 10640", output)

    def test_report_separates_verified_upstream_document_from_ingestion_error(self):
        report = {"generated_at": "2026-09-24T00:00:00Z", "metrics": [],
                  "judicial_sync": {"judicial_progress": {"completed_batches": 2,
                                                         "total_batches": 724}},
                  "judicial_upstream_unavailable": [{
                      "jid": "KLDM,111,訴,328,20230428,1", "error_type": "upstream_document_error",
                      "failure_runs": 2, "first_seen": "2026-09-23T00:00:00Z",
                      "last_seen": "2026-09-24T00:00:00Z",
                      "jlist_metadata": {"list_date": "2026-09-23"},
                      "provenance": {"source_url": "https://data.judicial.gov.tw/jdg/api/JList"}}],
                  "judicial_window_quality": {"attempted_jids": 50, "jlist_total": 18082,
                                              "jlist_processing_coverage": 0.0028,
                                              "ingested_jids": 42, "pending_jids": 0,
                                              "upstream_unavailable_jids": 8,
                                              "ingestion_failure_rate": 0,
                                              "upstream_unavailable_rate": 0.16,
                                              "last_attempt_age_hours": 1}}
        output = markdown(report)
        self.assertIn("Verified upstream document unavailable", output)
        self.assertIn("2/724 JList batches complete", output)
        self.assertIn("KLDM,111,訴,328,20230428,1", output)
        self.assertIn("Attempted: 50/18082 JIDs", output)

    def test_report_identifies_official_service_hours_as_source_availability(self):
        report = {"generated_at": "2026-09-24T00:00:00Z", "metrics": [],
                  "judicial_service_closed": True}
        self.assertIn("00:00–06:00 Asia/Taipei", markdown(report))


if __name__ == "__main__":
    unittest.main()
