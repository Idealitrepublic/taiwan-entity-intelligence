"""Synthetic source fixtures only; never publish fixture data."""
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.sources.court_notices import CATALOG, reviewed_bundle
from scripts.ingest_court_notices_dev import literal, apply
from src.sources.corporate_court_links import add_reviewed_corporate_link, LEGAL_NAME, UNIFORM


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
        self.assertEqual(len(bundle["entities"]), len(CATALOG))
        self.assertEqual(len(bundle["evidence"]), len(CATALOG))
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

    def corporate_fixture(self, *, role_proof=True, uniform=UNIFORM, setup="0630308"):
        from urllib.parse import urlencode
        target = self.directory / "wei-case.html"
        raw = target.read_bytes() + (LEGAL_NAME + "（下稱頂新公司）" +
                                   ("頂新公司不服；對頂新公司科以罰金刑" if role_proof else "僅被提及")).encode()
        target.write_bytes(raw)
        entry = next(r for r in self.manifest if r["file"] == target.name)
        entry.update(sha256=sha256(raw).hexdigest(), bytes=len(raw))
        registry = [{"Business_Accounting_NO": uniform, "Company_Name": LEGAL_NAME,
                     "Company_Status_Desc": "核准設立", "Company_Setup_Date": setup,
                     "Responsible_Name": "私人姓名不得輸出", "Company_Location": "私人地址不得輸出"}]
        raw = json.dumps(registry, ensure_ascii=False).encode()
        (self.directory / "registry-59066479.json").write_bytes(raw)
        self.manifest.append({"file": "registry-59066479.json", "sha256": sha256(raw).hexdigest(),
                              "bytes": len(raw), "retrieved_at": "2026-11-01T10:00:00+00:00",
                              "source_url": "https://data.gcis.nat.gov.tw/od/data/api/"
                              "5F64D864-61CB-4D0D-8AD9-492047CC1EA6?" +
                              urlencode({"$filter": "Business_Accounting_NO eq " + UNIFORM})})
        self.save()

    def test_reviewed_corporate_role_has_identifier_proofs_and_no_person_records(self):
        self.corporate_fixture()
        bundle = add_reviewed_corporate_link(self.bundle(publication_status="published"), self.directory)
        self.assertEqual(len(bundle["entities"]), len(CATALOG) + 1)
        self.assertEqual([r["relationship_type"] for r in bundle["relationships"]], ["RELATED_TO_JUDGMENT"])
        relation = bundle["relationships"][0]
        self.assertEqual(relation["confidence"], "HIGH")
        self.assertEqual(relation["start_date"], relation["end_date"])
        self.assertIn("Corporate party", relation["source_role"])
        self.assertFalse(any(e["entity_type"] == "Person" for e in bundle["entities"]))
        self.assertEqual(bundle["identifiers"][0]["value"], UNIFORM)
        self.assertNotIn("私人姓名", json.dumps(bundle, ensure_ascii=False))
        self.assertNotIn("私人地址", json.dumps(bundle, ensure_ascii=False))
        role = next(e for e in bundle["evidence"] if e["id"] == relation["primary_evidence_id"])
        self.assertFalse(role["source_locator"]["news_comention_is_relationship"])
        self.assertIn("registry_snapshot_sha256", role["source_locator"])

    def test_news_comention_without_a_specific_role_cannot_make_an_edge(self):
        self.corporate_fixture(role_proof=False)
        with self.assertRaisesRegex(ValueError, "co-mention"):
            add_reviewed_corporate_link(self.bundle(), self.directory)

    def test_wrong_identifier_even_with_same_name_is_rejected(self):
        self.corporate_fixture(uniform="12345678")
        with self.assertRaisesRegex(ValueError, "identifier mismatch"):
            add_reviewed_corporate_link(self.bundle(), self.directory)

    def test_company_created_after_case_cannot_be_linked_by_name(self):
        self.corporate_fixture(setup="1150101")
        with self.assertRaisesRegex(ValueError, "postdates"):
            add_reviewed_corporate_link(self.bundle(), self.directory)

    def test_nonofficial_registry_cannot_establish_identity(self):
        self.corporate_fixture()
        self.manifest[-1]["source_url"] = "https://example.com/company/" + UNIFORM
        self.save()
        with self.assertRaisesRegex(ValueError, "official exact"):
            add_reviewed_corporate_link(self.bundle(), self.directory)

    def test_dry_run_keeps_corporate_entities_and_relationships_draft(self):
        self.corporate_fixture()
        result = add_reviewed_corporate_link(self.bundle(), self.directory)
        self.assertTrue(all(e["publication_status"] == "draft" for e in result["entities"] + result["evidence"]))
        self.assertEqual(result["relationships"][0]["status"], "draft")

    def test_personal_record_is_rejected_before_backup_or_connection(self):
        bundle = self.bundle()
        bundle["entities"][0]["entity_type"] = "Person"
        with patch("scripts.ingest_court_notices_dev.check_backup", side_effect=AssertionError("must not connect")):
            with self.assertRaisesRegex(ValueError, "Personal records"):
                apply(bundle, self.directory / "receipt", self.directory / "backup")

    def test_unapproved_relationship_is_rejected_before_connection(self):
        bundle = self.bundle()
        bundle["relationships"] = [{"id": "r", "relationship_type": "OFFICER_OF"}]
        with self.assertRaisesRegex(ValueError, "corporate case roles"):
            apply(bundle, self.directory / "receipt", self.directory / "backup")

    def test_duplicate_entity_cannot_create_an_incorrect_expected_delta(self):
        bundle = self.bundle()
        bundle["entities"].append(bundle["entities"][0])
        with self.assertRaisesRegex(ValueError, "Duplicate identifiers"):
            apply(bundle, self.directory / "receipt", self.directory / "backup")


if __name__ == "__main__":
    unittest.main()
