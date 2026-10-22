"""Deterministic, read-only investigation report projection and rendering."""
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from html import escape
import re
from urllib.parse import urlsplit

from src.entities.contracts import response
from src.entities.models import uuid_string
from src.entities.repository import EntityRepository, EntityStoreUnavailable
from src.workspaces import (
    WorkspaceRepository,
    WorkspaceStoreUnavailable,
    WorkspaceUnauthorized,
    access_token_from_header,
)

REPORT_VERSION = "1"
MAX_GRAPH_RELATIONSHIPS = 25
MAX_REPORT_GRAPH_EDGES = 100
MAX_WORKSPACE_ROOTS = 5
POLITICAL_RELATIONSHIPS = {
    "POLITICAL_CONTRIBUTION_TO", "MEMBER_OF", "LEGISLATOR_OF",
    "COMMITTEE_MEMBER", "PROPOSED_BILL", "CO_SPONSORED_BILL",
    "GOVERNMENT_POSITION",
}
LIVE_RELATIONSHIP_TYPES = {
    "procurement_award": "CONTRACT_WITH", "labor_penalty": "RELATED_TO_PENALTY",
    "mentioned_in_judgment": "RELATED_TO_JUDGMENT",
    "source_connected_company": "SOURCE_CONNECTED_COMPANY",
}
SECTION_TITLES = (
    ("entity_profiles", "實體概況 / Entity Profile"),
    ("company_registry", "公司登記 / Company Registry"),
    ("key_relationships", "關鍵關係 / Key Relationships"),
    ("political_relationships", "政治關係 / Political Relationships"),
    ("government_contracts", "政府標案 / Government Contracts"),
    ("judgments", "司法裁判 / Judgments"),
    ("penalties", "裁罰 / Penalties"),
    ("asset_records", "財產申報 / Asset Records"),
    ("relationship_graph", "關係圖 / Relationship Graph"),
    ("sources", "來源 / Sources"),
)


class ReportNotFound(RuntimeError):
    pass


class ReportValidationError(ValueError):
    pass


class EmptyWorkspaceReport(ReportValidationError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _evidence(record):
    if not isinstance(record, dict) or not record.get("id"):
        return None
    return {
        **record,
        "source": record.get("source_name"),
        "source_url": record.get("source_url"),
        "retrieved_at": record.get("retrieved_at"),
    }


def _relation(edge, nodes):
    evidence = _evidence(edge.get("primary_evidence"))
    relationship = {key: value for key, value in edge.items()
                    if key not in ("source", "target", "primary_evidence")}
    source_id = edge.get("source") or edge.get("source_entity_id")
    target_id = edge.get("target") or edge.get("target_entity_id")
    return {
        "relationship": relationship,
        "source_entity": nodes.get(source_id, {"id": source_id}),
        "target_entity": nodes.get(target_id, {"id": target_id}),
        "evidence": evidence,
        "source": evidence.get("source") if evidence else None,
        "source_url": evidence.get("source_url") if evidence else None,
        "retrieved_at": evidence.get("retrieved_at") if evidence else None,
    }


def _asset(row):
    evidence = _evidence(row.get("primary_evidence"))
    return {
        **{key: value for key, value in row.items() if key != "primary_evidence"},
        "evidence": evidence,
        "source": evidence.get("source") if evidence else None,
        "source_url": evidence.get("source_url") if evidence else None,
        "retrieved_at": evidence.get("retrieved_at") if evidence else None,
    }


def _normalize_evidence_tree(value):
    if isinstance(value, list):
        return [_normalize_evidence_tree(item) for item in value]
    if not isinstance(value, dict):
        return value
    if value.get("id") and "source_name" in value:
        return _evidence(value)
    return {key: _normalize_evidence_tree(child) for key, child in value.items()}


def _stored_relationship(row):
    links = row.get("evidence", [])
    primary_id = row.get("primary_evidence_id")
    primary = next((link.get("evidence") for link in links
                    if (link.get("evidence") or {}).get("id") == primary_id), None)
    primary = primary or next((link.get("evidence") for link in links
                               if link.get("evidence")), None)
    evidence = _evidence(primary)
    relationship = {key: value for key, value in row.items()
                    if key not in ("evidence", "evidence_has_more", "source_name",
                                   "source_url", "source_record_id")}
    return {
        "relationship": relationship,
        "source_entity": {"id": row.get("source_entity_id")},
        "target_entity": {"id": row.get("target_entity_id")},
        "evidence": evidence,
        "source": evidence.get("source") if evidence else None,
        "source_url": evidence.get("source_url") if evidence else None,
        "retrieved_at": evidence.get("retrieved_at") if evidence else None,
    }


def _source_map(report):
    sources = {}

    def visit(value):
        if isinstance(value, dict):
            evidence = value.get("evidence")
            if isinstance(evidence, dict) and evidence.get("id"):
                sources[evidence["id"]] = evidence
            if value.get("id") and "source_name" in value:
                normalized = _evidence(value)
                if normalized:
                    sources[normalized["id"]] = normalized
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for key, value in report.items():
        if key != "sources":
            visit(value)
    return sources


class ReportService:
    def __init__(self, entity_repository=None, workspace_factory=None, clock=None):
        self.entities = entity_repository or EntityRepository()
        self.workspace_factory = workspace_factory or WorkspaceRepository
        self.clock = clock or _now

    def _report_graph(self, entity_id):
        """Read evidenced neighbor pages, with a firm report size boundary."""
        graph = self.entities.graph_neighbors(entity_id, limit=MAX_GRAPH_RELATIONSHIPS)
        if not graph:
            return None
        nodes = {node["id"]: node for node in graph.get("nodes", []) if node.get("id")}
        edges = {edge["id"]: edge for edge in graph.get("edges", []) if edge.get("id")}
        cursor = graph.get("next_cursor")
        seen_cursors = set()
        while graph.get("has_more") and cursor and cursor not in seen_cursors and len(edges) < MAX_REPORT_GRAPH_EDGES:
            seen_cursors.add(cursor)
            page = self.entities.graph_neighbors(entity_id, limit=MAX_GRAPH_RELATIONSHIPS, after=cursor)
            if not page:
                break
            nodes.update({node["id"]: node for node in page.get("nodes", []) if node.get("id")})
            edges.update({edge["id"]: edge for edge in page.get("edges", []) if edge.get("id")})
            graph = page
            cursor = page.get("next_cursor")
        return {"nodes": list(nodes.values()), "edges": list(edges.values()),
                "has_more": bool(graph.get("has_more")), "focus_entity_id": entity_id}

    def _entity_report(self, entity_id, report_type="ENTITY"):
        entity_id = uuid_string(entity_id)
        entity = self.entities.entity(entity_id)
        if not entity:
            raise ReportNotFound("Published Entity not found")
        if report_type == "POLITICIAN" and entity.get("entity_type") != "Politician":
            raise ReportNotFound("Published Politician not found")

        graph = self._report_graph(entity_id)
        graph = graph or {"nodes": [entity], "edges": [], "has_more": False}
        nodes = {node["id"]: node for node in graph.get("nodes", []) if node.get("id")}
        nodes.setdefault(entity_id, entity)
        relationships = [_relation(edge, nodes) for edge in graph.get("edges", [])]
        asset_records = []
        politician = None
        if entity.get("entity_type") == "Politician":
            politician = self.entities.politician_profile(
                entity_id, relationship_limit=MAX_GRAPH_RELATIONSHIPS)
            assets = self.entities.asset_declarations(
                entity_id, limit=MAX_GRAPH_RELATIONSHIPS)
            asset_records = [_asset(row) for row in (assets or {}).get("items", [])]

        entity_evidence = []
        for link in entity.get("evidence", []):
            normalized = _evidence(link.get("evidence"))
            if normalized:
                entity_evidence.append({"fact_type": link.get("fact_type"),
                                        "evidence": normalized})
        profile = {**entity, "evidence": entity_evidence}
        registry = (self.entities.company_registry_for_entity(entity_id)
                    if entity.get("entity_type") == "Company" else None)
        if politician:
            profile["politician_profile"] = _normalize_evidence_tree(politician)

        report = {
            "report_version": REPORT_VERSION,
            "report_type": report_type,
            "generated_at": self.clock(),
            "title": f"T.E.I. 調查報告 / Investigation Report — {entity.get('display_name') or entity.get('canonical_name') or entity_id}",
            "methodology": (
                "關係與證據僅整理已發布公開資料；公司登記若以統編向經濟部即時查得，將明確標示。未顯示不代表不存在，亦不推論違法或犯罪。 "
                "Published evidenced links plus clearly marked exact-ID live company registry; absence is not proof of no record or wrongdoing."),
            "coverage": {
                "relationship_limit": MAX_REPORT_GRAPH_EDGES,
                "relationship_truncated": bool(graph.get("has_more")),
                "asset_limit": MAX_GRAPH_RELATIONSHIPS,
            },
            "entity_profiles": [profile],
            "company_registry": [registry] if isinstance(registry, dict) else [],
            "key_relationships": relationships,
            "political_relationships": [row for row in relationships if
                                        row["relationship"].get("relationship_type")
                                        in POLITICAL_RELATIONSHIPS],
            "government_contracts": [row for row in relationships if
                                     row["relationship"].get("relationship_type") == "CONTRACT_WITH"],
            "judgments": [row for row in relationships if
                          row["relationship"].get("relationship_type") == "RELATED_TO_JUDGMENT"],
            "penalties": [row for row in relationships if
                          row["relationship"].get("relationship_type") == "RELATED_TO_PENALTY"],
            "asset_records": asset_records,
            "relationship_graph": {
                "focus_entity_id": entity_id,
                "nodes": list(nodes.values()),
                "edges": relationships,
                "truncated": bool(graph.get("has_more")),
            },
            "sources": [],
        }
        report["sources"] = list(_source_map(report).values())
        if isinstance(registry, dict) and registry.get("source_url"):
            report["sources"].append({"source_name": registry.get("source") or "經濟部公司登記",
                                      "source_url": registry["source_url"],
                                      "retrieved_at": registry.get("fetched_at"),
                                      "title": "公司登記來源 / Company registry source"})
        return report

    def entity_report(self, entity_id):
        return self._entity_report(entity_id)

    def politician_report(self, entity_id):
        return self._entity_report(entity_id, "POLITICIAN")

    def company_report(self, uniform, *, company_loader=None, award_loader=None, related_loader=None):
        """Snapshot the same bounded live sources used by the company screen."""
        if not isinstance(uniform, str) or not re.fullmatch(r"[0-9]{8}", uniform):
            raise ReportValidationError("Invalid company identifier")
        if company_loader is None:
            from src.cloud_company import build_company
            company_loader = build_company
        if award_loader is None:
            from src.sources.procurement import lookup_awards
            def award_loader(value):
                return lookup_awards(value, timeout=12)
        if related_loader is None:
            from src.live_related_companies import related_companies
            related_loader = related_companies
        with ThreadPoolExecutor(max_workers=3) as pool:
            company_job = pool.submit(company_loader, uniform)
            award_job = pool.submit(award_loader, uniform)
            related_job = pool.submit(related_loader, uniform)
            try:
                data = company_job.result()
            except Exception as exc:
                raise EntityStoreUnavailable("Official company registry unavailable") from exc
            try:
                awards = award_job.result()
            except Exception:
                awards = {"status": "partial", "records": [], "limited": True}
            try:
                related = related_job.result()
            except Exception:
                related = {"status": "partial", "items": [], "limited": True}
        if data.get("status") != "ok" or data.get("uniform_number") != uniform:
            raise ReportNotFound("Official company not found")
        company = data.get("company") or {}
        if str(company.get("Business_Accounting_NO") or "") != uniform:
            raise ReportNotFound("Official company ID mismatch")
        graph = data.get("graph") or {}
        nodes = {row["id"]: dict(row) for row in graph.get("nodes", []) if row.get("id")}
        edges = list(graph.get("edges") or [])
        root_id = f"company:{uniform}"
        check = data.get("website_crosscheck") or {}
        if check.get("domain"):
            website_id = "website:" + check["domain"]
            site_evidence = {"title": "公司網站 / Company website",
                             "source_name": data.get("website_source"),
                             "source_url": data.get("website_url"),
                             "source_record_id": uniform}
            nodes[website_id] = {"id": website_id, "type": "website",
                                 "label": check["domain"], "evidence": site_evidence}
            edges.append({"source": root_id, "target": website_id,
                          "relationship": "website", "evidence": site_evidence})
            for index, hit in enumerate((check.get("anti_fraud") or {}).get("records") or []):
                hit_id = f"anti_fraud:{check['domain']}:{index}"
                hit_evidence = {"title": hit.get("網站性質") or "165 官方網域紀錄",
                                "source_name": "165 警政署網域索引",
                                "source_url": hit.get("source_url") or check.get("source_url"),
                                "source_record_id": check["domain"],
                                "retrieved_at": check.get("indexed_at")}
                nodes[hit_id] = {"id": hit_id, "type": "anti_fraud",
                                 "label": hit.get("網站性質") or check["domain"],
                                 "evidence": hit_evidence}
                edges.append({"source": website_id, "target": hit_id,
                              "relationship": "listed_in_anti_fraud", "evidence": hit_evidence,
                              "observation_only": True})
        root_evidence = (nodes.get(root_id) or {}).get("evidence") or {}
        registry = {"uniform_number": uniform, "name": data.get("company_name"),
                    "status": company.get("Company_Status_Desc"),
                    "representative_name": company.get("Responsible_Name"),
                    "address": company.get("Company_Location"),
                    "capital_amount": company.get("Capital_Stock_Amount"),
                    "established_date": company.get("Company_Setup_Date"),
                    "source": root_evidence.get("source_name") or "經濟部公司登記",
                    "source_url": root_evidence.get("source_url"),
                    "fetched_at": root_evidence.get("retrieved_at"),
                    "data_status": "live_official_exact_id"}
        for row in awards.get("records") or []:
            record_id = "procurement:" + str(row.get("id"))
            evidence = {"title": row.get("title"), "source_name": awards.get("source"),
                        "source_url": row.get("source_url"),
                        "source_record_id": row.get("id"),
                        "retrieved_at": awards.get("retrieved_at")}
            nodes[record_id] = {"id": record_id, "type": "procurement",
                                "label": row.get("title") or "政府決標公告",
                                "properties": {"date": row.get("date"), "agency": row.get("agency")},
                                "evidence": evidence}
            edges.append({"source": root_id, "target": record_id,
                          "relationship": "procurement_award", "evidence": evidence})
        for item in (related or {}).get("items") or []:
            target_uniform = str(item.get("uniform_number") or "")
            evidence = item.get("evidence") or {}
            if not (re.fullmatch(r"[0-9]{8}", target_uniform) and
                    target_uniform != uniform and item.get("company_name") and
                    evidence.get("source_url") and evidence.get("source_record_id") and
                    item.get("connection_type") in ("corporate_director", "same_award_notice")):
                continue
            connector_id = f"related-connection:{uniform}:{target_uniform}"
            target_id = f"related-company:{target_uniform}"
            nodes[connector_id] = {"id": connector_id, "type": "related_connection",
                                   "label": item.get("connection_label"), "evidence": evidence}
            nodes[target_id] = {"id": target_id, "type": "related_company",
                                "label": item["company_name"], "evidence": evidence}
            edges.extend([{"source": root_id, "target": connector_id,
                           "relationship": item.get("connection_label"), "evidence": evidence,
                           "observation_only": True},
                          {"source": connector_id, "target": target_id,
                           "relationship": "source_connected_company", "evidence": evidence,
                           "observation_only": True}])
        categories = {"government_contracts": [], "judgments": [], "penalties": []}
        relationships, sources = [], {}
        for node in nodes.values():
            evidence = node.get("evidence") or {}
            if evidence.get("source_url"):
                locator = evidence.get("source_record_id") or evidence.get("source_locator")
                key = (evidence.get("source_url"), locator)
                sources[key] = {"title": evidence.get("title") or node.get("label"),
                                "source_name": evidence.get("source_name"),
                                "source_url": evidence["source_url"],
                                "retrieved_at": evidence.get("retrieved_at"),
                                "source_record_id": evidence.get("source_record_id"),
                                "source_locator": evidence.get("source_locator")}
        for edge in edges:
            source = nodes.get(edge.get("source")) or {}
            target = nodes.get(edge.get("target")) or {}
            evidence = edge.get("evidence") or target.get("evidence") or {}
            if not evidence.get("source_url"):
                continue
            raw_type = edge.get("relationship") or "source_observation"
            relationship = {"relationship_type": LIVE_RELATIONSHIP_TYPES.get(raw_type, raw_type),
                            "start_date": (target.get("properties") or {}).get("date"),
                            "source_role": "來源觀察；身分待核 / Source observation; verify identity"
                            if edge.get("observation_only") or target.get("type") == "judicial"
                            else "官方統編或來源內紀錄 / Exact ID or source-scoped record"}
            record = {"relationship": relationship,
                      "source_entity": {"display_name": source.get("label") or source.get("id")},
                      "target_entity": {"display_name": target.get("label") or target.get("id")},
                      "evidence": evidence}
            category = {"procurement_award": "government_contracts",
                        "mentioned_in_judgment": "judgments",
                        "labor_penalty": "penalties"}.get(raw_type)
            if category:
                categories[category].append(record)
            else:
                relationships.append(record)
        if registry.get("source_url"):
            sources[(registry["source_url"], uniform)] = {
                "title": "公司登記 / Company registry", "source_name": registry["source"],
                "source_url": registry["source_url"], "retrieved_at": registry.get("fetched_at"),
                "source_record_id": uniform}
        truncated = bool(awards.get("limited") or (related or {}).get("limited")
                         or (data.get("judicial_result") or {}).get("limited"))
        return {"report_version": REPORT_VERSION, "report_type": "LIVE_COMPANY",
                "generated_at": self.clock(),
                "title": f"{data.get('company_name')}｜公司調查報告 / Company Investigation Report",
                "methodology": "本報告重查即時來源；來源觀察、名稱候選與正式關係分開標示，不推論犯罪或違法。 Live source snapshot; observations and name candidates are not formal findings.",
                "coverage": {"live_source_truncated": truncated,
                             "source_partial": any(value.get("status") == "partial" for value in
                                                   (awards, related or {}, data.get("judicial_result") or {}))},
                "entity_profiles": [{"display_name": data.get("company_name"),
                                     "entity_type": "Company", "public_identifier": uniform,
                                     "identity_status": "EXACT", "evidence": [root_evidence] if root_evidence else []}],
                "company_registry": [registry], "key_relationships": relationships,
                "anti_fraud_checks": [{"domain": check.get("domain"),
                                       "status": check.get("status") or "unavailable",
                                       "matched": (check.get("anti_fraud") or {}).get("matched", 0),
                                       "source_url": check.get("source_url"),
                                       "retrieved_at": check.get("indexed_at")}]
                if check.get("domain") else [],
                "political_relationships": [], "asset_records": [], **categories,
                "relationship_graph": {"nodes": list(nodes.values()), "edges": edges,
                                       "truncated": truncated},
                "sources": list(sources.values())}

    def workspace_report(self, workspace_id, access_token):
        workspace_id = uuid_string(workspace_id)
        workspace = self.workspace_factory(access_token).get(workspace_id)
        if not workspace:
            raise ReportNotFound("Owned Workspace not found")
        items = workspace.get("items", [])
        if not items:
            raise EmptyWorkspaceReport("Save a Workspace item before exporting")
        roots = []
        saved_relationships = {}
        unavailable = []
        for item in items:
            root = item.get("entity_id") or item.get("graph_root_entity_id")
            if root and root not in roots:
                roots.append(root)
            if item.get("item_type") == "RELATIONSHIP" and item.get("relationship_id"):
                relationship = self.entities.relationship(item["relationship_id"])
                saved_relationships[item["relationship_id"]] = relationship
                if relationship:
                    for endpoint in ("source_entity_id", "target_entity_id"):
                        if relationship.get(endpoint) and relationship[endpoint] not in roots:
                            roots.append(relationship[endpoint])
        child_reports = []
        for root in roots[:MAX_WORKSPACE_ROOTS]:
            try:
                child_reports.append(self._entity_report(root))
            except ReportNotFound:
                unavailable.append({"entity_id": root, "reason": "not_publicly_available"})
        report = {
            "report_version": REPORT_VERSION,
            "report_type": "WORKSPACE",
            "generated_at": self.clock(),
            "title": f"T.E.I. 調查工作區報告 / Workspace Report — {workspace.get('name') or workspace_id}",
            "methodology": (
                "僅整理此帳號收藏與已發布的證據資料；不作自動判斷或結論。 "
                "Owner-scoped saved items and published evidence only; no automated conclusion."),
            "coverage": {
                "workspace_item_limit": 200,
                "workspace_items_truncated": bool(workspace.get("items_has_more")),
                "entity_root_limit": MAX_WORKSPACE_ROOTS,
                "entity_roots_truncated": len(roots) > MAX_WORKSPACE_ROOTS,
                "unavailable_saved_references": unavailable,
            },
            "workspace": {key: value for key, value in workspace.items() if key != "items"},
            "workspace_items": items,
            "saved_evidence": [],
            "entity_profiles": [], "company_registry": [], "key_relationships": [],
            "political_relationships": [], "government_contracts": [],
            "judgments": [], "penalties": [], "asset_records": [],
            "relationship_graph": {"nodes": [], "edges": [], "truncated": False},
            "sources": [],
        }
        node_map, edge_map = {}, {}
        saved_sources = []
        for child in child_reports:
            for key in ("entity_profiles", "company_registry", "key_relationships", "political_relationships",
                        "government_contracts", "judgments", "penalties", "asset_records"):
                report[key].extend(child[key])
            graph = child["relationship_graph"]
            for node in graph["nodes"]:
                node_map[node["id"]] = node
            for edge in graph["edges"]:
                edge_id = edge.get("relationship", {}).get("id")
                if edge_id:
                    edge_map[edge_id] = edge
            report["relationship_graph"]["truncated"] |= bool(graph.get("truncated"))
            saved_sources.extend({"id": source.get("id") or f"registry:{source.get('source_url')}", **source}
                                 for source in child.get("sources", []) if source.get("source_url"))
        report["relationship_graph"].update(
            nodes=list(node_map.values()), edges=list(edge_map.values()))
        for item in items:
            if item.get("item_type") == "EVIDENCE" and item.get("evidence_id"):
                evidence = _evidence(self.entities.evidence(item["evidence_id"]))
                if evidence:
                    saved_sources.append(evidence)
                    report["saved_evidence"].append(evidence)
                else:
                    unavailable.append({"workspace_item_id": item.get("id"),
                                        "evidence_id": item["evidence_id"], "reason": "not_publicly_available"})
            elif item.get("item_type") == "RELATIONSHIP" and item.get("relationship_id"):
                relationship = saved_relationships.get(item["relationship_id"])
                if not relationship:
                    unavailable.append({"workspace_item_id": item.get("id"),
                                        "relationship_id": item["relationship_id"], "reason": "not_publicly_available"})
                for link in (relationship or {}).get("evidence", []):
                    evidence = _evidence(link.get("evidence"))
                    if evidence:
                        saved_sources.append(evidence)
                if relationship:
                    saved = _stored_relationship(relationship)
                    saved_id = saved["relationship"].get("id")
                    if saved_id and saved_id not in edge_map:
                        edge_map[saved_id] = saved
                        report["key_relationships"].append(saved)
                        relationship_type = saved["relationship"].get("relationship_type")
                        if relationship_type in POLITICAL_RELATIONSHIPS:
                            report["political_relationships"].append(saved)
                        category = {"CONTRACT_WITH": "government_contracts",
                                    "RELATED_TO_JUDGMENT": "judgments",
                                    "RELATED_TO_PENALTY": "penalties"}.get(relationship_type)
                        if category:
                            report[category].append(saved)
            elif item.get("item_type") == "SOURCE":
                saved_sources.append({
                    "id": f"workspace-source:{item.get('id')}",
                    "source": item.get("title") or "Workspace source",
                    "source_name": item.get("title") or "Workspace source",
                    "source_url": item.get("source_url"),
                    "retrieved_at": item.get("created_at"),
                    "workspace_item_id": item.get("id"),
                })
        sources = _source_map(report)
        sources.update({source["id"]: source for source in saved_sources})
        report["sources"] = list(sources.values())
        for key in ("entity_profiles", "company_registry", "key_relationships", "political_relationships",
                    "government_contracts", "judgments", "penalties", "asset_records"):
            unique = {}
            for row in report[key]:
                row_id = row.get("relationship", {}).get("id") or row.get("id") or row.get("uniform_number")
                if row_id:
                    unique[row_id] = row
            report[key] = list(unique.values())
        report["relationship_graph"]["edges"] = list(edge_map.values())
        return report


def _safe_url(value):
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    return value if parsed.scheme in ("http", "https") and parsed.netloc else None


def render_report_html(report):
    from src.report_presentation import present_report

    view = present_report(report)

    def fact_html(label, value):
        url = _safe_url(value) if "URL" in label else None
        shown = (f'<a href="{escape(url, quote=True)}" rel="noreferrer">{escape(value)}</a>'
                 if url else escape(value))
        return f'<div class="report-field"><dt>{escape(label)}</dt><dd>{shown}</dd></div>'

    sections = "".join(
        f'<section id="{escape(section["key"])}"><div class="section-head"><h2>{escape(section["title"])}</h2>'
        f'<span>{len(section["items"])} 筆 / records</span></div>'
        + "".join(f'<article><h3>{escape(item["title"])}</h3><dl>'
                  + "".join(fact_html(label, value) for label, value in item["facts"])
                  + '</dl></article>' for item in section["items"]) + '</section>'
        for section in view["sections"])
    summary = "".join(f'<div><b>{value}</b><span>{escape(label)}</span></div>'
                      for label, value in view["summary"].items())
    warnings = "".join(f'<p class="warning">{escape(message)}</p>' for message in view["warnings"])
    empty = (f'<section class="coverage"><h2>尚無已發布紀錄 / No published records</h2>'
             f'<p>{escape("、".join(view["empty"]))}</p></section>') if view["empty"] else ""
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{escape(report['title'])}</title><style>
*{{box-sizing:border-box}}html{{min-width:0}}body{{font:15px/1.55 system-ui,"Noto Sans TC",sans-serif;color:#17202a;max-width:1120px;margin:auto;padding:28px;background:#f5f7f9;overflow-wrap:break-word}}
header,section{{min-width:0;max-width:100%;background:white;border:1px solid #dce3e8;border-radius:10px;padding:18px;margin:12px 0}}header{{border-top:6px solid #285b81}}article{{min-width:0;padding:12px 0;border-top:1px solid #e4e9ed;break-inside:auto}}article:first-of-type{{border-top:0}}h1{{font-size:26px;margin:0 0 8px}}h2{{font-size:19px;margin:0}}h3{{font-size:15px;margin:0 0 8px}}.section-head{{display:flex;justify-content:space-between;align-items:baseline;gap:12px;border-bottom:1px solid #dce3e8;padding-bottom:8px}}.section-head span{{color:#5c6975;white-space:nowrap}}
.summary{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:16px 0}}.summary div{{padding:10px;border-radius:7px;background:#edf3f7}}.summary b,.summary span{{display:block}}.summary b{{font-size:22px}}.summary span{{color:#5c6975}}.warning{{border-left:3px solid #b97029;padding-left:9px;color:#744516}}.meta{{color:#5c6975}}
dl{{display:block;min-width:0;margin:4px 0}}.report-field{{display:grid;grid-template-columns:minmax(145px,23%) minmax(0,1fr);gap:12px;min-width:0;padding:4px 0}}dt{{color:#5c6975;overflow-wrap:break-word}}dd{{min-width:0;margin:0;overflow-wrap:anywhere;word-break:normal;white-space:pre-wrap}}a{{color:#1769aa;overflow-wrap:anywhere}}@media(max-width:640px){{body{{padding:12px}}.summary{{grid-template-columns:1fr 1fr}}.report-field{{grid-template-columns:minmax(0,1fr);gap:2px}}}}
@page{{size:A4 landscape;margin:12mm}}@media print{{html,body{{width:auto;max-width:none;margin:0;padding:0;background:white;font-size:10pt}}header,section{{border-color:#dce3e8;margin:0 0 7mm;padding:4mm;break-inside:auto}}article{{break-inside:auto}}h1,h2,h3,dt{{break-after:avoid-page}}.report-field{{break-inside:avoid-page;page-break-inside:avoid}}a{{color:#1769aa;text-decoration:underline}}}}
</style></head><body><header><h1>{escape(report['title'])}</h1>
<p>{escape(report['methodology'])}</p><p class="meta">產生時間 / Generated at: {escape(report['generated_at'])} · 類型 / Type: {escape(report['report_type'])}</p>
<div class="summary">{summary}</div>{warnings}</header>{sections}{empty}</body></html>"""


def dispatch_report_api(path, query, authorization=None, service=None):
    parts = path.strip("/").split("/")
    if len(parts) != 5 or parts[:3] != ["api", "v1", "reports"]:
        return 404, {"error": "Not found / 找不到端點"}, None
    scope = parts[3]
    try:
        record_id = parts[4] if scope == "company" else uuid_string(parts[4])
        output_format = query.get("format", ["json"])[0]
        if scope not in ("entity", "politician", "workspace", "company") or output_format not in ("json", "html", "pdf"):
            raise ReportValidationError("Invalid report request")
        service = service or ReportService()
        if scope == "workspace":
            token = access_token_from_header(authorization)
            report = service.workspace_report(record_id, token)
        else:
            report = getattr(service, f"{scope}_report")(record_id)
    except EmptyWorkspaceReport:
        return 422, {"error": "Workspace 尚無收藏項目；請先收藏再匯出 / Save an item before exporting",
                     "status": "empty_workspace"}, None
    except (ReportValidationError, ValueError, TypeError):
        return 400, {"error": "報告參數錯誤 / Invalid report parameters"}, None
    except WorkspaceUnauthorized:
        return 401, {"error": "請先登入 / Authentication required"}, None
    except ReportNotFound:
        return 404, {"error": "找不到可發布的報告資料 / Report source not found"}, None
    except (EntityStoreUnavailable, WorkspaceStoreUnavailable):
        return 503, {"status": "unavailable", "error": "報告資料暫時無法使用 / Report data unavailable"}, None
    if output_format == "html":
        return 200, render_report_html(report), "text/html; charset=utf-8"
    if output_format == "pdf":
        from src.report_pdf import render_report_pdf
        return 200, render_report_pdf(report), "application/pdf"
    return 200, response(report), None
