"""Small, dependency-free data models used by the MVP."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Company:
    uniform_number: str
    name: str
    status: Optional[str] = None
    representative: Optional[str] = None
    capital: Optional[Any] = None
    address: Optional[str] = None
    setup_date: Optional[str] = None


@dataclass
class Person:
    name: str
    position: Optional[str] = None
    representative: Optional[str] = None
    shares: Optional[Any] = None


@dataclass
class Tender:
    tender_id: Optional[str] = None
    name: Optional[str] = None
    agency: Optional[str] = None
    award_date: Optional[str] = None
    amount: Optional[Any] = None
    winner: Optional[str] = None


@dataclass
class GraphNode:
    id: str
    type: str
    label: str
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    source: str
    target: str
    relationship: str
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EntityGraph:
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)

    def add_node(self, node: GraphNode) -> None:
        if not any(n.id == node.id for n in self.nodes):
            self.nodes.append(node)

    def add_edge(self, edge: GraphEdge) -> None:
        if not any(
            e.source == edge.source
            and e.target == edge.target
            and e.relationship == edge.relationship
            for e in self.edges
        ):
            self.edges.append(edge)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [
                {
                    "id": n.id,
                    "type": n.type,
                    "label": n.label,
                    "properties": n.properties,
                }
                for n in self.nodes
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "relationship": e.relationship,
                    "properties": e.properties,
                }
                for e in self.edges
            ],
        }
