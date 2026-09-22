import unittest

from src.entities.resolution import (
    relationship_confidence_allowed,
    resolution_quality,
    resolve_entity_candidates,
)

SOURCE = "11111111-1111-4111-8111-111111111111"
CANDIDATE = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"
EVIDENCE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_EVIDENCE = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def observation(**updates):
    item = {"entity_id": SOURCE, "entity_type": "Person", "name": "王小明",
            "source": "company_registry", "evidence_id": EVIDENCE,
            "identifiers": [], "company_entity_ids": [], "roles": [],
            "start_date": None, "end_date": None}
    item.update(updates)
    return item


def candidate(**updates):
    item = {"entity_id": CANDIDATE, "entity_type": "Person", "name": "王小明",
            "source": "legislative_registry", "evidence_ids": [OTHER_EVIDENCE],
            "identifiers": [], "company_entity_ids": [], "roles": [],
            "start_date": None, "end_date": None}
    item.update(updates)
    return item


class EntityResolutionTests(unittest.TestCase):
    def test_exact_official_identifier_is_traceable(self):
        identifier = {"namespace": "tw:uniform_number", "value": "12345678",
                      "confidence": "EXACT"}
        result = resolve_entity_candidates(
            observation(entity_type="Company", identifiers=[identifier]),
            [candidate(entity_type="Company", identifiers=[identifier])])[0]
        self.assertEqual((result.confidence, result.score), ("EXACT", "1.00"))
        self.assertEqual(result.reason, "shared_exact_official_identifier")
        self.assertEqual(result.matching_evidence_ids, (EVIDENCE, OTHER_EVIDENCE))
        self.assertEqual(result.status, "pending")

    def test_ambiguous_or_conflicting_identifiers_never_resolve(self):
        identifier = {"namespace": "official:id", "value": "A", "confidence": "EXACT"}
        ambiguous = resolve_entity_candidates(
            observation(identifiers=[identifier]),
            [candidate(identifiers=[identifier]),
             candidate(entity_id=OTHER, identifiers=[identifier])])
        self.assertTrue(all(item.confidence == "UNRESOLVED" for item in ambiguous))
        conflict = resolve_entity_candidates(
            observation(identifiers=[identifier]),
            [candidate(identifiers=[{**identifier, "value": "B"}])])[0]
        self.assertEqual((conflict.confidence, conflict.score), ("UNRESOLVED", "0.00"))

    def test_same_name_alone_is_low_and_not_relationship_eligible(self):
        result = resolve_entity_candidates(observation(), [candidate()])[0]
        self.assertEqual(result.confidence, "LOW")
        self.assertFalse(relationship_confidence_allowed(result.confidence))
        self.assertTrue(result.signals["normalized_name_match"])

    def test_verified_company_role_and_time_context_can_be_high(self):
        source = observation(company_entity_ids=["company-1"], roles=["董事"],
                             start_date="2022-01-01", end_date="2024-12-31")
        match = candidate(company_entity_ids=["company-1"], roles=[" 董事 "],
                          start_date="2023-01-01", end_date="2025-12-31")
        result = resolve_entity_candidates(source, [match])[0]
        self.assertEqual(result.confidence, "HIGH")
        self.assertGreaterEqual(float(result.score), 0.75)
        self.assertTrue(relationship_confidence_allowed(result.confidence))

    def test_name_and_verified_company_context_is_medium_and_not_publishable(self):
        result = resolve_entity_candidates(
            observation(source="asset_declaration", company_entity_ids=["company-1"]),
            [candidate(source="asset_declaration", company_entity_ids=["company-1"])])[0]
        self.assertEqual((result.confidence, result.score), ("MEDIUM", "0.50"))
        self.assertFalse(relationship_confidence_allowed(result.confidence))

    def test_type_mismatch_is_unresolved_even_with_same_name_context(self):
        result = resolve_entity_candidates(
            observation(company_entity_ids=["company-1"], roles=["董事"]),
            [candidate(entity_type="Politician", company_entity_ids=["company-1"],
                       roles=["董事"])])[0]
        self.assertEqual(result.reason, "entity_type_mismatch")
        self.assertEqual(result.confidence, "UNRESOLVED")

    def test_labeled_quality_gate_has_perfect_precision_and_recall(self):
        identifier = {"namespace": "official:id", "value": "A", "confidence": "EXACT"}
        exact = resolve_entity_candidates(observation(identifiers=[identifier]),
                                          [candidate(identifiers=[identifier])])[0]
        high = resolve_entity_candidates(
            observation(company_entity_ids=["company-1"], roles=["董事"],
                        start_date="2022-01-01", end_date="2024-12-31"),
            [candidate(company_entity_ids=["company-1"], roles=["董事"],
                       start_date="2023-01-01", end_date="2025-12-31")])[0]
        name_only = resolve_entity_candidates(observation(), [candidate()])[0]
        medium = resolve_entity_candidates(
            observation(source="asset_declaration", company_entity_ids=["company-1"]),
            [candidate(source="asset_declaration", company_entity_ids=["company-1"])])[0]
        wrong_type = resolve_entity_candidates(
            observation(), [candidate(entity_type="Politician")])[0]
        sample = [{"confidence": item.confidence, "is_match": truth}
                  for item, truth in ((exact, True), (high, True),
                                      (medium, False), (name_only, False),
                                      (wrong_type, False))]
        quality = resolution_quality(sample)
        self.assertEqual(quality["sample_size"], 5)
        self.assertEqual((quality["precision"], quality["recall"]), (1.0, 1.0))


if __name__ == "__main__":
    unittest.main()
