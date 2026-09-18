import unittest
from pathlib import Path
from unittest.mock import Mock

from src.entities.api import dispatch_entity_api
from src.entities.repository import EntityFeatureUnavailable, EntityRepository
from src.political_contributions import build_political_contribution_bundle

COMPANY = "11111111-1111-4111-8111-111111111111"
POLITICIAN = "22222222-2222-4222-8222-222222222222"
RELATIONSHIP = "33333333-3333-4333-8333-333333333333"
EVIDENCE = "44444444-4444-4444-8444-444444444444"


def source_row(**updates):
    row = {
        "source_record_id": "112-legislator-A-0001",
        "filing_id": "112-legislator-A",
        "politician_source_id": "legislator-001",
        "donor_uniform_number": "１２３４５６７８",
        "amount": "120,000",
        "date": "2024-01-15",
        "contribution_type": "營利事業捐贈",
        "source_url": "https://ardata.cy.gov.tw/data/search/advanced",
    }
    row.update(updates)
    return row


def entities():
    return ({"id": COMPANY, "entity_type": "Company", "display_name": "測試公司"},
            {"id": POLITICIAN, "entity_type": "Politician", "display_name": "林立委"})


def rpc_row(extra=False):
    company, politician = entities()
    relationship = {
        "id": RELATIONSHIP if not extra else "55555555-5555-4555-8555-555555555555",
        "source_entity_id": COMPANY, "target_entity_id": POLITICIAN,
        "relationship_type": "POLITICAL_CONTRIBUTION_TO",
        "primary_evidence_id": EVIDENCE, "amount": 120000, "currency": "TWD",
        "start_date": "2024-01-15", "source_role": "營利事業捐贈",
    }
    evidence = {"id": EVIDENCE, "source_record_id": "112-legislator-A-0001",
                "source_url": "https://ardata.cy.gov.tw/data/search/advanced",
                "source_locator": {"match_method": "exact_uniform_number"}}
    return {"focus_entity": company, "relationship": relationship,
            "company_entity": company, "politician_entity": politician,
            "primary_evidence": evidence}


class PoliticalContributionTests(unittest.TestCase):
    def test_adapter_exactly_matches_full_width_uniform_and_preserves_source(self):
        company, politician = entities()
        bundle, report = build_political_contribution_bundle(
            [source_row()], companies_by_uniform={"12345678": company},
            politicians_by_source_id={"legislator-001": politician},
            retrieved_at="2026-09-16T10:00:00+08:00")
        self.assertEqual(report["counts"]["relationships"], 1)
        edge = bundle["relationships"][0]
        proof = bundle["evidence"][0]
        self.assertEqual((edge["source_entity_id"], edge["target_entity_id"]),
                         (COMPANY, POLITICIAN))
        self.assertEqual((edge["amount"], edge["currency"]), ("120000", "TWD"))
        self.assertEqual((edge["start_date"], edge["date_precision"]), ("2024-01-15", "day"))
        self.assertEqual(edge["source_role"], "營利事業捐贈")
        self.assertEqual(edge["status"], "draft")
        self.assertEqual(proof["source_record_id"], "112-legislator-A-0001")
        self.assertEqual(proof["source_locator"]["match_method"], "exact_uniform_number")
        self.assertEqual(proof["source_locator"]["uniform_number"], "12345678")
        self.assertEqual(proof["source_url"], "https://ardata.cy.gov.tw/data/search/advanced")

    def test_adapter_never_name_matches_or_auto_publishes(self):
        company, politician = entities()
        rows = [source_row(donor_uniform_number="", donor_name="測試公司"),
                source_row(source_record_id="second", donor_uniform_number="87654321")]
        bundle, report = build_political_contribution_bundle(
            rows, companies_by_uniform={"12345678": company},
            politicians_by_source_id={"legislator-001": politician},
            retrieved_at="2026-09-16T10:00:00+08:00")
        self.assertEqual(bundle["relationships"], [])
        self.assertEqual(len(report["skipped"]), 2)
        self.assertEqual(report["publication_status"], "draft")

    def test_adapter_is_deterministic_and_rejects_invalid_amount_or_date(self):
        company, politician = entities()
        kwargs = {"companies_by_uniform": {"12345678": company},
                  "politicians_by_source_id": {"legislator-001": politician},
                  "retrieved_at": "2026-09-16T10:00:00+08:00"}
        first = build_political_contribution_bundle([source_row()], **kwargs)[0]
        second = build_political_contribution_bundle([source_row()], **kwargs)[0]
        self.assertEqual(first["relationships"][0]["id"], second["relationships"][0]["id"])
        invalid, report = build_political_contribution_bundle(
            [source_row(amount="NaN"), source_row(source_record_id="bad-date", date="2024/01/15")],
            **kwargs)
        self.assertEqual(invalid["relationships"], [])
        self.assertEqual(len(report["skipped"]), 2)

    def test_repository_uses_one_bounded_rpc_and_projects_public_fields(self):
        calls = []

        def get(table, params):
            calls.append((table, params))
            return [rpc_row(), rpc_row(extra=True)]

        page = EntityRepository(transport=get).political_contributions(
            COMPANY, limit=1, after=RELATIONSHIP)
        self.assertEqual(calls, [("rpc/political_contributions_for_entity", {
            "focus_entity_id": COMPANY, "result_limit": 1,
            "after_relationship_id": RELATIONSHIP})])
        self.assertTrue(page["has_more"])
        self.assertEqual(page["next_cursor"], RELATIONSHIP)
        self.assertEqual(page["items"][0]["company"]["id"], COMPANY)
        self.assertEqual(page["items"][0]["politician"]["id"], POLITICIAN)
        self.assertEqual(page["items"][0]["contribution_type"], "營利事業捐贈")
        self.assertEqual(page["items"][0]["source_record"]["id"], "112-legislator-A-0001")

    def test_repository_has_bounded_backward_compatible_fallback(self):
        calls = []

        def get(table, params):
            calls.append((table, params))
            if table == "rpc/political_contributions_for_entity":
                raise EntityFeatureUnavailable("old schema")
            if table == "entities":
                return [entities()[0]]
            exact = rpc_row()
            relationship = {**exact["relationship"],
                            "company_entity": exact["company_entity"],
                            "politician_entity": exact["politician_entity"],
                            "primary_evidence": exact["primary_evidence"]}
            fuzzy = {**relationship, "id": "55555555-5555-4555-8555-555555555555",
                     "primary_evidence": {**exact["primary_evidence"],
                                          "source_locator": {"match_method": "name"}}}
            return [relationship, fuzzy]

        page = EntityRepository(transport=get).political_contributions(COMPANY, limit=2)
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(calls[-1][1]["limit"], 3)
        self.assertEqual(calls[-1][1]["relationship_type"],
                         "eq.POLITICAL_CONTRIBUTION_TO")

    def test_api_validates_limit_cursor_and_returns_v1_envelope(self):
        repo = Mock()
        repo.political_contributions.return_value = {"items": [], "has_more": False}
        path = f"/api/v1/entities/{COMPANY}/political-contributions"
        code, body, _ = dispatch_entity_api(path, {"limit": ["25"]}, repo)
        self.assertEqual((code, body["api_version"]), (200, "1"))
        repo.political_contributions.assert_called_once_with(COMPANY, limit=25, after=None)
        for query in ({"limit": ["0"]}, {"limit": ["26"]}, {"after": ["bad"]}):
            self.assertEqual(dispatch_entity_api(path, query, repo)[0], 400)
        repo.political_contributions.return_value = None
        self.assertEqual(dispatch_entity_api(path, {}, repo)[0], 404)

    def test_company_and_politician_pages_expose_bidirectional_contributions(self):
        html = (Path(__file__).parents[1] / "web" / "index.html").read_text()
        for token in ("/political-contributions", "politicalContributionCards",
                      "政治獻金 / Political contributions", "source_record",
                      "exact_uniform_number"):
            self.assertIn(token, html)


if __name__ == "__main__":
    unittest.main()
