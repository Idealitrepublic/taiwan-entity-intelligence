"""Conservative legacy snapshot adapter. Output is always draft, never auto-published."""
from decimal import Decimal, InvalidOperation
from .models import evidence_from_projection, stable_id, timestamp
from .resolution import company_entity, person_observation
from src.relationships.models import Relationship

# Supervisors are preserved as source roles, not silently reclassified as directors.
DIRECTOR_ROLES = {"董事", "董事長", "副董事長", "獨立董事", "常務董事"}
OFFICER_ROLES = {"經理人", "總經理", "經理"}


def build_legacy_bundle(snapshot):
    bundle = {key: [] for key in ("entities", "identifiers", "evidence", "entity_evidence",
              "relationships", "relationship_evidence", "legacy_map")}
    report = {"skipped": [], "person_identity": "source_scoped", "publication_status": "draft"}
    companies = {}
    for row in snapshot.get("companies", []):
        try:
            entity = company_entity(row["uniform_number"], row["name"])
            observed = timestamp(row["fetched_at"])
            evidence = evidence_from_projection(
                source_name=row.get("source") or "MOEA/GCI", source_record_id=f"company:{row['uniform_number']}",
                source_class="Official Registry", source_url=row.get("source_url"),
                source_locator={"dataset": "company_registry", "uniform_number": row["uniform_number"]},
                title=f"公司登記 / Company registration：{entity.display_name}",
                summary=f"統一編號 / Uniform number：{row['uniform_number']}",
                observed_at=observed, retrieved_at=observed)
        except (ValueError, TypeError, KeyError):
            report["skipped"].append({"kind": "company", "id": row.get("id"), "reason": "invalid_source_fields"})
            continue
        companies[str(row["id"])] = entity
        bundle["entities"].append(entity.to_dict())
        bundle["evidence"].append(evidence.to_dict())
        bundle["identifiers"].append({"entity_id": entity.id, "namespace": "tw:uniform_number", "value": row["uniform_number"]})
        bundle["entity_evidence"].append({"entity_id": entity.id, "evidence_id": evidence.id, "fact_type": "company_registration"})
        bundle["legacy_map"].append({"legacy_namespace": "companies", "legacy_id": str(row["id"]), "entity_id": entity.id})
    for row in snapshot.get("company_people", []):
        company = companies.get(str(row.get("company_id")))
        role = (row.get("role") or "").strip()
        relationship_type = "DIRECTOR_OF" if role in DIRECTOR_ROLES else "OFFICER_OF" if role in OFFICER_ROLES else None
        if not company or not relationship_type:
            report["skipped"].append({"kind": "company_people", "id": row.get("id"), "reason": "missing_company_or_unmapped_role"})
            continue
        try:
            if row.get("id") is None:
                raise ValueError("Missing stable legacy record ID")
            person = person_observation(company.id, str(row["id"]), row["person_name"])
            observed = timestamp(row["fetched_at"])
            quantity = None
            if row.get("share_count") is not None:
                try:
                    amount = Decimal(str(row["share_count"]))
                    if not amount.is_finite() or amount < 0:
                        raise ValueError("Invalid share quantity")
                    quantity = str(amount)
                except (InvalidOperation, ValueError):
                    report["skipped"].append({"kind": "holding", "id": row["id"], "reason": "invalid_quantity"})
            evidence = evidence_from_projection(
                source_name=row.get("source") or "MOEA/GCI",
                source_record_id=f"legacy:company_people:{row['id']}", source_class="Official Registry",
                source_url=row.get("source_url"), source_locator={"dataset": "company_directors",
                    "uniform_number": company.source_id, "legacy_record_id": str(row["id"])},
                title=f"{role} / Registered role：{person.display_name}",
                summary=f"{company.display_name}；{role}；{person.display_name}"
                    + (f"；登記股數 / Registered shares：{quantity}" if quantity is not None else ""),
                observed_at=observed, retrieved_at=observed)
            relationship = Relationship(
                id=stable_id("relationship", "legacy:company_people", f"{row['id']}:{evidence.content_hash}"),
                source_entity_id=person.id, target_entity_id=company.id,
                relationship_type=relationship_type, primary_evidence_id=evidence.id,
                observed_at=observed, confidence="HIGH", source_role=role,
                quantity=quantity, quantity_unit="shares" if quantity is not None else None)
        except (ValueError, TypeError, KeyError):
            report["skipped"].append({"kind": "company_people", "id": row.get("id"), "reason": "invalid_source_fields"})
            continue
        # Registered shares retain their unit; they are not an inferred ownership edge.
        bundle["entities"].append(person.to_dict())
        bundle["evidence"].append(evidence.to_dict())
        bundle["relationships"].append(relationship.to_dict())
        bundle["entity_evidence"].append({"entity_id": person.id, "evidence_id": evidence.id, "fact_type": "registered_role_observation"})
        bundle["legacy_map"].append({"legacy_namespace": "company_people:person_observation", "legacy_id": str(row["id"]), "entity_id": person.id})
    # Repeated source rows in an export must not generate duplicate entities.
    for key in ("entities", "evidence", "relationships"):
        bundle[key] = list({row["id"]: row for row in bundle[key]}.values())
    report["counts"] = {key: len(value) for key, value in bundle.items()}
    return bundle, report
