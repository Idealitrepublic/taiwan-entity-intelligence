"""Public, bounded PostgREST reads. Never use service-role credentials here."""
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlencode
from .contracts import (
    ENTITY_FIELDS as PUBLIC_ENTITY_FIELDS,
    EVIDENCE_FIELDS as PUBLIC_EVIDENCE_FIELDS,
    RELATIONSHIP_FIELDS as PUBLIC_RELATIONSHIP_FIELDS,
    POLITICIAN_TERM_FIELDS as PUBLIC_POLITICIAN_TERM_FIELDS,
    ASSET_DECLARATION_FIELDS as PUBLIC_ASSET_DECLARATION_FIELDS,
    select_list,
)
from .models import uuid_string
from src.public_config import SUPABASE_PUBLISHABLE_KEY

ENTITY_FIELDS = select_list(PUBLIC_ENTITY_FIELDS)
EVIDENCE_FIELDS = select_list(PUBLIC_EVIDENCE_FIELDS)
RELATIONSHIP_FIELDS = select_list(PUBLIC_RELATIONSHIP_FIELDS)
POLITICIAN_TERM_FIELDS = select_list(PUBLIC_POLITICIAN_TERM_FIELDS)
ASSET_DECLARATION_FIELDS = select_list(PUBLIC_ASSET_DECLARATION_FIELDS)


class EntityStoreUnavailable(RuntimeError):
    """No credentials or unavailable/missing Phase 1 schema."""


class EntityFeatureUnavailable(EntityStoreUnavailable):
    """The backing store is reachable but does not have an additive read RPC yet."""


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
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and table in (
                    "rpc/find_entity_relationship_path", "rpc/political_contributions_for_entity",
                    "politician_terms", "asset_declarations"):
                raise EntityFeatureUnavailable("Additive Entity feature is not installed") from exc
            raise EntityStoreUnavailable("Entity database unavailable") from exc
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

    def graph_neighbors(self, entity_id, *, limit=12, after=None, relationship_type=None):
        entity_id = uuid_string(entity_id)
        params = {"focus_id": entity_id, "result_limit": limit}
        if after:
            params["after_relationship_id"] = uuid_string(after)
        if relationship_type:
            params["relationship_type_filter"] = relationship_type
        rows = self.transport("rpc/graph_entity_neighbors", params)
        if not rows:
            return None
        root = rows[0].get("focus_entity")
        if not root:
            return None
        relationship_rows = [row for row in rows if row.get("relationship")]
        visible = relationship_rows[:limit]
        nodes = {root["id"]: root}
        edges = []
        for row in visible:
            source, target = row.get("source_entity"), row.get("target_entity")
            primary = row.get("primary_evidence")
            if not source or not target or not primary:
                continue
            nodes[source["id"]] = source
            nodes[target["id"]] = target
            relationship = row["relationship"]
            edges.append({**relationship, "source": relationship["source_entity_id"],
                          "target": relationship["target_entity_id"],
                          "primary_evidence": primary})
        has_more = len(relationship_rows) > limit
        return {"focus_entity_id": entity_id,
                "nodes": sorted(nodes.values(), key=lambda item: item["id"]), "edges": edges,
                "has_more": has_more,
                "next_cursor": edges[-1]["id"] if has_more and edges else None,
                "requested_limit": limit}

    def politician_profile(self, entity_id, *, relationship_limit=25):
        entity_id = uuid_string(entity_id)
        if not 1 <= relationship_limit <= 25:
            raise ValueError("Politician relationship limit must be between 1 and 25")
        profile = self.entity(entity_id)
        if not profile or profile.get("entity_type") != "Politician":
            return None
        schema_available = True
        try:
            terms = self.transport("politician_terms", {
                "select": (
                    f"{POLITICIAN_TERM_FIELDS},"
                    f"party:entities!politician_terms_party_entity_id_fkey({ENTITY_FIELDS}),"
                    "primary_evidence:evidence_records!politician_terms_primary_evidence_id_fkey("
                    f"{EVIDENCE_FIELDS})"
                ),
                "politician_entity_id": f"eq.{entity_id}",
                "publication_status": "eq.published",
                "order": "term_number.desc,start_date.desc,id.asc",
                "limit": 21,
            })
        except EntityFeatureUnavailable:
            terms, schema_available = [], False
        relationship_rows = self.transport("relationships", {
            "select": (
                f"{RELATIONSHIP_FIELDS},"
                f"source_entity:entities!relationships_source_entity_id_fkey({ENTITY_FIELDS}),"
                f"target_entity:entities!relationships_target_entity_id_fkey({ENTITY_FIELDS}),"
                "primary_evidence:evidence_records!relationships_primary_evidence_id_fkey("
                f"{EVIDENCE_FIELDS})"
            ),
            "source_entity_id": f"eq.{entity_id}",
            "relationship_type": (
                "in.(MEMBER_OF,LEGISLATOR_OF,COMMITTEE_MEMBER,PROPOSED_BILL,CO_SPONSORED_BILL)"),
            "status": "eq.published", "order": "id.asc", "limit": relationship_limit + 1,
        })
        groups = {"affiliations": [], "legislatures": [], "committees": [],
                  "proposed_bills": [], "co_sponsored_bills": []}
        relationship_groups = {
            "MEMBER_OF": "affiliations", "LEGISLATOR_OF": "legislatures",
            "COMMITTEE_MEMBER": "committees", "PROPOSED_BILL": "proposed_bills",
            "CO_SPONSORED_BILL": "co_sponsored_bills",
        }
        for row in relationship_rows[:relationship_limit]:
            group = relationship_groups.get(row.get("relationship_type"))
            if not group or not row.get("target_entity") or not row.get("primary_evidence"):
                continue
            groups[group].append({
                "relationship": {key: value for key, value in row.items()
                                 if key not in ("source_entity", "target_entity", "primary_evidence")},
                "entity": row["target_entity"],
                "evidence": row["primary_evidence"],
            })
        return {"entity": profile, "terms": terms[:20], "terms_has_more": len(terms) > 20,
                "relationship_has_more": len(relationship_rows) > relationship_limit,
                "schema_available": schema_available, **groups}

    def political_contributions(self, entity_id, *, limit=25, after=None):
        entity_id = uuid_string(entity_id)
        if not 1 <= limit <= 25:
            raise ValueError("Political contribution limit must be between 1 and 25")
        params = {"focus_entity_id": entity_id, "result_limit": limit}
        if after:
            params["after_relationship_id"] = uuid_string(after)
        try:
            rows = self.transport("rpc/political_contributions_for_entity", params)
        except EntityFeatureUnavailable:
            return self._political_contributions_fallback(entity_id, limit=limit, after=after)
        if not rows:
            return None
        focus = rows[0].get("focus_entity")
        if not focus:
            return None
        return self._political_contribution_page(focus, rows, limit)

    @staticmethod
    def _political_contribution_page(focus, rows, limit):
        records = [row for row in rows if row.get("relationship")]
        items = []
        for row in records[:limit]:
            relationship = row.get("relationship") or {}
            evidence = row.get("primary_evidence") or {}
            company, politician = row.get("company_entity"), row.get("politician_entity")
            if not company or not politician or not evidence:
                continue
            items.append({
                "relationship": relationship,
                "company": company,
                "politician": politician,
                "amount": relationship.get("amount"),
                "currency": relationship.get("currency"),
                "date": relationship.get("start_date"),
                "contribution_type": relationship.get("source_role"),
                "source_record": {"id": evidence.get("source_record_id"),
                                  "locator": evidence.get("source_locator")},
                "evidence": evidence,
                "original_source_url": evidence.get("source_url"),
            })
        has_more = len(records) > limit
        return {"focus_entity": focus, "items": items, "has_more": has_more,
                "next_cursor": items[-1]["relationship"]["id"] if has_more and items else None,
                "match_method": "exact_uniform_number", "requested_limit": limit}

    def _political_contributions_fallback(self, entity_id, *, limit, after):
        entities = self.transport("entities", {
            "select": ENTITY_FIELDS, "id": f"eq.{entity_id}",
            "entity_type": "in.(Company,Politician)",
            "publication_status": "eq.published", "limit": 1})
        if not entities:
            return None
        params = {
            "select": (
                f"{RELATIONSHIP_FIELDS},"
                f"company_entity:entities!relationships_source_entity_id_fkey({ENTITY_FIELDS}),"
                f"politician_entity:entities!relationships_target_entity_id_fkey({ENTITY_FIELDS}),"
                "primary_evidence:evidence_records!relationships_primary_evidence_id_fkey("
                f"{EVIDENCE_FIELDS})"),
            "or": f"(source_entity_id.eq.{entity_id},target_entity_id.eq.{entity_id})",
            "relationship_type": "eq.POLITICAL_CONTRIBUTION_TO",
            "status": "eq.published", "order": "id.asc", "limit": limit + 1,
        }
        if after:
            params["id"] = f"gt.{uuid_string(after)}"
        raw = self.transport("relationships", params)
        rows = []
        for item in raw:
            evidence = item.get("primary_evidence") or {}
            if (evidence.get("source_locator") or {}).get("match_method") != "exact_uniform_number":
                continue
            relationship = {key: value for key, value in item.items()
                            if key not in ("company_entity", "politician_entity", "primary_evidence")}
            rows.append({"focus_entity": entities[0], "relationship": relationship,
                         "company_entity": item.get("company_entity"),
                         "politician_entity": item.get("politician_entity"),
                         "primary_evidence": evidence})
        return self._political_contribution_page(entities[0], rows, limit)

    def asset_declarations(self, politician_id, *, limit=25, after=None,
                           declaration_year=None, asset_type=None):
        politician_id = uuid_string(politician_id)
        if not 1 <= limit <= 25:
            raise ValueError("Asset declaration limit must be between 1 and 25")
        profiles = self.transport("entities", {
            "select": ENTITY_FIELDS, "id": f"eq.{politician_id}",
            "entity_type": "eq.Politician", "publication_status": "eq.published", "limit": 1})
        if not profiles:
            return None
        params = {
            "select": (
                f"{ASSET_DECLARATION_FIELDS},"
                f"company:entities!asset_declarations_company_entity_id_fkey({ENTITY_FIELDS}),"
                f"relationship:relationships!asset_declarations_relationship_id_fkey({RELATIONSHIP_FIELDS}),"
                "primary_evidence:evidence_records!asset_declarations_primary_evidence_id_fkey("
                f"{EVIDENCE_FIELDS})"),
            "politician_id": f"eq.{politician_id}", "publication_status": "eq.published",
            "order": "id.asc", "limit": limit + 1,
        }
        if after:
            params["id"] = f"gt.{uuid_string(after)}"
        if declaration_year is not None:
            params["declaration_year"] = f"eq.{int(declaration_year)}"
        if asset_type:
            params["asset_type"] = f"eq.{asset_type}"
        try:
            rows = self.transport("asset_declarations", params)
        except EntityFeatureUnavailable:
            return {"politician": profiles[0], "items": [], "has_more": False,
                    "next_cursor": None, "schema_available": False,
                    "requested_limit": limit}
        visible = rows[:limit]
        has_more = len(rows) > limit
        return {"politician": profiles[0], "items": visible, "has_more": has_more,
                "next_cursor": visible[-1]["id"] if has_more and visible else None,
                "schema_available": True, "requested_limit": limit}

    def relationship_path(self, source_entity_id, target_entity_id, *, max_depth=3):
        source_entity_id = uuid_string(source_entity_id)
        target_entity_id = uuid_string(target_entity_id)
        try:
            rows = self.transport("rpc/find_entity_relationship_path", {
                "start_entity_id": source_entity_id,
                "end_entity_id": target_entity_id,
                "max_depth": max_depth,
            })
        except EntityFeatureUnavailable:
            return self._relationship_path_from_graph(source_entity_id, target_entity_id,
                                                      max_depth=max_depth)
        if not rows:
            return None
        result = rows[0].get("path_result")
        if not isinstance(result, dict):
            raise EntityStoreUnavailable("Unexpected path response")
        return result

    def _relationship_path_from_graph(self, source_entity_id, target_entity_id, *, max_depth):
        page_size, entity_limit = 12, 30
        target_graph = self.graph_neighbors(target_entity_id, limit=1)
        if target_graph is None:
            return None
        target = next((node for node in target_graph["nodes"]
                       if node["id"] == target_entity_id), None)
        frontier = [source_entity_id]
        visited = {source_entity_id}
        parents = {}
        entities = {target_entity_id: target}
        expanded = 0
        truncated = False
        source = None
        for _depth in range(1, max_depth + 1):
            next_frontier = []
            for current_id in frontier:
                if expanded >= entity_limit:
                    truncated = True
                    break
                graph = self.graph_neighbors(current_id, limit=page_size)
                if graph is None:
                    if current_id == source_entity_id:
                        return None
                    continue
                expanded += 1
                entities.update({node["id"]: node for node in graph["nodes"]})
                source = source or entities.get(source_entity_id)
                truncated = truncated or graph["has_more"]
                for edge in graph["edges"]:
                    neighbor_id = edge["target"] if edge["source"] == current_id else edge["source"]
                    if neighbor_id in visited:
                        continue
                    visited.add(neighbor_id)
                    parents[neighbor_id] = (current_id, edge)
                    if neighbor_id == target_entity_id:
                        segments = []
                        cursor = target_entity_id
                        while cursor != source_entity_id:
                            previous, path_edge = parents[cursor]
                            segments.append({
                                "from_entity": entities.get(previous, {"id": previous}),
                                "to_entity": entities.get(cursor, {"id": cursor}),
                                "traversal_direction": (
                                    "forward" if path_edge["source"] == previous else "reverse"),
                                "relationship": {key: value for key, value in path_edge.items()
                                                 if key != "primary_evidence"},
                                "evidence": path_edge.get("primary_evidence"),
                            })
                            cursor = previous
                        segments.reverse()
                        return {"found": True, "source_entity": source,
                                "target_entity": target, "depth": len(segments),
                                "segments": segments, "max_depth": max_depth,
                                "relationship_limit_per_node": page_size,
                                "entity_expansion_limit": entity_limit,
                                "traversal_bounded": True, "truncated": truncated,
                                "backend": "graph_neighbors_fallback"}
                    next_frontier.append(neighbor_id)
            if truncated and expanded >= entity_limit:
                break
            frontier = next_frontier
            if not frontier:
                break
        return {"found": False, "source_entity": source, "target_entity": target,
                "depth": None, "segments": [], "max_depth": max_depth,
                "relationship_limit_per_node": page_size,
                "entity_expansion_limit": entity_limit,
                "traversal_bounded": True, "truncated": truncated,
                "backend": "graph_neighbors_fallback"}
