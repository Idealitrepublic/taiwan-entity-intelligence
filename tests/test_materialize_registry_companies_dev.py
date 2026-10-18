import json
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import materialize_registry_companies_dev as ingest


ROWS = [
    {"uniform": "22099131", "expected_name": "台灣積體電路製造股份有限公司",
     "labels": 1, "company_form": True},
    {"uniform": "43878009", "expected_name": "威廉沈娛樂有限公司",
     "labels": 2, "company_form": True},
    {"uniform": "12529007", "expected_name": "環泰企業股份有限公司",
     "labels": 1, "company_form": True},
]
REGISTRY = {"Business_Accounting_NO": "22099131",
            "Company_Name": "台灣積體電路製造股份有限公司",
            "Company_Status_Desc": "核准設立", "Change_Of_Approval_Data": "1150821"}
DEV_ENV = {"PGHOST": "db.canqjiokrtcxkwblhmml.supabase.co", "PGUSER": "postgres"}


class RegistryIntegrationTests(unittest.TestCase):
    def test_conflicting_donor_names_do_not_block_independent_official_identity(self):
        official = {**REGISTRY, "Business_Accounting_NO": "43878009",
                    "Company_Name": "威廉沈娛樂有限公司"}
        status, bundle = ingest.classify(ROWS[1], official, "2026-10-18T00:00:00+00:00")
        self.assertEqual(status, "verified_id_conflicting_donor_labels")
        self.assertEqual(bundle["entities"][0]["source_id"], "43878009")
        self.assertNotIn("relationships", bundle)

    def test_exact_id_name_produces_registry_only_bundle(self):
        status, bundle = ingest.classify(ROWS[0], REGISTRY, "2026-10-18T00:00:00+00:00")
        self.assertEqual(status, "verified")
        self.assertEqual(bundle["entities"][0]["source_id"], "22099131")
        self.assertEqual(len(bundle["entity_evidence"]), 1)
        self.assertNotIn("relationships", bundle)

    def test_name_mismatch_does_not_create_donor_relationship(self):
        changed = {**REGISTRY, "Company_Name": "另一家公司股份有限公司"}
        status, bundle = ingest.classify(ROWS[0], changed, "2026-10-18T00:00:00+00:00")
        self.assertEqual(status, "verified_id_name_differs")
        self.assertEqual(bundle["entities"][0]["canonical_name"], "另一家公司股份有限公司")
        self.assertNotIn("relationships", bundle)

    def test_dissolved_company_keeps_official_status(self):
        changed = {**REGISTRY, "Company_Status_Desc": "解散"}
        status, bundle = ingest.classify(ROWS[0], changed, "2026-10-18T00:00:00+00:00")
        self.assertEqual(status, "verified_id_not_active")
        self.assertIn("解散", bundle["evidence"][0]["summary"])

    def test_run_checkpoints_published_batch_and_resumes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "checkpoint.json"
            fetched = []
            published = []

            def fetch(uniform):
                fetched.append(uniform)
                if uniform == "22099131":
                    return REGISTRY, None
                return None, "http_504"

            with patch.object(ingest, "candidates", return_value=ROWS), \
                 patch.object(ingest, "publish", side_effect=lambda bundles, env: published.extend(bundles)):
                first = ingest.run(apply=True, state_path=path, fetch=fetch,
                                   env=DEV_ENV, pause=lambda _seconds: None)
                second = ingest.run(apply=True, state_path=path, fetch=fetch,
                                    env=DEV_ENV, pause=lambda _seconds: None)
            self.assertEqual(first["published"], 1)
            self.assertEqual(first["processed"], 3)
            self.assertEqual(first["deferred"], 0)
            self.assertEqual(first["unresolved"]["official_unavailable"], 2)
            self.assertEqual(first["source_errors"]["http_504"], 2)
            self.assertEqual(second["already_integrated"], 1)
            self.assertEqual(len(published), 1)
            self.assertEqual(fetched.count("22099131"), 1)
            self.assertEqual(json.loads(path.read_text())["22099131"]["status"], "integrated")

    def test_bounded_run_reports_deferred_candidates(self):
        with patch.object(ingest, "candidates", return_value=ROWS):
            totals = ingest.run(apply=False, max_candidates=1, env=DEV_ENV,
                                fetch=lambda _uniform: (REGISTRY, None),
                                pause=lambda _seconds: None)
        self.assertEqual((totals["candidates"], totals["processed"], totals["deferred"]),
                         (3, 1, 2))

    def test_non_development_target_refused_before_query(self):
        with patch.object(ingest, "candidates") as query:
            with self.assertRaises(RuntimeError):
                ingest.run(apply=True, env={"PGHOST": "production.example", "PGUSER": "postgres"})
            query.assert_not_called()

    def test_official_empty_200_is_not_a_transport_error(self):
        with patch.object(ingest.urllib.request, "urlopen", return_value=BytesIO(b"")) as call:
            row, error = ingest.official_registry("01814546", pause=lambda _seconds: None)
        self.assertIsNone(row)
        self.assertEqual(error, "official_not_found")
        self.assertEqual(call.call_count, 1)


if __name__ == "__main__":
    unittest.main()
