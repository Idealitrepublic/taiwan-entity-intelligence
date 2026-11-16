"""Exercise the first public release through the same API entrypoint as visitors."""
import unittest
from unittest.mock import Mock, patch

from app import dispatch
from src import cloud_company
from src.entities.models import stable_id
from src.entities.repository import EntityRepository, EntityStoreUnavailable
from src.sources.procurement import lookup_reviewed_awards

ID = "00000000-0000-4000-8000-000000000001"
UNIFORM = "96979933"


class PublicGraphLaunchTests(unittest.TestCase):
    def test_company_returns_registry_roles_and_lookup_links_only(self):
        data = [{"Business_Accounting_NO": UNIFORM, "Company_Name": "公司"}]
        officers = [{"Person_Name": "公開職務範例", "Person_Position_Name": "董事"}]
        with (patch.object(cloud_company, "_moea_rows", side_effect=[data, officers]),
              patch.object(cloud_company, "_supabase_evidence", side_effect=AssertionError),
              patch.object(cloud_company, "indexed_records", side_effect=AssertionError),
              patch.object(cloud_company, "records_for_company", side_effect=AssertionError),
              patch.object(cloud_company, "check_domain", side_effect=AssertionError)):
            status, payload, _ = dispatch(f"/api/company/{UNIFORM}", {})
        self.assertEqual(status, 200)
        self.assertTrue(payload["public_graph_scope"])
        self.assertEqual([node["type"] for node in payload["graph"]["nodes"]], ["company", "person"])
        proof = payload["graph"]["edges"][0]["evidence"]
        self.assertTrue(proof["source_locator"].startswith(f"Business_Accounting_NO={UNIFORM};"))
        self.assertEqual(payload["evidence_status"]["裁罰"]["url"], "https://announcement.mol.gov.tw/")
        self.assertEqual(payload["evidence_status"]["司法院"]["url"], "https://judgment.judicial.gov.tw/")
        self.assertFalse({"judicial_records", "labor_penalties", "website_crosscheck"} & payload.keys())

    def test_signed_off_scope_is_required_before_canonical_data_queries(self):
        repository = EntityRepository(require_launch_scope=True)
        repository._request = Mock(return_value=[])
        with self.assertRaises(EntityStoreUnavailable):
            repository.entity(ID)
        repository._request.assert_called_once_with("rpc/public_graph_scope_version", {})

    def test_public_live_path_does_not_load_court_index(self):
        first = stable_id("entity", "tw:uniform_number", UNIFORM)
        second = stable_id("entity", "tw:uniform_number", "04690983")
        data = {"source": [first], "target": [second], "source_uniform": [UNIFORM],
                "target_uniform": ["04690983"], "company_only": ["1"], "live": ["1"]}
        with patch("src.entities.api.live_company_path", return_value={"found": False}) as lookup:
            self.assertEqual(dispatch("/api/v1/paths", data)[0], 200)
        lookup.assert_called_once_with(UNIFORM, "04690983", max_depth=3, public_graph_only=True)

    def test_public_forbidden_filters_are_disabled(self):
        self.assertEqual(dispatch("/api/v1/search", {"q": ["台灣"], "entity_type": ["Judgment"]})[0], 400)
        self.assertEqual(dispatch(f"/api/v1/graph/{ID}", {"relationship_type": ["RELATED_TO_PENALTY"]})[0], 400)
        self.assertEqual(dispatch(f"/api/v1/entities/{ID}/political-contributions", {})[0], 404)
        self.assertEqual(dispatch("/api/domain-check", {"domain": ["example.com"]})[0], 404)

    def test_award_requires_official_notice_role_exact_uniform_and_identifier(self):
        source = {"bidder_uniform_number": UNIFORM, "winner": True,
                  "review_method": "official_row_compared_with_exact_bidder_id_and_award_role",
                  "unit_id": "U", "job_number": "J", "notice_filename": "N", "award_date": "2026-11-10"}
        proof = {"source_locator": source, "source_url": "https://web.pcc.gov.tw/review"}
        edge = {"source_entity_id": ID, "relationship_type": "CONTRACT_WITH", "primary_evidence": proof}
        with patch("src.entities.repository.EntityRepository") as factory:
            db = factory.return_value
            db.company_for_uniform.return_value = {"id": ID}
            db.graph_neighbors.return_value = {"edges": [edge, {**edge, "primary_evidence":
                {**proof, "source_url": "https://web.pcc.gov.tw.evil.example/review"}}], "has_more": False}
            result = lookup_reviewed_awards(UNIFORM)
        factory.assert_called_once_with(require_launch_scope=True)
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["records"][0]["id"], "U:J:N")
        self.assertEqual(result["records"][0]["publication_status"], "published")
