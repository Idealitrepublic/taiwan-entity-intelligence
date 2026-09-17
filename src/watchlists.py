"""Authenticated, owner-scoped Watchlist and dashboard Alert API."""
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlencode

from src.entities.contracts import response
from src.entities.models import uuid_string
from src.public_config import SUPABASE_PUBLISHABLE_KEY
from src.workspaces import WorkspaceUnauthorized, access_token_from_header

WATCHLIST_FIELDS = (
    "id,owner_user_id,entity_id,created_at,"
    "entity:entities(id,entity_type,display_name,canonical_name)"
)
ALERT_FIELDS = (
    "id,watchlist_entry_id,owner_user_id,entity_id,event_type,source_kind,"
    "relationship_id,asset_declaration_id,evidence_id,event_observed_at,"
    "first_seen_at,read_at,entity:entities(id,entity_type,display_name,canonical_name),"
    "evidence:evidence_records(id,source_name,source_record_id,source_url,title,summary,"
    "observed_at,retrieved_at)"
)
ALERT_STATES = {"all", "unread", "read"}


class WatchlistStoreUnavailable(RuntimeError):
    pass


class WatchlistFeatureUnavailable(WatchlistStoreUnavailable):
    pass


class WatchlistUnauthorized(RuntimeError):
    pass


class WatchlistValidationError(ValueError):
    pass


def watchlist_payload(payload):
    if not isinstance(payload, dict) or set(payload) != {"entity_id"}:
        raise WatchlistValidationError("entity_id is required")
    return {"entity_id": uuid_string(payload["entity_id"])}


def alert_payload(payload):
    if not isinstance(payload, dict) or set(payload) != {"read"}:
        raise WatchlistValidationError("read is required")
    if not isinstance(payload["read"], bool):
        raise WatchlistValidationError("read must be boolean")
    return {"read_at": datetime.now(timezone.utc).isoformat() if payload["read"] else None}


def _first(query, name, default=None):
    value = (query or {}).get(name, [default])
    return value[0] if isinstance(value, list) else value


class WatchlistRepository:
    """PostgREST client forwarding only the signed-in user's JWT."""

    def __init__(self, access_token, transport=None):
        self.url = os.environ.get("TEI_ENTITY_SUPABASE_URL") or os.environ.get(
            "SUPABASE_URL", "https://rztdbdurkjfrirsrrhtu.supabase.co")
        self.key = os.environ.get("TEI_ENTITY_ANON_KEY") or os.environ.get("SUPABASE_ANON_KEY")
        if not self.key and self.url.rstrip("/") == "https://rztdbdurkjfrirsrrhtu.supabase.co":
            self.key = SUPABASE_PUBLISHABLE_KEY
        self.access_token = access_token
        self.transport = transport or self._request

    def _request(self, method, resource, params=None, body=None):
        if not self.key:
            raise WatchlistStoreUnavailable("Public API credential is not configured")
        query = f"?{urlencode(params or {})}" if params else ""
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        headers = {"apikey": self.key, "Authorization": f"Bearer {self.access_token}",
                   "Content-Type": "application/json", "Accept": "application/json"}
        if method != "GET":
            headers["Prefer"] = "return=representation"
        request = urllib.request.Request(
            f"{self.url.rstrip('/')}/rest/v1/{resource}{query}", data=data,
            headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=12) as result:
                raw = result.read()
                value = json.loads(raw) if raw else []
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise WatchlistUnauthorized("Session is not authorized") from exc
            if exc.code == 404:
                raise WatchlistFeatureUnavailable("Watchlist schema is not installed") from exc
            if exc.code in (400, 409, 422):
                raise WatchlistValidationError("Watchlist request was rejected") from exc
            raise WatchlistStoreUnavailable("Watchlist database unavailable") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise WatchlistStoreUnavailable("Watchlist database unavailable") from exc
        if not isinstance(value, (list, dict)):
            raise WatchlistStoreUnavailable("Unexpected watchlist database response")
        return value

    def list_entries(self):
        rows = self.transport("GET", "watchlist_entries", {
            "select": WATCHLIST_FIELDS, "order": "created_at.desc,id.asc", "limit": 51}, None)
        return {"items": rows[:50], "has_more": len(rows) > 50}

    def add_entry(self, payload):
        rows = self.transport("POST", "watchlist_entries", None, watchlist_payload(payload))
        return rows[0] if rows else None

    def delete_entry(self, entry_id):
        rows = self.transport("DELETE", "watchlist_entries", {
            "id": f"eq.{uuid_string(entry_id)}"}, None)
        return rows[0] if rows else None

    def sync(self):
        value = self.transport("POST", "rpc/sync_watchlist_events", None, {"scan_limit": 25})
        if isinstance(value, list):
            return value[0] if value else None
        return value

    def list_alerts(self, *, state="all", limit=50):
        if state not in ALERT_STATES or not 1 <= limit <= 50:
            raise WatchlistValidationError("Invalid alert filters")
        params = {"select": ALERT_FIELDS, "order": "first_seen_at.desc,id.asc",
                  "limit": limit + 1}
        if state == "unread":
            params["read_at"] = "is.null"
        elif state == "read":
            params["read_at"] = "not.is.null"
        rows = self.transport("GET", "watchlist_events", params, None)
        unread = self.transport("GET", "watchlist_events", {
            "select": "id", "read_at": "is.null", "order": "first_seen_at.desc,id.asc",
            "limit": 101}, None)
        return {"items": rows[:limit], "has_more": len(rows) > limit,
                "unread_count": min(len(unread), 100), "unread_count_capped": len(unread) > 100}

    def mark_alert(self, alert_id, payload):
        rows = self.transport("PATCH", "watchlist_events", {
            "id": f"eq.{uuid_string(alert_id)}"}, alert_payload(payload))
        return rows[0] if rows else None

    def mark_all_read(self):
        rows = self.transport("PATCH", "watchlist_events", {"read_at": "is.null"}, {
            "read_at": datetime.now(timezone.utc).isoformat()})
        return {"updated": len(rows)}


def dispatch_watchlist_api(method, path, query, payload, authorization, repository=None):
    """Dispatch bounded Watchlist/Alert operations; RLS remains authoritative."""
    try:
        token = access_token_from_header(authorization)
        repository = repository or WatchlistRepository(token)
        parts = path.strip("/").split("/")
        result = None
        if parts == ["api", "v1", "watchlist"]:
            if method == "GET":
                result = repository.list_entries()
            elif method == "POST":
                result = repository.add_entry(payload)
            else:
                return 405, {"error": "Method not allowed"}, None
        elif parts == ["api", "v1", "watchlist", "sync"] and method == "POST":
            result = repository.sync()
        elif len(parts) == 4 and parts[:3] == ["api", "v1", "watchlist"]:
            if method != "DELETE":
                return 405, {"error": "Method not allowed"}, None
            result = repository.delete_entry(parts[3])
        elif parts == ["api", "v1", "alerts"] and method == "GET":
            state = str(_first(query, "state", "all") or "all")
            limit = int(_first(query, "limit", "50"))
            result = repository.list_alerts(state=state, limit=limit)
        elif parts == ["api", "v1", "alerts", "read-all"] and method == "POST":
            result = repository.mark_all_read()
        elif len(parts) == 4 and parts[:3] == ["api", "v1", "alerts"]:
            if method != "PATCH":
                return 405, {"error": "Method not allowed"}, None
            result = repository.mark_alert(parts[3], payload)
        else:
            return 404, {"error": "Not found / 找不到端點"}, None
    except (WatchlistUnauthorized, WorkspaceUnauthorized):
        return 401, {"error": "請登入後使用 Watchlist / Authentication required"}, None
    except (WatchlistValidationError, ValueError, TypeError):
        return 400, {"error": "Watchlist 輸入格式錯誤 / Invalid input"}, None
    except WatchlistFeatureUnavailable:
        return 503, {"status": "not_enabled", "schema_available": False,
                     "error": "Watchlist schema 尚未部署 / Schema unavailable"}, None
    except WatchlistStoreUnavailable:
        return 503, {"status": "unavailable",
                     "error": "Watchlist 暫時無法使用 / Watchlist unavailable"}, None
    if result is None:
        return 404, {"error": "找不到項目，或不屬於目前使用者 / Not found"}, None
    return (201 if method == "POST" and parts == ["api", "v1", "watchlist"] else 200), response(result), None
