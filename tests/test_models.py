import unittest

from src.models import EntityGraph, GraphEdge, GraphNode


class EntityGraphTests(unittest.TestCase):
    def test_deduplicates_nodes_and_edges(self):
        graph = EntityGraph()
        graph.add_node(GraphNode("company:1", "company", "Test"))
        graph.add_node(GraphNode("company:1", "company", "Test"))
        graph.add_edge(GraphEdge("company:1", "person:A", "director"))
        graph.add_edge(GraphEdge("company:1", "person:A", "director"))

        self.assertEqual(len(graph.nodes), 1)
        self.assertEqual(len(graph.edges), 1)


if __name__ == "__main__":
    unittest.main()
