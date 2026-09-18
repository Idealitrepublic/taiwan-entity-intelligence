"""Authenticated, owner-scoped Investigation Workspace API."""
import json
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlsplit

from src.entities.contracts import response
from src.entities.models import uuid_string
from src.runtime_config import private_supabase_config

WORKSPACE_FIELDS = "id,owner_user_id,name,description,created_at,updated_at"
WORKSPACE_ITEM_FIELDS = (
    "id,workspace_id,owner_user_id,created_by_user_id,item_type,entity_id,relationship_id,"
    "evidence_id,graph_root_entity_id,source_url,title,note_text,metadata,created_at,updated_at"
)
ITEM_TYPES = {"ENTITY", "RELATIONSHIP", "EVIDENCE", "GRAPH", "SOURCE", "NOTE"}
ITEM_REFERENCE_FIELDS = {
    "ENTITY": "entity_id",
    "RELATIONSHIP": "relationship_id",
    "EVIDENCE": "evidence_id",
    "GRAPH": "graph_root_entity_id",
    "SOURCE": "source_url",
    "NOTE": "note_text",
}


class WorkspaceStoreUnavailable(RuntimeError):
    pass


class WorkspaceFeatureUnavailable(WorkspaceStoreUnavailable):
    pass


class WorkspaceUnauthorized(RuntimeError):
    pass


class WorkspaceValidationError(ValueError):
    pass


def access_token_from_header(header):
    if not isinstance(header, str) or not header.startswith("Bearer "):
        raise WorkspaceUnauthorized("Authentication required")
    token = header[7:].strip()
    if not 20 <= len(token) <= 4096:
        raise WorkspaceUnauthorized("Invalid access token")
    return token


def _text(value, name, *, maximum, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise WorkspaceValidationError(f"{name} must be text")
    cleaned = value.strip()
    if (required and not cleaned) or len(cleaned) > maximum:
        raise WorkspaceValidationError(f"Invalid {name}")
    return cleaned or None


def _metadata(value):
    if value is None:
        return {}
    if not isinstance(value, dict) or len(json.dumps(value, ensure_ascii=False)) > 8192:
        raise WorkspaceValidationError("Invalid metadata")
    return value


def workspace_payload(payload, *, partial=False):
    if not isinstance(payload, dict):
        raise WorkspaceValidationError("JSON object required")
    allowed = {"name", "description"}
    if set(payload) - allowed or (not partial and "name" not in payload) or not payload:
        raise WorkspaceValidationError("Invalid workspace fields")
    result = {}
    if "name" in payload:
        result["name"] = _text(payload["name"], "name", maximum=120, required=True)
    if "description" in payload:
        result["description"] = _text(payload["description"], "description", maximum=2000)
    return result


def workspace_item_payload(payload, *, partial=False):
    if not isinstance(payload, dict):
        raise WorkspaceValidationError("JSON object required")
    mutable = {"title", "note_text", "metadata"}
    if partial:
        if not payload or set(payload) - mutable:
            raise WorkspaceValidationError("Invalid item update fields")
        result = {}
        if "title" in payload:
            result["title"] = _text(payload["title"], "title", maximum=500)
        if "note_text" in payload:
            result["note_text"] = _text(
                payload["note_text"], "note", maximum=10000, required=True)
        if "metadata" in payload:
            result["metadata"] = _metadata(payload["metadata"])
        return result
    allowed = {"item_type", *ITEM_REFERENCE_FIELDS.values(), *mutable}
    if set(payload) - allowed:
        raise WorkspaceValidationError("Invalid item fields")
    item_type = str(payload.get("item_type") or "").upper()
    if item_type not in ITEM_TYPES:
        raise WorkspaceValidationError("Invalid item type")
    reference_field = ITEM_REFERENCE_FIELDS[item_type]
    result = {"item_type": item_type, "metadata": _metadata(payload.get("metadata"))}
    for field in ("entity_id", "relationship_id", "evidence_id", "graph_root_entity_id"):
        value = payload.get(field)
        if field == reference_field:
            result[field] = uuid_string(value)
        elif value is not None:
            raise WorkspaceValidationError("Item has incompatible references")
    if item_type == "SOURCE":
        source_url = _text(payload.get("source_url"), "source URL", maximum=2048, required=True)
        parsed_url = urlsplit(source_url)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            raise WorkspaceValidationError("Invalid source URL")
        result["source_url"] = source_url
    elif payload.get("source_url") is not None:
        raise WorkspaceValidationError("Item has incompatible source URL")
    if item_type == "NOTE":
        result["note_text"] = _text(
            payload.get("note_text"), "note", maximum=10000, required=True)
    elif payload.get("note_text") is not None:
        raise WorkspaceValidationError("Item has incompatible note")
    if payload.get("title") is not None:
        result["title"] = _text(payload["title"], "title", maximum=500)
    return result


class WorkspaceRepository:
    """PostgREST client that forwards a user JWT and relies on owner RLS."""

    def __init__(self, access_token, transport=None):
        self.url, self.key = private_supabase_config()
        self.access_token = access_token
        self.transport = transport or self._request

    def _request(self, method, table, params=None, body=None):
        if not self.key:
            raise WorkspaceStoreUnavailable("Public API credential is not configured")
        query = f"?{urlencode(params or {})}" if params else ""
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        headers = {"apikey": self.key, "Authorization": f"Bearer {self.access_token}",
                   "Content-Type": "application/json", "Accept": "application/json"}
        if method != "GET":
            headers["Prefer"] = "return=representation"
        request = urllib.request.Request(
            f"{self.url.rstrip('/')}/rest/v1/{table}{query}", data=data,
            headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=12) as result:
                raw = result.read()
                rows = json.loads(raw) if raw else []
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise WorkspaceUnauthorized("Session is not authorized") from exc
            if exc.code == 404:
                raise WorkspaceFeatureUnavailable("Workspace schema is not installed") from exc
            if exc.code in (400, 409, 422):
                raise WorkspaceValidationError("Workspace request was rejected") from exc
            raise WorkspaceStoreUnavailable("Workspace database unavailable") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise WorkspaceStoreUnavailable("Workspace database unavailable") from exc
        if not isinstance(rows, list):
            raise WorkspaceStoreUnavailable("Unexpected workspace database response")
        return rows

    def list(self):
        rows = self.transport("GET", "investigation_workspaces", {
            "select": WORKSPACE_FIELDS, "order": "updated_at.desc,id.asc", "limit": 51}, None)
        return {"items": rows[:50], "has_more": len(rows) > 50}

    def get(self, workspace_id):
        workspace_id = uuid_string(workspace_id)
        workspaces = self.transport("GET", "investigation_workspaces", {
            "select": WORKSPACE_FIELDS, "id": f"eq.{workspace_id}", "limit": 1}, None)
        if not workspaces:
            return None
        items = self.transport("GET", "workspace_items", {
            "select": WORKSPACE_ITEM_FIELDS, "workspace_id": f"eq.{workspace_id}",
            "order": "created_at.desc,id.asc", "limit": 201}, None)
        return {**workspaces[0], "items": items[:200], "items_has_more": len(items) > 200}

    def create(self, payload):
        rows = self.transport("POST", "investigation_workspaces", None,
                              workspace_payload(payload))
        return rows[0] if rows else None

    def update(self, workspace_id, payload):
        rows = self.transport("PATCH", "investigation_workspaces", {
            "id": f"eq.{uuid_string(workspace_id)}"}, workspace_payload(payload, partial=True))
        return rows[0] if rows else None

    def delete(self, workspace_id):
        rows = self.transport("DELETE", "investigation_workspaces", {
            "id": f"eq.{uuid_string(workspace_id)}"}, None)
        return rows[0] if rows else None

    def add_item(self, workspace_id, payload):
        body = {"workspace_id": uuid_string(workspace_id), **workspace_item_payload(payload)}
        rows = self.transport("POST", "workspace_items", None, body)
        return rows[0] if rows else None

    def update_item(self, workspace_id, item_id, payload):
        rows = self.transport("PATCH", "workspace_items", {
            "id": f"eq.{uuid_string(item_id)}",
            "workspace_id": f"eq.{uuid_string(workspace_id)}",
        }, workspace_item_payload(payload, partial=True))
        return rows[0] if rows else None

    def delete_item(self, workspace_id, item_id):
        rows = self.transport("DELETE", "workspace_items", {
            "id": f"eq.{uuid_string(item_id)}",
            "workspace_id": f"eq.{uuid_string(workspace_id)}",
        }, None)
        return rows[0] if rows else None


def dispatch_workspace_api(method, path, payload, authorization, repository=None):
    """Dispatch bounded workspace CRUD; database RLS remains authoritative."""
    try:
        token = access_token_from_header(authorization)
        repository = repository or WorkspaceRepository(token)
        parts = path.strip("/").split("/")
        result = None
        if parts == ["api", "v1", "workspaces"]:
            if method == "GET":
                result = repository.list()
            elif method == "POST":
                result = repository.create(payload)
            else:
                return 405, {"error": "Method not allowed"}, None
        elif len(parts) == 4 and parts[:3] == ["api", "v1", "workspaces"]:
            workspace_id = uuid_string(parts[3])
            if method == "GET":
                result = repository.get(workspace_id)
            elif method == "PATCH":
                result = repository.update(workspace_id, payload)
            elif method == "DELETE":
                result = repository.delete(workspace_id)
            else:
                return 405, {"error": "Method not allowed"}, None
        elif (len(parts) == 5 and parts[:3] == ["api", "v1", "workspaces"]
              and parts[4] == "items" and method == "POST"):
            result = repository.add_item(uuid_string(parts[3]), payload)
        elif (len(parts) == 6 and parts[:3] == ["api", "v1", "workspaces"]
              and parts[4] == "items"):
            workspace_id, item_id = uuid_string(parts[3]), uuid_string(parts[5])
            if method == "PATCH":
                result = repository.update_item(workspace_id, item_id, payload)
            elif method == "DELETE":
                result = repository.delete_item(workspace_id, item_id)
            else:
                return 405, {"error": "Method not allowed"}, None
        else:
            return 404, {"error": "Not found / 找不到端點"}, None
    except WorkspaceUnauthorized:
        return 401, {"error": "請登入後使用調查工作區 / Authentication required"}, None
    except (WorkspaceValidationError, ValueError, TypeError):
        return 400, {"error": "Workspace 輸入格式錯誤 / Invalid workspace input"}, None
    except WorkspaceFeatureUnavailable:
        return 503, {"status": "not_enabled", "schema_available": False,
                     "error": "Workspace schema 尚未部署 / Workspace schema unavailable"}, None
    except WorkspaceStoreUnavailable:
        return 503, {"status": "unavailable",
                     "error": "Workspace 暫時無法使用 / Workspace unavailable"}, None
    if result is None:
        return 404, {"error": "找不到 Workspace 項目，或不屬於目前使用者 / Not found"}, None
    code = 201 if method == "POST" else 200
    return code, response(result), None
