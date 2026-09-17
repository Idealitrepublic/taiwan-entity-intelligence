import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from app import app
from src.watchlists import (
    WatchlistRepository,
    WatchlistValidationError,
    alert_payload,
    dispatch_watchlist_api,
    watchlist_payload,
)

ENTRY = "31313131-3131-4131-8131-313131313131"
ENTITY = "32323232-3232-4232-8232-323232323232"
ALERT = "33333333-3333-4333-8333-333333333330"
TOKEN = "authenticated-user-token-for-watchlist-tests"


class WatchlistTests(unittest.TestCase):
    def test_payloads_are_strict_and_bounded(self):
        self.assertEqual(watchlist_payload({"entity_id": ENTITY}), {"entity_id": ENTITY})
        self.assertIsNotNone(alert_payload({"read": True})["read_at"])
        self.assertIsNone(alert_payload({"read": False})["read_at"])
        for payload in ({}, {"entity_id": "bad"}, {"entity_id": ENTITY, "owner": "x"}):
            with self.assertRaises((WatchlistValidationError, ValueError)):
                watchlist_payload(payload)
        with self.assertRaises(WatchlistValidationError):
            alert_payload({"read": "yes"})

    def test_repository_queries_are_bounded_and_owner_is_never_set(self):
        calls = []

        def transport(method, resource, params, body):
            calls.append((method, resource, params, body))
            if resource == "watchlist_entries" and method == "GET":
                return [{"id": ENTRY}]
            if resource == "watchlist_events" and method == "GET":
                return []
            if resource.startswith("rpc/"):
                return {"inserted": 0, "watched": 1}
            return [{"id": ALERT, **(body or {})}]

        repository = WatchlistRepository(TOKEN, transport=transport)
        self.assertEqual(repository.list_entries()["items"][0]["id"], ENTRY)
        repository.add_entry({"entity_id": ENTITY})
        repository.list_alerts(state="unread", limit=20)
        repository.sync()
        self.assertEqual(calls[0][2]["limit"], 51)
        self.assertNotIn("owner_user_id", calls[1][3])
        self.assertEqual(calls[2][2]["read_at"], "is.null")
        self.assertEqual(calls[-1][3], {"scan_limit": 25})

    def test_repository_forwards_user_jwt_and_never_service_role(self):
        with patch.dict(os.environ, {
                "TEI_ENTITY_ANON_KEY": "public-key",
                "SUPABASE_SERVICE_ROLE_KEY": "do-not-use"}, clear=True):
            repository = WatchlistRepository(TOKEN)
            with patch("urllib.request.urlopen") as open_url:
                open_url.return_value.__enter__.return_value.read.return_value = b"[]"
                repository.list_entries()
                request = open_url.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), f"Bearer {TOKEN}")
        self.assertEqual(request.get_header("Apikey"), "public-key")
        self.assertNotIn("do-not-use", str(request.headers))
        self.assertEqual(parse_qs(urlsplit(request.full_url).query)["limit"], ["51"])

    def test_api_requires_auth_and_routes_watchlist_alert_actions(self):
        self.assertEqual(dispatch_watchlist_api(
            "GET", "/api/v1/watchlist", {}, None, None)[0], 401)
        repository = Mock()
        repository.list_entries.return_value = {"items": [], "has_more": False}
        code, body, _ = dispatch_watchlist_api(
            "GET", "/api/v1/watchlist", {}, None, f"Bearer {TOKEN}", repository)
        self.assertEqual((code, body["api_version"]), (200, "1"))
        repository.add_entry.return_value = {"id": ENTRY}
        self.assertEqual(dispatch_watchlist_api(
            "POST", "/api/v1/watchlist", {}, {"entity_id": ENTITY},
            f"Bearer {TOKEN}", repository)[0], 201)
        repository.mark_alert.return_value = {"id": ALERT, "read_at": "now"}
        self.assertEqual(dispatch_watchlist_api(
            "PATCH", f"/api/v1/alerts/{ALERT}", {}, {"read": True},
            f"Bearer {TOKEN}", repository)[0], 200)
        repository.mark_all_read.return_value = {"updated": 3}
        self.assertEqual(dispatch_watchlist_api(
            "POST", "/api/v1/alerts/read-all", {}, {},
            f"Bearer {TOKEN}", repository)[1]["data"]["updated"], 3)

    def test_wsgi_accepts_private_json_and_keeps_public_writes_denied(self):
        status = []
        payload = json.dumps({"entity_id": ENTITY}).encode()
        environ = {
            "REQUEST_METHOD": "POST", "PATH_INFO": "/api/v1/watchlist",
            "CONTENT_LENGTH": str(len(payload)), "wsgi.input": io.BytesIO(payload),
            "HTTP_AUTHORIZATION": f"Bearer {TOKEN}",
        }
        with patch("app.dispatch_watchlist_api", return_value=(201, {"ok": True}, None)):
            body = b"".join(app(environ, lambda value, _headers: status.append(value)))
        self.assertEqual(status, ["201 Created"])
        self.assertEqual(json.loads(body), {"ok": True})
        status.clear()
        app({"REQUEST_METHOD": "POST", "PATH_INFO": f"/api/v1/entities/{ENTITY}"},
            lambda value, _headers: status.append(value))
        self.assertEqual(status, ["405 Method Not Allowed"])

    def test_ui_has_dashboard_filters_and_read_state(self):
        html = (Path(__file__).parents[1] / "web" / "index.html").read_text()
        for token in ("watchlistOpen", "watchlistAdd", "/api/v1/watchlist/sync",
                      "alertState", "alertReadAll", "alert-toggle-read"):
            self.assertIn(token, html)


if __name__ == "__main__":
    unittest.main()
