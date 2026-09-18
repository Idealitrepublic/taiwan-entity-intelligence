import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from app import app, dispatch
from src.reports import ReportNotFound, ReportService, dispatch_report_api, render_report_html

ENTITY = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
REL = "33333333-3333-4333-8333-333333333333"
EVIDENCE = "44444444-4444-4444-8444-444444444444"
WORKSPACE = "55555555-5555-4555-8555-555555555555"
TOKEN = "authenticated-user-token-for-report-tests"


def evidence(title="Official record"):
    return {"id": EVIDENCE, "source_name": "Official source",
            "source_url": "https://example.gov.tw/record", "retrieved_at": "2026-09-01T00:00:00Z",
            "title": title}


def entity(entity_type="Company"):
    return {"id": ENTITY, "entity_type": entity_type, "display_name": "測試實體",
            "canonical_name": "測試實體", "evidence": [{"fact_type": "IDENTITY", "evidence": evidence()}]}


def graph(relationship_type="CONTRACT_WITH"):
    return {"nodes": [entity(), {"id": OTHER, "entity_type": "GovernmentAgency",
                                  "display_name": "測試機關"}],
            "edges": [{"id": REL, "source": ENTITY, "target": OTHER,
                       "source_entity_id": ENTITY, "target_entity_id": OTHER,
                       "relationship_type": relationship_type,
                       "primary_evidence": evidence()}], "has_more": False}


class ReportTests(unittest.TestCase):
    def test_entity_report_has_all_sections_and_source_provenance(self):
        repository = Mock()
        repository.entity.return_value = entity()
        repository.graph_neighbors.return_value = graph()
        report = ReportService(repository, clock=lambda: "2026-09-17T00:00:00Z").entity_report(ENTITY)
        for key in ("entity_profiles", "key_relationships", "political_relationships",
                    "government_contracts", "judgments", "penalties", "asset_records",
                    "relationship_graph", "sources"):
            self.assertIn(key, report)
        self.assertEqual(len(report["government_contracts"]), 1)
        self.assertEqual(report["sources"][0]["source"], "Official source")
        self.assertEqual(report["sources"][0]["source_url"], "https://example.gov.tw/record")
        self.assertEqual(report["sources"][0]["retrieved_at"], "2026-09-01T00:00:00Z")
        repository.graph_neighbors.assert_called_once_with(ENTITY, limit=25)

    def test_politician_report_includes_assets_and_rejects_other_types(self):
        repository = Mock()
        repository.entity.return_value = entity("Politician")
        politician_graph = graph("POLITICAL_CONTRIBUTION_TO")
        politician_graph["nodes"][0] = entity("Politician")
        repository.graph_neighbors.return_value = politician_graph
        repository.politician_profile.return_value = {"entity": entity("Politician"), "terms": []}
        repository.asset_declarations.return_value = {"items": [{
            "id": OTHER, "asset_type": "STOCK", "amount": 1000,
            "primary_evidence": evidence("Asset declaration")}]}
        report = ReportService(repository).politician_report(ENTITY)
        self.assertEqual(len(report["political_relationships"]), 1)
        self.assertEqual(report["asset_records"][0]["source"], "Official source")
        repository.entity.return_value = entity("Company")
        with self.assertRaises(ReportNotFound):
            ReportService(repository).politician_report(ENTITY)

    def test_workspace_report_forwards_owner_token_and_includes_saved_sources(self):
        repository = Mock()
        repository.evidence.return_value = evidence("Saved evidence")
        repository.relationship.return_value = {
            "id": REL, "source_entity_id": ENTITY, "target_entity_id": OTHER,
            "relationship_type": "RELATED_TO_JUDGMENT", "primary_evidence_id": EVIDENCE,
            "evidence": [{"support_type": "supports", "evidence": evidence()}]}
        captured = []

        class Workspaces:
            def __init__(self, token):
                captured.append(token)

            def get(self, workspace_id):
                return {"id": workspace_id, "owner_user_id": OTHER, "name": "專案",
                        "items_has_more": False, "items": [
                            {"id": REL, "item_type": "EVIDENCE", "evidence_id": EVIDENCE},
                            {"id": ENTITY, "item_type": "RELATIONSHIP", "relationship_id": REL},
                            {"id": OTHER, "item_type": "SOURCE", "title": "人工來源",
                             "source_url": "https://example.org/source",
                             "created_at": "2026-09-02T00:00:00Z"}]}

        report = ReportService(repository, workspace_factory=Workspaces).workspace_report(
            WORKSPACE, TOKEN)
        self.assertEqual(captured, [TOKEN])
        self.assertEqual(report["workspace"]["owner_user_id"], OTHER)
        self.assertEqual({row["source"] for row in report["sources"]},
                         {"Official source", "人工來源"})
        self.assertEqual(report["judgments"][0]["relationship"]["id"], REL)

    def test_dispatch_validates_scope_format_and_workspace_auth(self):
        service = Mock()
        service.entity_report.return_value = {"title": "Report", "methodology": "facts",
                                              "report_type": "ENTITY", "generated_at": "now",
                                              "coverage": {}}
        code, body, _ = dispatch_report_api(
            f"/api/v1/reports/entity/{ENTITY}", {}, service=service)
        self.assertEqual((code, body["api_version"]), (200, "1"))
        self.assertEqual(dispatch_report_api(
            f"/api/v1/reports/workspace/{WORKSPACE}", {}, service=service)[0], 401)
        self.assertEqual(dispatch_report_api(
            f"/api/v1/reports/entity/{ENTITY}", {"format": ["pdf"]}, service=service)[0], 400)

    def test_html_is_readable_and_escapes_data(self):
        report = {"title": "<unsafe>", "methodology": "Facts only", "report_type": "ENTITY",
                  "generated_at": "now", "coverage": {}, **{key: [] for key in (
                      "entity_profiles", "key_relationships", "political_relationships",
                      "government_contracts", "judgments", "penalties", "asset_records",
                      "sources")}, "relationship_graph": {}}
        html = render_report_html(report)
        self.assertIn("Entity Profile / 實體概況", html)
        self.assertIn("Relationship Graph / 關係圖", html)
        self.assertIn("&lt;unsafe&gt;", html)
        self.assertNotIn("<unsafe>", html)

    def test_wsgi_routes_report_get_and_denies_write(self):
        self.assertEqual(dispatch(f"/api/v1/reports/entity/{ENTITY}", {}, method="POST")[0], 405)
        environ = {"REQUEST_METHOD": "GET", "PATH_INFO": f"/api/v1/reports/entity/{ENTITY}",
                   "QUERY_STRING": "format=html", "wsgi.input": io.BytesIO()}
        status, headers = [], []
        with patch("app.dispatch_report_api", return_value=(200, "<h1>Report</h1>", "text/html")):
            body = b"".join(app(environ, lambda value, values: (status.append(value), headers.extend(values))))
        self.assertEqual(status, ["200 OK"])
        self.assertEqual(body, b"<h1>Report</h1>")
        self.assertIn(("Content-Type", "text/html"), headers)

    def test_ui_exposes_entity_politician_and_workspace_exports(self):
        html = (Path(__file__).parents[1] / "web" / "index.html").read_text()
        for token in ("report-export", "workspaceReportView", "workspaceReportDownload",
                      "/api/v1/reports/", "data-report-download"):
            self.assertIn(token, html)


if __name__ == "__main__":
    unittest.main()
