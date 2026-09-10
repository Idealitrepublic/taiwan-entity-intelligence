import unittest
from pathlib import Path
from unittest.mock import Mock

from app import dispatch
from src.entities.api import dispatch_entity_api
from src.entities.repository import EntityRepository

ROOT = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
REL = "33333333-3333-4333-8333-333333333333"
EVIDENCE = "44444444-4444-4444-8444-444444444444"


class GraphV2Tests(unittest.TestCase):
    def test_repository_batches_nodes_and_evidence_without_n_plus_one(self):
        calls = []

        def get(table, params):
            calls.append((table, params))
            self.assertEqual(table, "rpc/graph_entity_neighbors")
            return [{"focus_entity": {"id": ROOT, "entity_type": "Company"},
                     "relationship": {"id": REL, "source_entity_id": OTHER,
                                      "target_entity_id": ROOT,
                                      "primary_evidence_id": EVIDENCE,
                                      "relationship_type": "DIRECTOR_OF"},
                     "source_entity": {"id": OTHER, "entity_type": "Person"},
                     "target_entity": {"id": ROOT, "entity_type": "Company"},
                     "primary_evidence": {"id": EVIDENCE, "title": "董事登記"}}]

        graph = EntityRepository(transport=get).graph_neighbors(ROOT, limit=12)
        self.assertEqual(len(calls), 1)
        self.assertEqual({node["id"] for node in graph["nodes"]}, {ROOT, OTHER})
        self.assertEqual(graph["edges"][0]["primary_evidence"]["id"], EVIDENCE)
        self.assertEqual(calls[0][1], {"focus_id": ROOT, "result_limit": 12})

    def test_missing_primary_evidence_suppresses_edge(self):
        def get(table, params):
            return [{"focus_entity": {"id": ROOT},
                     "relationship": {"id": REL, "source_entity_id": ROOT,
                                      "target_entity_id": OTHER,
                                      "primary_evidence_id": EVIDENCE},
                     "source_entity": {"id": ROOT}, "target_entity": {"id": OTHER},
                     "primary_evidence": None}]
        self.assertEqual(EntityRepository(transport=get).graph_neighbors(ROOT)["edges"], [])

    def test_repository_trims_probe_row_and_exposes_cursor(self):
        def get(table, params):
            rows = []
            for index in range(3):
                relationship_id = f"33333333-3333-4333-8333-{index:012d}"
                rows.append({"focus_entity": {"id": ROOT},
                             "relationship": {"id": relationship_id,
                                              "source_entity_id": ROOT,
                                              "target_entity_id": OTHER,
                                              "primary_evidence_id": EVIDENCE},
                             "source_entity": {"id": ROOT}, "target_entity": {"id": OTHER},
                             "primary_evidence": {"id": EVIDENCE}})
            return rows
        graph = EntityRepository(transport=get).graph_neighbors(ROOT, limit=2)
        self.assertEqual(len(graph["edges"]), 2)
        self.assertTrue(graph["has_more"])
        self.assertEqual(graph["next_cursor"], graph["edges"][-1]["id"])

    def test_graph_api_validates_bounds_and_calls_repository(self):
        repo = Mock()
        repo.graph_neighbors.return_value = {"focus_entity_id": ROOT, "nodes": [], "edges": []}
        code, body, _ = dispatch_entity_api(
            f"/api/v1/graph/{ROOT}", {"limit": ["12"], "relationship_type": ["DIRECTOR_OF"]}, repo)
        self.assertEqual(code, 200)
        self.assertEqual(body["data"]["focus_entity_id"], ROOT)
        repo.graph_neighbors.assert_called_once_with(
            ROOT, limit=12, after=None, relationship_type="DIRECTOR_OF")
        for query in ({"limit": ["0"]}, {"limit": ["26"]},
                      {"relationship_type": ["ARBITRARY"]}, {"after": ["bad"]}):
            self.assertEqual(dispatch_entity_api(f"/api/v1/graph/{ROOT}", query, repo)[0], 400)

    def test_graph_api_returns_404_for_unpublished_root(self):
        repo = Mock()
        repo.graph_neighbors.return_value = None
        self.assertEqual(dispatch_entity_api(f"/api/v1/graph/{ROOT}", {}, repo)[0], 404)

    def test_shareable_entity_and_graph_routes_serve_html(self):
        for prefix in ("entity", "graph"):
            code, body, content_type = dispatch(f"/{prefix}/{ROOT}", {})
            self.assertEqual(code, 200)
            self.assertIn("text/html", content_type)
            self.assertIn("Taiwan Entity Intelligence", body)
        self.assertEqual(dispatch("/graph/not-a-uuid", {})[0], 404)

    def test_graph_ui_has_lazy_limits_filters_and_edge_evidence(self):
        html = (Path(__file__).parents[1] / "web" / "index.html").read_text()
        for token in ("GRAPH_PAGE_SIZE=12", "GRAPH_MAX_DEPTH=3", "GRAPH_MAX_NODES=60",
                      "expandKnowledgeNode", "showKnowledgeEdge", "relationshipFilter",
                      "關係證據 / Relationship evidence", "/api/v1/graph/"):
            self.assertIn(token, html)


if __name__ == "__main__":
    unittest.main()
