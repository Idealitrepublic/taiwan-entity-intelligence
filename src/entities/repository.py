"""Public, bounded PostgREST reads. Never use service-role credentials here."""
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlencode
from .models import uuid_string
from src.public_config import SUPABASE_PUBLISHABLE_KEY

ENTITY_FIELDS = "id,entity_type,canonical_name,display_name,identity_status,created_at,updated_at"
EVIDENCE_FIELDS = ("id,source_name,source_record_id,source_class,source_url,source_locator,"
                   "title,summary,observed_at,retrieved_at,content_hash,status,created_at,updated_at")
RELATIONSHIP_FIELDS = ("id,source_entity_id,target_entity_id,relationship_type,primary_evidence_id,"
                       "start_date,end_date,date_precision,observed_at,amount,currency,percentage,"
                       "quantity,quantity_unit,source_role,confidence,status,created_at,updated_at")


class EntityStoreUnavailable(RuntimeError):
    """No credentials or unavailable/missing Phase 1 schema."""


class EntityRepository:
    def __init__(self, transport=None):
        self.url = os.environ.get("TEI_ENTITY_SUPABASE_URL") or os.environ.get(
            "SUPABASE_URL", "https://rztdbdurkjfrirsrrhtu.supabase.co")
        self.key = os.environ.get("TEI_ENTITY_ANON_KEY") or os.environ.get("SUPABASE_ANON_KEY")
        if not self.key and self.url.rstrip("/") == "https://rztdbdurkjfrirsrrhtu.supabase.co":
            self.key = SUPABASE_PUBLISHABLE_KEY
        self.transport = transport or self._get

    def _get(self, table, params):
        if not self.key:
            raise EntityStoreUnavailable("Public read credential is not configured")
        request = urllib.request.Request(
            f"{self.url.rstrip('/')}/rest/v1/{table}?{urlencode(params)}",
            headers={"apikey": self.key, "Authorization": f"Bearer {self.key}"})
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                rows = json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise EntityStoreUnavailable("Entity database unavailable") from exc
        if not isinstance(rows, list):
            raise EntityStoreUnavailable("Unexpected entity database response")
        return rows

    def entity(self, entity_id):
        rows = self.transport("entities", {"select": ENTITY_FIELDS, "id": f"eq.{uuid_string(entity_id)}",
                                          "publication_status": "eq.published", "limit": 1})
        if not rows:
            return None
        links = self.transport("entity_evidence", {
            "select": f"fact_type,evidence:evidence_records({EVIDENCE_FIELDS})",
            "entity_id": f"eq.{uuid_string(entity_id)}", "order": "evidence_id.asc,fact_type.asc", "limit": 51})
        return {**rows[0], "evidence": [link for link in links[:50] if link.get("evidence")],
                "evidence_has_more": len(links) > 50}

    def evidence(self, evidence_id):
        rows = self.transport("evidence_records", {"select": EVIDENCE_FIELDS,
            "id": f"eq.{uuid_string(evidence_id)}", "status": "eq.active",
            "publication_status": "eq.published", "limit": 1})
        return rows[0] if rows else None

    def relationship(self, relationship_id):
        rows = self.transport("relationships", {"select": RELATIONSHIP_FIELDS,
            "id": f"eq.{uuid_string(relationship_id)}", "status": "eq.published", "limit": 1})
        if not rows:
            return None
        relationship = dict(rows[0])
        primary = self.evidence(relationship["primary_evidence_id"])
        # Defensive against concurrent retraction between the two reads.
        if not primary:
            return None
        links = self.transport("relationship_evidence", {
            "select": f"support_type,evidence:evidence_records({EVIDENCE_FIELDS})",
            "relationship_id": f"eq.{relationship_id}", "order": "evidence_id.asc", "limit": 51})
        evidence = [{"support_type": "supports", "evidence": primary}]
        evidence.extend(link for link in links[:50]
                        if link.get("evidence") and link["evidence"]["id"] != primary["id"])
        relationship.update(evidence=evidence, evidence_has_more=len(links) > 50,
                            source_name=primary["source_name"], source_url=primary["source_url"],
                            source_record_id=primary["source_record_id"])
        return relationship

    def relationships(self, entity_id, *, limit=25, after=None, relationship_type=None):
        entity_id = uuid_string(entity_id)
        params = {"select": RELATIONSHIP_FIELDS,
                  "or": f"(source_entity_id.eq.{entity_id},target_entity_id.eq.{entity_id})",
                  "status": "eq.published", "order": "id.asc", "limit": limit + 1}
        if after:
            params["id"] = f"gt.{uuid_string(after)}"
        if relationship_type:
            params["relationship_type"] = f"eq.{relationship_type}"
        rows = self.transport("relationships", params)
        return {"items": rows[:limit], "has_more": len(rows) > limit,
                "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None}

    def search(self, term, *, entity_type=None, limit=20):
        params = {"search_query": term, "result_limit": limit}
        if entity_type:
            params["entity_type_filter"] = entity_type
        rows = self.transport("rpc/search_entities", params)
        groups = {}
        for row in rows:
            kind = row.get("entity_type")
            groups[kind] = groups.get(kind, 0) + 1
        return {"query": term, "items": rows, "groups": groups,
                "result_count": len(rows), "limit": limit}
