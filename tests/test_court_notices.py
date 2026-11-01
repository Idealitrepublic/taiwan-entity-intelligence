"""Synthetic source fixtures only; never publish fixture data."""
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.sources.court_notices import CATALOG, reviewed_bundle
from scripts.ingest_court_notices_dev import literal


class CourtNoticeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.manifest = []
        for fact in CATALOG.values():
            text = ("<html><body>" + fact["proof"] + fact["lower_court"] + "全案確定"
                    + "私人姓名、私人住址，不得匯入<script>secretToken</script></body></html>")
            raw = text.encode()
            (self.directory / fact["file"]).write_bytes(raw)
            self.manifest.append({"file": fact["file"], "source_url":
                                  "https://www.judicial.gov.tw/tw/cp-1888-" + fact["url_suffix"],
                                  "sha256": sha256(raw).hexdigest(), "bytes": len(raw),
                                  "retrieved_at": "2026-11-01T10:00:00+00:00"})
        self.save()

    def save(self):
        (self.directory / "acquisition.json").write_text(json.dumps(self.manifest))

    def bundle(self, **kwargs):
        return reviewed_bundle(self.directory, as_of=date(2026, 11, 1), **kwargs)

    def test_exports_only_case_metadata_with_traceable_evidence(self):
        bundle = self.bundle(publication_status="published")
        self.assertEqual(len(bundle["entities"]), 3)
        self.assertEqual(len(bundle["evidence"]), 3)
        self.assertNotIn("relationships", bundle)
        self.assertTrue(all(e["entity_type"] == "Judgment" for e in bundle["entities"]))
        self.assertTrue(all(e["identity_status"] == "SOURCE_SCOPED" for e in bundle["entities"]))
        serialized = json.dumps(bundle, ensure_ascii=False)
        for excluded in ("私人姓名", "私人住址", "secretToken"):
            self.assertNotIn(excluded, serialized)
        for evidence in bundle["evidence"]:
            self.assertIn("並非判決全文", evidence["summary"])
            self.assertIn("不表示所有當事人均有罪", evidence["summary"])
            self.assertEqual(evidence["source_locator"]["party_identity_matching"], "not_performed")
        for link, entity, evidence in zip(bundle["entity_evidence"], bundle["entities"], bundle["evidence"]):
            self.assertEqual((link["entity_id"], link["evidence_id"]), (entity["id"], evidence["id"]))

    def test_docket_group_is_not_split_into_invented_jids(self):
        bundled = self.bundle()
        grouped = [e for e in bundled["evidence"] if e["source_record_id"] == "judicial-news:688053"]
        self.assertEqual(len(grouped), 1)
        self.assertEqual(len(grouped[0]["source_locator"]["docket_numbers"]), 2)
        self.assertNotIn("jid", grouped[0]["source_locator"])

    def test_retrieval_retry_does_not_duplicate_entities_or_evidence(self):
        before = self.bundle()
        self.manifest[0]["retrieved_at"] = "2026-11-01T11:00:00+00:00"
        self.save()
        after = self.bundle()
        for kind in ("entities", "evidence"):
            self.assertEqual([e["id"] for e in before[kind]], [e["id"] for e in after[kind]])

    def test_tampered_snapshot_or_unofficial_host_is_rejected(self):
        for key, value in (("sha256", "0" * 64), ("bytes", 0),
                           ("source_url", "https://untrusted.example/tw/notice")):
            original = self.manifest[0][key]
            self.manifest[0][key] = value
            self.save()
            with self.assertRaises(ValueError):
                self.bundle()
            self.manifest[0][key] = original

    def test_duplicate_manifest_is_rejected(self):
        self.manifest.append(self.manifest[0])
        self.save()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.bundle()

    def test_source_without_finality_proof_rejects_entire_batch(self):
        fact = list(CATALOG.values())[-1]
        path = self.directory / fact["file"]
        raw = "上訴中，尚未確定".encode()
        path.write_bytes(raw)
        self.manifest[-1].update(sha256=sha256(raw).hexdigest(), bytes=len(raw))
        self.save()
        with self.assertRaisesRegex(ValueError, "proof is missing"):
            self.bundle()

    def test_future_or_old_finality_and_future_retrieval_are_rejected(self):
        for review_date in (date(2022, 1, 1), date(2030, 11, 1)):
            with self.assertRaisesRegex(ValueError, "five-year"):
                reviewed_bundle(self.directory, as_of=review_date)
        self.manifest[0]["retrieved_at"] = "2027-01-01T00:00:00+00:00"
        self.save()
        with self.assertRaisesRegex(ValueError, "timestamp"):
            self.bundle()

    def test_unreviewed_catalog_fields_are_not_exported(self):
        with patch.dict(CATALOG["667383"], {"person": "不得輸出的姓名", "company_id": "12345678"}):
            value = json.dumps(self.bundle(), ensure_ascii=False)
        self.assertNotIn("不得輸出的姓名", value)
        self.assertNotIn("12345678", value)

    def test_sql_literal_cannot_inject_statements(self):
        self.assertEqual(literal("a'); DROP TABLE x;--"), "'a''); DROP TABLE x;--'")


if __name__ == "__main__":
    unittest.main()
