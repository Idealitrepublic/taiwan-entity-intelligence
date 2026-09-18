"""Deterministic, read-only investigation report projection and rendering."""
from datetime import datetime, timezone
from html import escape
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
MAX_WORKSPACE_ROOTS = 5
POLITICAL_RELATIONSHIPS = {
    "POLITICAL_CONTRIBUTION_TO", "MEMBER_OF", "LEGISLATOR_OF",
    "COMMITTEE_MEMBER", "PROPOSED_BILL", "CO_SPONSORED_BILL",
    "GOVERNMENT_POSITION",
}
SECTION_TITLES = (
    ("entity_profiles", "Entity Profile / 實體概況"),
    ("key_relationships", "Key Relationships / 關鍵關係"),
    ("political_relationships", "Political Relationships / 政治關係"),
    ("government_contracts", "Government Contracts / 政府標案"),
    ("judgments", "Judgments / 判決"),
    ("penalties", "Penalties / 裁罰"),
    ("asset_records", "Asset Records / 財產申報"),
    ("relationship_graph", "Relationship Graph / 關係圖"),
    ("sources", "Sources / 來源"),
)


class ReportNotFound(RuntimeError):
    pass


class ReportValidationError(ValueError):
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

    def _entity_report(self, entity_id, report_type="ENTITY"):
        entity_id = uuid_string(entity_id)
        entity = self.entities.entity(entity_id)
        if not entity:
            raise ReportNotFound("Published Entity not found")
        if report_type == "POLITICIAN" and entity.get("entity_type") != "Politician":
            raise ReportNotFound("Published Politician not found")

        graph = self.entities.graph_neighbors(entity_id, limit=MAX_GRAPH_RELATIONSHIPS)
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
        if politician:
            profile["politician_profile"] = _normalize_evidence_tree(politician)

        report = {
            "report_version": REPORT_VERSION,
            "report_type": report_type,
            "generated_at": self.clock(),
            "title": f"T.E.I. Investigation Report — {entity.get('display_name') or entity.get('canonical_name') or entity_id}",
            "methodology": (
                "Objective compilation of published, evidence-backed records. "
                "No finding of illegality, conflict of interest, or improper benefit is made."),
            "coverage": {
                "relationship_limit": MAX_GRAPH_RELATIONSHIPS,
                "relationship_truncated": bool(graph.get("has_more")),
                "asset_limit": MAX_GRAPH_RELATIONSHIPS,
            },
            "entity_profiles": [profile],
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
        return report

    def entity_report(self, entity_id):
        return self._entity_report(entity_id)

    def politician_report(self, entity_id):
        return self._entity_report(entity_id, "POLITICIAN")

    def workspace_report(self, workspace_id, access_token):
        workspace_id = uuid_string(workspace_id)
        workspace = self.workspace_factory(access_token).get(workspace_id)
        if not workspace:
            raise ReportNotFound("Owned Workspace not found")
        items = workspace.get("items", [])
        roots = []
        for item in items:
            root = item.get("entity_id") or item.get("graph_root_entity_id")
            if root and root not in roots:
                roots.append(root)
        child_reports = [self._entity_report(root) for root in roots[:MAX_WORKSPACE_ROOTS]]
        report = {
            "report_version": REPORT_VERSION,
            "report_type": "WORKSPACE",
            "generated_at": self.clock(),
            "title": f"T.E.I. Investigation Workspace — {workspace.get('name') or workspace_id}",
            "methodology": (
                "Owner-scoped compilation of saved items and published evidence-backed records. "
                "No automated judgment or conclusion is included."),
            "coverage": {
                "workspace_item_limit": 200,
                "workspace_items_truncated": bool(workspace.get("items_has_more")),
                "entity_root_limit": MAX_WORKSPACE_ROOTS,
                "entity_roots_truncated": len(roots) > MAX_WORKSPACE_ROOTS,
            },
            "workspace": {key: value for key, value in workspace.items() if key != "items"},
            "workspace_items": items,
            "entity_profiles": [], "key_relationships": [],
            "political_relationships": [], "government_contracts": [],
            "judgments": [], "penalties": [], "asset_records": [],
            "relationship_graph": {"nodes": [], "edges": [], "truncated": False},
            "sources": [],
        }
        node_map, edge_map = {}, {}
        for child in child_reports:
            for key in ("entity_profiles", "key_relationships", "political_relationships",
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
        report["relationship_graph"].update(
            nodes=list(node_map.values()), edges=list(edge_map.values()))
        saved_sources = []
        for item in items:
            if item.get("item_type") == "EVIDENCE" and item.get("evidence_id"):
                evidence = _evidence(self.entities.evidence(item["evidence_id"]))
                if evidence:
                    saved_sources.append(evidence)
            elif item.get("item_type") == "RELATIONSHIP" and item.get("relationship_id"):
                relationship = self.entities.relationship(item["relationship_id"])
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
        report["relationship_graph"]["edges"] = list(edge_map.values())
        return report


def _safe_url(value):
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    return value if parsed.scheme in ("http", "https") and parsed.netloc else None


def _render_value(value, key=""):
    if value is None or value == "":
        return "<span class=empty>—</span>"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        if not value:
            return "<p class=empty>No published records / 目前無已發布紀錄</p>"
        return "".join(f"<article>{_render_value(item)}</article>" for item in value)
    if isinstance(value, dict):
        rows = []
        for child_key, child in value.items():
            if child_key in ("content_hash",):
                continue
            rows.append(
                f"<dt>{escape(str(child_key).replace('_', ' '))}</dt>"
                f"<dd>{_render_value(child, child_key)}</dd>")
        return f"<dl>{''.join(rows)}</dl>"
    url = _safe_url(value) if key == "source_url" else None
    text = escape(str(value))
    return f'<a href="{escape(url, quote=True)}" rel="noreferrer">{text}</a>' if url else text


def render_report_html(report):
    sections = "".join(
        f"<section><h2>{escape(title)}</h2>{_render_value(report.get(key))}</section>"
        for key, title in SECTION_TITLES)
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{escape(report['title'])}</title><style>
body{{font:15px/1.55 system-ui,sans-serif;color:#17202a;max-width:1040px;margin:auto;padding:32px;background:#f5f7f9}}
header,section,article{{background:white;border:1px solid #dce3e8;border-radius:10px;padding:18px;margin:14px 0}}
article{{background:#fafbfc}}h1{{font-size:26px}}h2{{font-size:19px;border-bottom:1px solid #e4e9ed;padding-bottom:8px}}
dl{{display:grid;grid-template-columns:minmax(150px,220px) 1fr;gap:6px 14px;margin:4px 0}}dt{{color:#5c6975}}dd{{margin:0;overflow-wrap:anywhere}}
a{{color:#1769aa}}.empty{{color:#71808e}}@media print{{body{{background:white;padding:0}}section,header,article{{break-inside:avoid}}}}
</style></head><body><header><h1>{escape(report['title'])}</h1>
<p>{escape(report['methodology'])}</p><dl><dt>Report type</dt><dd>{escape(report['report_type'])}</dd>
<dt>Generated at</dt><dd>{escape(report['generated_at'])}</dd><dt>Coverage</dt><dd>{_render_value(report['coverage'])}</dd></dl></header>
{sections}</body></html>"""


def dispatch_report_api(path, query, authorization=None, service=None):
    parts = path.strip("/").split("/")
    if len(parts) != 5 or parts[:3] != ["api", "v1", "reports"]:
        return 404, {"error": "Not found / 找不到端點"}, None
    scope = parts[3]
    try:
        record_id = uuid_string(parts[4])
        output_format = query.get("format", ["json"])[0]
        if scope not in ("entity", "politician", "workspace") or output_format not in ("json", "html"):
            raise ReportValidationError("Invalid report request")
        service = service or ReportService()
        if scope == "workspace":
            token = access_token_from_header(authorization)
            report = service.workspace_report(record_id, token)
        else:
            report = getattr(service, f"{scope}_report")(record_id)
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
    return 200, response(report), None
