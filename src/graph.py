"""Build a bounded, explainable company relationship graph."""

from typing import Dict, Any

from .models import EntityGraph, GraphEdge, GraphNode
from .repository import (
    company_people,
    person_companies,
    company_tenders,
    materialize_company_evidence,
    evidence_for_entity,
)


def company_graph(conn, uniform_number: str) -> Dict[str, Any]:
    people = company_people(conn, uniform_number)
    graph = EntityGraph()

    company_name = people[0]["company_name"] if people else uniform_number
    company_node_id = "company:{}".format(uniform_number)
    graph.add_node(GraphNode(
        id=company_node_id,
        type="company",
        label=company_name,
        properties={"uniform_number": uniform_number},
    ))

    # Materialize only facts already present in local source tables.
    materialize_company_evidence(conn, uniform_number, company_name)

    seen_people = set()
    seen_companies = {uniform_number}

    for person in people:
        person_name = person.get("person_name")
        if not person_name:
            continue
        person_id = "person:{}".format(person_name)
        graph.add_node(GraphNode(
            id=person_id,
            type="person",
            label=person_name,
            properties={
                "position": person.get("position"),
                "representative": person.get("representative"),
                "shares": person.get("shares"),
            },
        ))
        evidence = evidence_for_entity(conn, company_node_id, 200)
        evidence_ids = [
            e["evidence_id"] for e in evidence
            if e.get("target_entity_id") == person_id
        ]
        graph.add_edge(GraphEdge(
            source=company_node_id,
            target=person_id,
            relationship=person.get("position") or "director_relationship",
            properties={
                "source": "company_directors",
                "evidence_ids": evidence_ids,
                "evidence_count": len(evidence_ids),
            },
        ))

        if person_name in seen_people:
            continue
        seen_people.add(person_name)

        for other in person_companies(conn, person_name):
            other_id = other.get("uniform_number")
            other_name = other.get("company_name")
            if not other_id or not other_name or other_id in seen_companies:
                continue
            seen_companies.add(other_id)
            other_node_id = "company:{}".format(other_id)
            graph.add_node(GraphNode(
                id=other_node_id,
                type="company",
                label=other_name,
                properties={"uniform_number": other_id},
            ))
            graph.add_edge(GraphEdge(
                source=person_id,
                target=other_node_id,
                relationship=other.get("position") or "director_relationship",
                properties={"source": "company_directors"},
            ))

    for tender in company_tenders(conn, company_name):
        tender_id = tender.get("tender_id") or tender.get("案號") or tender.get("標案編號") or tender.get("id")
        tender_name = tender.get("tender_name") or tender.get("標案名稱") or tender.get("案名") or str(tender_id or "Tender")
        if not tender_id:
            continue
        tender_node_id = "tender:{}".format(tender_id)
        graph.add_node(GraphNode(
            id=tender_node_id,
            type="tender",
            label=tender_name,
            properties=tender,
        ))
        evidence = evidence_for_entity(conn, company_node_id, 200)
        evidence_ids = [
            e["evidence_id"] for e in evidence
            if e.get("target_entity_id") == tender_node_id
        ]
        graph.add_edge(GraphEdge(
            source=company_node_id,
            target=tender_node_id,
            relationship="tender_winner",
            properties={
                "source": "local_tender_database",
                "evidence_ids": evidence_ids,
                "evidence_count": len(evidence_ids),
            },
        ))

    return graph.to_dict()
