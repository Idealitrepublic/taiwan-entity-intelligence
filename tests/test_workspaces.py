import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from app import app
from src.workspaces import (
    WorkspaceRepository,
    WorkspaceValidationError,
    dispatch_workspace_api,
    workspace_item_payload,
)

WORKSPACE = "11111111-1111-4111-8111-111111111111"
ITEM = "22222222-2222-4222-8222-222222222222"
TOKEN = "authenticated-user-token-for-tests"


class WorkspaceTests(unittest.TestCase):
    def test_all_supported_item_types_are_strictly_validated(self):
        fixtures = {
            "ENTITY": {"entity_id": ITEM},
            "RELATIONSHIP": {"relationship_id": ITEM},
            "EVIDENCE": {"evidence_id": ITEM},
            "GRAPH": {"graph_root_entity_id": ITEM},
            "SOURCE": {"source_url": "https://example.gov.tw/record"},
            "NOTE": {"note_text": "待核對來源"},
        }
        for item_type, reference in fixtures.items():
            parsed = workspace_item_payload({"item_type": item_type, **reference})
            self.assertEqual(parsed["item_type"], item_type)
        with self.assertRaises(WorkspaceValidationError):
            workspace_item_payload({"item_type": "ENTITY", "entity_id": ITEM,
                                    "evidence_id": ITEM})
        with self.assertRaises(WorkspaceValidationError):
            workspace_item_payload({"item_type": "SOURCE", "source_url": "javascript:x"})

    def test_repository_reads_are_bounded_and_mutations_do_not_set_owner(self):
        calls = []

        def transport(method, table, params, body):
            calls.append((method, table, params, body))
            if method == "GET" and table == "investigation_workspaces":
                return [{"id": WORKSPACE, "name": "測試"}]
            return [{"id": ITEM, **(body or {})}]

        repository = WorkspaceRepository(TOKEN, transport=transport)
        result = repository.list()
        self.assertEqual(result["items"][0]["id"], WORKSPACE)
        self.assertEqual(calls[0][2]["limit"], 51)
        repository.create({"name": "調查專案"})
        repository.add_item(WORKSPACE, {"item_type": "NOTE", "note_text": "註記"})
        self.assertNotIn("owner_user_id", calls[1][3])
        self.assertNotIn("created_by_user_id", calls[2][3])

    def test_repository_forwards_user_jwt_and_never_service_role(self):
        with patch.dict(os.environ, {
                "TEI_ENTITY_ANON_KEY": "public-key",
                "SUPABASE_SERVICE_ROLE_KEY": "do-not-use"}, clear=True):
            repository = WorkspaceRepository(TOKEN)
            with patch("urllib.request.urlopen") as open_url:
                open_url.return_value.__enter__.return_value.read.return_value = b"[]"
                repository.list()
                request = open_url.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), f"Bearer {TOKEN}")
        self.assertEqual(request.get_header("Apikey"), "public-key")
        self.assertNotIn("do-not-use", str(request.headers))
        self.assertEqual(parse_qs(urlsplit(request.full_url).query)["limit"], ["51"])

    def test_api_requires_auth_and_routes_crud(self):
        self.assertEqual(dispatch_workspace_api(
            "GET", "/api/v1/workspaces", None, None)[0], 401)
        repository = Mock()
        repository.list.return_value = {"items": [], "has_more": False}
        code, body, _ = dispatch_workspace_api(
            "GET", "/api/v1/workspaces", None, f"Bearer {TOKEN}", repository)
        self.assertEqual((code, body["api_version"]), (200, "1"))
        repository.create.return_value = {"id": WORKSPACE}
        self.assertEqual(dispatch_workspace_api(
            "POST", "/api/v1/workspaces", {"name": "專案"},
            f"Bearer {TOKEN}", repository)[0], 201)
        repository.delete_item.return_value = {"id": ITEM}
        path = f"/api/v1/workspaces/{WORKSPACE}/items/{ITEM}"
        self.assertEqual(dispatch_workspace_api(
            "DELETE", path, None, f"Bearer {TOKEN}", repository)[0], 200)

    def test_wsgi_accepts_bounded_json_and_keeps_legacy_writes_denied(self):
        status = []
        payload = json.dumps({"name": "專案"}).encode()
        environ = {
            "REQUEST_METHOD": "POST", "PATH_INFO": "/api/v1/workspaces",
            "CONTENT_LENGTH": str(len(payload)), "wsgi.input": io.BytesIO(payload),
            "HTTP_AUTHORIZATION": f"Bearer {TOKEN}",
        }
        with patch("app.dispatch_workspace_api", return_value=(201, {"ok": True}, None)):
            body = b"".join(app(environ, lambda value, _headers: status.append(value)))
        self.assertEqual(status, ["201 Created"])
        self.assertEqual(json.loads(body), {"ok": True})
        status.clear()
        app({"REQUEST_METHOD": "POST", "PATH_INFO": f"/api/v1/entities/{ITEM}"},
            lambda value, _headers: status.append(value))
        self.assertEqual(status, ["405 Method Not Allowed"])

    def test_public_auth_config_never_exposes_service_role(self):
        status = []
        with patch.dict(os.environ, {
                "TEI_ENTITY_ANON_KEY": "browser-safe-key",
                "SUPABASE_SERVICE_ROLE_KEY": "do-not-expose"}, clear=True):
            body = b"".join(app({"REQUEST_METHOD": "GET",
                                 "PATH_INFO": "/api/v1/workspace-config"},
                                lambda value, _headers: status.append(value)))
        result = json.loads(body)
        self.assertEqual(status, ["200 OK"])
        self.assertEqual(result["publishable_key"], "browser-safe-key")
        self.assertNotIn("do-not-expose", str(result))

    def test_ui_has_auth_crud_and_six_bookmark_types(self):
        html = (Path(__file__).parents[1] / "web" / "index.html").read_text()
        for token in ("workspaceOpen", "workspaceLogin", "/api/v1/workspaces",
                      "ENTITY", "RELATIONSHIP", "EVIDENCE", "GRAPH", "SOURCE", "NOTE"):
            self.assertIn(token, html)


if __name__ == "__main__":
    unittest.main()
