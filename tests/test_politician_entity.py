import unittest
from unittest.mock import Mock

from app import dispatch
from src.entities.api import dispatch_entity_api
from src.entities.repository import EntityFeatureUnavailable, EntityRepository

POLITICIAN = "11111111-1111-4111-8111-111111111111"
PARTY = "22222222-2222-4222-8222-222222222222"
COMMITTEE = "33333333-3333-4333-8333-333333333333"
RELATIONSHIP = "44444444-4444-4444-8444-444444444444"
EVIDENCE = "55555555-5555-4555-8555-555555555555"


class PoliticianEntityTests(unittest.TestCase):
    def test_repository_returns_terms_and_classified_evidence_relationships(self):
        calls = []

        def get(table, params):
            calls.append((table, params))
            if table == "entities":
                return [{"id": POLITICIAN, "entity_type": "Politician", "display_name": "林委員"}]
            if table == "entity_evidence":
                return []
            if table == "politician_terms":
                return [{"id": RELATIONSHIP, "term_number": 11, "constituency": "測試選區",
                         "party": {"id": PARTY, "display_name": "測試黨"},
                         "primary_evidence": {"id": EVIDENCE, "source_name": "立法院"}}]
            self.assertEqual(table, "relationships")
            return [{"id": RELATIONSHIP, "source_entity_id": POLITICIAN,
                     "target_entity_id": COMMITTEE, "relationship_type": "COMMITTEE_MEMBER",
                     "source_entity": {"id": POLITICIAN, "entity_type": "Politician"},
                     "target_entity": {"id": COMMITTEE, "entity_type": "GovernmentAgency",
                                       "display_name": "內政委員會"},
                     "primary_evidence": {"id": EVIDENCE, "source_name": "立法院"}}]

        result = EntityRepository(transport=get).politician_profile(POLITICIAN)
        self.assertEqual(result["terms"][0]["term_number"], 11)
        self.assertEqual(result["committees"][0]["entity"]["display_name"], "內政委員會")
        self.assertTrue(result["schema_available"])
        relationship_calls = [params for table, params in calls if table == "relationships"]
        self.assertEqual(len(relationship_calls), 1)
        self.assertEqual(relationship_calls[0]["limit"], 26)
        self.assertIn("COMMITTEE_MEMBER", relationship_calls[0]["relationship_type"])

    def test_missing_additive_table_falls_back_to_existing_relationships(self):
        def get(table, params):
            if table == "entities":
                return [{"id": POLITICIAN, "entity_type": "Politician"}]
            if table == "entity_evidence":
                return []
            if table == "politician_terms":
                raise EntityFeatureUnavailable("not installed")
            if table == "relationships":
                return []
            self.fail(f"unexpected table {table}")

        result = EntityRepository(transport=get).politician_profile(POLITICIAN)
        self.assertFalse(result["schema_available"])
        self.assertEqual(result["terms"], [])

    def test_api_is_bounded_and_rejects_non_politician(self):
        repo = Mock()
        repo.politician_profile.return_value = {"entity": {"id": POLITICIAN}, "terms": []}
        code, body, _ = dispatch_entity_api(
            f"/api/v1/politicians/{POLITICIAN}", {"limit": ["25"]}, repo)
        self.assertEqual((code, body["api_version"]), (200, "1"))
        repo.politician_profile.assert_called_once_with(POLITICIAN, relationship_limit=25)
        self.assertEqual(dispatch_entity_api(
            f"/api/v1/politicians/{POLITICIAN}", {"limit": ["26"]}, repo)[0], 400)
        repo.politician_profile.return_value = None
        self.assertEqual(dispatch_entity_api(f"/api/v1/politicians/{POLITICIAN}", {}, repo)[0], 404)

    def test_shareable_politician_page_and_ui_fields_exist(self):
        code, body, content_type = dispatch(f"/politician/{POLITICIAN}", {})
        self.assertEqual(code, 200)
        self.assertIn("text/html", content_type)
        for token in ("/api/v1/politicians/", "politicianOverview", "政黨 / Party",
                      "選區 / Constituency", "委員會 · Committees", "共同提案 · Co-sponsored bills"):
            self.assertIn(token, body)


if __name__ == "__main__":
    unittest.main()
