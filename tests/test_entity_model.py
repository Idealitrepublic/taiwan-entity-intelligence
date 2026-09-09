from dataclasses import replace
from datetime import datetime, timezone
import unittest

from src.entities.models import Entity, evidence_from_projection, stable_id, web_url
from src.entities.resolution import company_entity, person_observation, resolve_identifier
from src.entities.backfill import build_legacy_bundle
from src.relationships.models import Relationship


def snapshot():
    return {
        "companies": [{"id": 1, "uniform_number": "12345678", "name": "範例公司",
                       "fetched_at": "2025-01-02T00:00:00+00:00", "source": "MOEA/GCI",
                       "source_url": "https://example.gov.tw/company", "address": "PRIVATE", "raw": {"phone": "PRIVATE"}}],
        "company_people": [{"id": 1, "company_id": 1, "person_name": "同名人物", "role": "董事",
                            "fetched_at": "2025-01-02T00:00:00+00:00", "source_url": "https://example.gov.tw/directors",
                            "share_count": 1000}],
    }


class EntityModelTests(unittest.TestCase):
    def test_company_rename_keeps_internal_id(self):
        self.assertEqual(company_entity("12345678", "舊名").id, company_entity("12345678", "新名").id)

    def test_same_name_different_records_never_merges(self):
        a = person_observation("company1", "record1", "王小明")
        b = person_observation("company2", "record1", "王小明")
        c = person_observation("company1", "record2", "王小明")
        self.assertEqual(len({a.id, b.id, c.id}), 3)
        self.assertEqual(a.identity_status, "SOURCE_SCOPED")

    def test_reordering_does_not_change_person_id(self):
        data = snapshot()
        data["company_people"].append({**data["company_people"][0], "id": 2})
        one, _ = build_legacy_bundle(data)
        data["company_people"].reverse()
        two, _ = build_legacy_bundle(data)
        self.assertEqual({e["id"] for e in one["entities"]}, {e["id"] for e in two["entities"]})

    def test_identifier_requires_namespace_and_exact_confidence(self):
        rows = [{"namespace": "official:one", "value": "123", "entity_id": "a", "confidence": "EXACT"}]
        self.assertEqual(resolve_identifier("official:one", "123", rows).entity_id, "a")
        self.assertIsNone(resolve_identifier("official:two", "123", rows).entity_id)
        rows[0]["confidence"] = "HIGH"
        self.assertIsNone(resolve_identifier("official:one", "123", rows).entity_id)

    def test_conflicting_identifiers_are_unresolved(self):
        rows = [{"namespace": "n", "value": "v", "entity_id": x, "confidence": "EXACT"} for x in ("a", "b")]
        self.assertEqual(resolve_identifier("n", "v", rows).confidence, "UNRESOLVED")

    def test_invalid_source_url_rejected(self):
        for value in ("javascript:alert(1)", "https://user:password@example.com", "file:///tmp/source"):
            with self.assertRaises(ValueError):
                web_url(value)

    def test_retry_keeps_evidence_version_changed_fact_creates_new(self):
        args = dict(source_name="source", source_record_id="123", source_class="Official Registry",
                    source_url=None, source_locator={"file": "source.csv", "record_id": "123"},
                    title="Title", summary="fact", observed_at="2025-01-01T00:00:00Z", retrieved_at="2025-01-02T00:00:00Z")
        one = evidence_from_projection(**args)
        args["retrieved_at"] = datetime.now(timezone.utc).isoformat()
        self.assertEqual(one.id, evidence_from_projection(**args).id)
        args["summary"] = "corrected fact"
        self.assertNotEqual(one.id, evidence_from_projection(**args).id)

    def test_backfill_is_draft_with_no_private_raw_fields(self):
        bundle, report = build_legacy_bundle(snapshot())
        self.assertNotIn("PRIVATE", str(bundle))
        self.assertTrue(all(e["publication_status"] == "draft" for e in bundle["entities"]))
        self.assertTrue(all(r["status"] == "draft" for r in bundle["relationships"]))
        self.assertEqual(report["skipped"], [])

    def test_share_count_preserved_not_percentage(self):
        bundle, _ = build_legacy_bundle(snapshot())
        relationship = bundle["relationships"][0]
        self.assertEqual(relationship["quantity"], "1000")
        self.assertEqual(relationship["quantity_unit"], "shares")
        self.assertIsNone(relationship["percentage"])
        self.assertIsNone(relationship["start_date"])
        self.assertEqual(relationship["date_precision"], "unknown")

    def test_changed_holdings_create_new_evidence(self):
        data = snapshot()
        first, _ = build_legacy_bundle(data)
        data["company_people"][0]["share_count"] = 2000
        second, _ = build_legacy_bundle(data)
        self.assertNotEqual(first["relationships"][0]["id"], second["relationships"][0]["id"])

    def test_unmapped_role_is_reported_not_mislabeled(self):
        data = snapshot()
        data["company_people"][0]["role"] = "監察人"
        bundle, report = build_legacy_bundle(data)
        self.assertEqual(bundle["relationships"], [])
        self.assertEqual(len(report["skipped"]), 1)

    def test_missing_historical_timestamp_is_not_replaced_with_now(self):
        data = snapshot()
        data["company_people"][0]["fetched_at"] = None
        bundle, report = build_legacy_bundle(data)
        self.assertEqual(bundle["relationships"], [])
        self.assertEqual(len(report["skipped"]), 1)

    def test_relationship_validation(self):
        bundle, _ = build_legacy_bundle(snapshot())
        relationship = Relationship(**bundle["relationships"][0])
        for changes in ({"status": "published", "confidence": "LOW"},
                        {"primary_evidence_id": ""}, {"percentage": "101"},
                        {"amount": "NaN", "currency": "TWD"}, {"amount": "100"},
                        {"start_date": "2025-01-01", "end_date": "2024-01-01"}):
            with self.assertRaises(ValueError):
                replace(relationship, **changes)

    def test_unknown_entity_type_rejected(self):
        with self.assertRaises(ValueError):
            Entity(stable_id("e", "s", "1"), "Unknown", "n", "n", "s", "1")
