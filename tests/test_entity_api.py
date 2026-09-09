import json
import os
import unittest
from unittest.mock import patch, Mock
from urllib.parse import parse_qs, urlsplit

from app import app
from src.entities.api import dispatch_entity_api
from src.entities.repository import EntityRepository, EntityStoreUnavailable

ID = "11111111-1111-4111-8111-111111111111"


class EntityApiTests(unittest.TestCase):
    def test_invalid_id_is_rejected_before_network(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            code, _, _ = dispatch_entity_api("/api/v1/entities/not-a-uuid", {})
        self.assertEqual(code, 400)

    def test_emergency_feature_flag_disables_api(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.dict(os.environ, {"TEI_ENTITY_API_ENABLED": "0"}):
                self.assertEqual(dispatch_entity_api(f"/api/v1/entities/{ID}", {})[0], 503)

    def test_enabled_profile_and_missing_record(self):
        repo = Mock()
        with patch.dict(os.environ, {}, clear=True):
            repo.entity.return_value = {"id": ID, "display_name": "測試公司"}
            code, body, _ = dispatch_entity_api(f"/api/v1/entities/{ID}", {}, repo)
            self.assertEqual(code, 200)
            self.assertEqual(body["data"]["id"], ID)
            repo.entity.return_value = None
            self.assertEqual(dispatch_entity_api(f"/api/v1/entities/{ID}", {}, repo)[0], 404)

    def test_unavailable_is_not_an_empty_success(self):
        repo = Mock()
        repo.entity.side_effect = EntityStoreUnavailable("secret details")
        with patch.dict(os.environ, {}, clear=True):
            code, body, _ = dispatch_entity_api(f"/api/v1/entities/{ID}", {}, repo)
        self.assertEqual(code, 503)
        self.assertNotIn("secret", str(body))

    def test_limits_and_filters_are_validated(self):
        for query in ({"limit": ["0"]}, {"limit": ["51"]}, {"limit": ["abc"]},
                      {"after": ["bad"]}, {"relationship_type": ["ARBITRARY"]}):
            self.assertEqual(dispatch_entity_api(f"/api/v1/entities/{ID}/relationships", query)[0], 400)

    def test_relationship_pages_are_bounded_and_ordered(self):
        calls = []
        def get(table, params):
            calls.append((table, params))
            return [{"id": str(i)} for i in range(3)]
        repo = EntityRepository(transport=get)
        page = repo.relationships(ID, limit=2, relationship_type="DIRECTOR_OF", after=ID)
        self.assertEqual(len(page["items"]), 2)
        self.assertEqual(page["next_cursor"], "1")
        self.assertTrue(page["has_more"])
        self.assertEqual(calls[0][1]["limit"], 3)
        self.assertEqual(calls[0][1]["id"], f"gt.{ID}")
        self.assertEqual(calls[0][1]["relationship_type"], "eq.DIRECTOR_OF")

    def test_read_key_never_uses_service_role(self):
        with patch.dict(os.environ, {"SUPABASE_SERVICE_ROLE_KEY": "DO_NOT_USE", "TEI_ENTITY_ANON_KEY": "public-test"}, clear=True):
            repo = EntityRepository()
            with patch("urllib.request.urlopen") as open_url:
                open_url.return_value.__enter__.return_value.read.return_value = b"[]"
                repo.evidence(ID)
                request = open_url.call_args.args[0]
                self.assertEqual(request.get_header("Authorization"), "Bearer public-test")
                self.assertNotIn("DO_NOT_USE", str(request.headers))
                params = parse_qs(urlsplit(request.full_url).query)
                self.assertNotIn("raw", params["select"][0])

    def test_retracted_primary_evidence_hides_relationship(self):
        def get(table, params):
            if table == "relationships":
                return [{"id": ID, "primary_evidence_id": ID}]
            return []
        self.assertIsNone(EntityRepository(transport=get).relationship(ID))

    def test_old_company_response_remains_identical(self):
        payload = {"status": "ok", "company_name": "公司", "nodes": [], "edges": [], "evidence_status": {}}
        with patch("app.core.build_company", return_value=payload):
            status = []
            body = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/api/company/12345678"},
                                lambda s, h: status.append(s)))
        self.assertEqual(json.loads(body), payload)
        self.assertEqual(status, ["200 OK"])

    def test_new_routes_are_read_only(self):
        status = []
        body = b"".join(app({"REQUEST_METHOD": "POST", "PATH_INFO": f"/api/v1/entities/{ID}"},
                            lambda s, h: status.append(s)))
        self.assertEqual(status, ["405 Method Not Allowed"])
        self.assertIn(b"Method not allowed", body)
