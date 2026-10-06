import unittest
from pathlib import Path
from unittest.mock import Mock

from src.entities.api import dispatch_entity_api
from src.entities.repository import (
    EntityFeatureUnavailable,
    EntityRepository,
    EntityStoreUnavailable,
)

SOURCE = "11111111-1111-4111-8111-111111111111"
TARGET = "22222222-2222-4222-8222-222222222222"


class RelationshipPathTests(unittest.TestCase):
    def test_repository_uses_one_bounded_rpc(self):
        calls = []

        def get(table, params):
            calls.append((table, params))
            return [{"path_result": {"found": True, "depth": 2, "segments": []}}]

        result = EntityRepository(transport=get).relationship_path(SOURCE, TARGET, max_depth=2)
        self.assertTrue(result["found"])
        self.assertEqual(calls, [("rpc/find_entity_relationship_path", {
            "start_entity_id": SOURCE, "end_entity_id": TARGET, "max_depth": 2})])

    def test_repository_rejects_malformed_rpc_result(self):
        with self.assertRaises(EntityStoreUnavailable):
            EntityRepository(transport=lambda *_: [{"path_result": None}]).relationship_path(
                SOURCE, TARGET)

    def test_repository_falls_back_to_bounded_graph_for_older_schema(self):
        def get(table, params):
            if table == "rpc/find_entity_relationship_path":
                raise EntityFeatureUnavailable("not installed")
            focus = params["focus_id"]
            if focus == TARGET:
                return [{"focus_entity": {"id": TARGET, "display_name": "B"},
                         "relationship": None}]
            return [{"focus_entity": {"id": SOURCE, "display_name": "A"},
                     "relationship": {"id": "33333333-3333-4333-8333-333333333333",
                                      "source_entity_id": SOURCE,
                                      "target_entity_id": TARGET,
                                      "relationship_type": "DIRECTOR_OF"},
                     "source_entity": {"id": SOURCE, "display_name": "A"},
                     "target_entity": {"id": TARGET, "display_name": "B"},
                     "primary_evidence": {"id": "44444444-4444-4444-8444-444444444444",
                                          "source_name": "fixture"}}]

        result = EntityRepository(transport=get).relationship_path(SOURCE, TARGET)
        self.assertTrue(result["found"])
        self.assertEqual(result["depth"], 1)
        self.assertEqual(result["backend"], "graph_neighbors_fallback")
        self.assertEqual(result["segments"][0]["traversal_direction"], "forward")

    def test_api_validates_endpoints_and_depth(self):
        repo = Mock()
        repo.relationship_path.return_value = {"found": False, "depth": None, "segments": []}
        code, body, _ = dispatch_entity_api("/api/v1/paths", {
            "source": [SOURCE], "target": [TARGET], "max_depth": ["3"]}, repo)
        self.assertEqual(code, 200)
        self.assertFalse(body["data"]["found"])
        repo.relationship_path.assert_called_once_with(SOURCE, TARGET, max_depth=3)
        for query in ({}, {"source": [SOURCE], "target": [SOURCE]},
                      {"source": [SOURCE], "target": [TARGET], "max_depth": ["0"]},
                      {"source": [SOURCE], "target": [TARGET], "max_depth": ["4"]}):
            self.assertEqual(dispatch_entity_api("/api/v1/paths", query, repo)[0], 400)

    def test_fallback_depths_preserve_shortest_path_and_edge_evidence(self):
        nodes = [SOURCE, TARGET, "55555555-5555-4555-8555-555555555555",
                 "66666666-6666-4666-8666-666666666666"]
        edges = [{"id": f"33333333-3333-4333-8333-{index:012d}",
                  "source_entity_id": nodes[index], "target_entity_id": nodes[index + 1],
                  "relationship_type": "MEMBER_OF", "primary_evidence_id": TARGET}
                 for index in range(3)]

        def get(table, params):
            if table == "rpc/find_entity_relationship_path":
                raise EntityFeatureUnavailable("not installed")
            focus = params["focus_id"]
            return [{"focus_entity": {"id": focus}, "relationship": edge,
                     "source_entity": {"id": edge["source_entity_id"]},
                     "target_entity": {"id": edge["target_entity_id"]},
                     "primary_evidence": {"id": TARGET,
                                          "source_url": "https://official.example/record",
                                          "retrieved_at": "2026-10-07T00:00:00Z"}}
                    for edge in edges
                    if focus in (edge["source_entity_id"], edge["target_entity_id"])]

        for depth in (1, 2, 3):
            with self.subTest(depth=depth):
                result = EntityRepository(transport=get).relationship_path(
                    nodes[0], nodes[3], max_depth=depth)
                self.assertEqual(result["found"], depth == 3)
                self.assertEqual(len(result["segments"]), 3 if depth == 3 else 0)
                if depth == 3:
                    self.assertTrue(all(segment["evidence"]["retrieved_at"]
                                        for segment in result["segments"]))

    def test_fallback_cycles_and_reverse_edges_do_not_duplicate_nodes(self):
        def get(table, params):
            if table == "rpc/find_entity_relationship_path":
                raise EntityFeatureUnavailable("not installed")
            return [{"focus_entity": {"id": params["focus_id"]},
                     "relationship": {"id": SOURCE, "source_entity_id": TARGET,
                                      "target_entity_id": SOURCE,
                                      "primary_evidence_id": TARGET},
                     "source_entity": {"id": TARGET}, "target_entity": {"id": SOURCE},
                     "primary_evidence": {"id": TARGET}}]

        result = EntityRepository(transport=get).relationship_path(SOURCE, TARGET, max_depth=3)
        self.assertEqual(result["depth"], 1)
        self.assertEqual(result["segments"][0]["traversal_direction"], "reverse")

    def test_api_returns_404_when_an_endpoint_is_not_public(self):
        repo = Mock()
        repo.relationship_path.return_value = None
        self.assertEqual(dispatch_entity_api("/api/v1/paths", {
            "source": [SOURCE], "target": [TARGET]}, repo)[0], 404)

    def test_ui_exposes_two_endpoint_path_finder_and_evidence(self):
        html = (Path(__file__).parents[1] / "web" / "index.html").read_text()
        for token in ("pathSource", "pathTarget", "findRelationshipPath",
                      "/api/v1/paths", "traversal_direction",
                      "原始來源 / Original source", "最多 2 個中介 / Up to 2 intermediaries"):
            self.assertIn(token, html)


if __name__ == "__main__":
    unittest.main()
