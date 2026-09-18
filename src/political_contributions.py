"""Exact-ID adapter for Control Yuan political-contribution records.

The adapter only links an already-resolved Company and Politician. It never
falls back to donor or candidate names, and all output remains draft for review.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
import unicodedata

from src.entities.models import evidence_from_projection, stable_id, timestamp
from src.relationships.models import Relationship

SOURCE_NAME = "監察院政治獻金公開查閱平臺"
SOURCE_URL = "https://ardata.cy.gov.tw/"


def _entity_value(entity, key):
    return entity.get(key) if isinstance(entity, dict) else getattr(entity, key)


def _uniform_number(value):
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not re.fullmatch(r"[0-9]{8}", normalized):
        raise ValueError("A Taiwan company uniform number must contain exactly eight digits")
    return normalized


def _money(value):
    amount = Decimal(str(value).replace(",", ""))
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Contribution amount must be positive and finite")
    return format(amount, "f")


def build_political_contribution_bundle(rows, *, companies_by_uniform,
                                        politicians_by_source_id, retrieved_at):
    """Project allowlisted source rows into Evidence and Company→Politician edges."""
    retrieved = timestamp(retrieved_at)
    companies = {}
    for key, entity in companies_by_uniform.items():
        companies[_uniform_number(key)] = entity
    bundle = {"entities": [], "identifiers": [], "evidence": [], "entity_evidence": [],
              "relationships": [], "relationship_evidence": [], "legacy_map": []}
    report = {"skipped": [], "match_method": "exact_uniform_number",
              "publication_status": "draft"}
    for row in rows:
        record_id = row.get("source_record_id")
        try:
            uniform = _uniform_number(row.get("donor_uniform_number"))
            company = companies.get(uniform)
            politician = politicians_by_source_id.get(str(row.get("politician_source_id") or ""))
            if company is None:
                raise LookupError("unmatched_company_uniform_number")
            if politician is None:
                raise LookupError("unmatched_politician_source_id")
            if _entity_value(company, "entity_type") != "Company":
                raise ValueError("resolved donor must be a Company")
            if _entity_value(politician, "entity_type") != "Politician":
                raise ValueError("resolved recipient must be a Politician")
            if not isinstance(record_id, str) or not record_id.strip():
                raise ValueError("source record ID is required")
            contribution_date = date.fromisoformat(str(row.get("date"))).isoformat()
            amount = _money(row.get("amount"))
            contribution_type = str(row.get("contribution_type") or "").strip()
            if not contribution_type:
                raise ValueError("contribution type is required")
            observed = f"{contribution_date}T00:00:00+00:00"
            locator = {
                "dataset": str(row.get("dataset") or "political_contribution_public_platform"),
                "filing_id": str(row.get("filing_id") or ""),
                "source_record_id": record_id,
                "match_method": "exact_uniform_number",
                "uniform_number": uniform,
            }
            evidence = evidence_from_projection(
                source_name=SOURCE_NAME, source_record_id=record_id,
                source_class="Government Open Data",
                source_url=row.get("source_url") or SOURCE_URL,
                source_locator=locator,
                title=f"政治獻金 / Political contribution：{_entity_value(company, 'display_name')}",
                summary=(f"{_entity_value(company, 'display_name')} → "
                         f"{_entity_value(politician, 'display_name')}；{amount} TWD；"
                         f"{contribution_type}；{contribution_date}"),
                observed_at=observed, retrieved_at=retrieved)
            relationship = Relationship(
                id=stable_id("relationship", "political_contribution",
                             f"{record_id}:{evidence.content_hash}"),
                source_entity_id=_entity_value(company, "id"),
                target_entity_id=_entity_value(politician, "id"),
                relationship_type="POLITICAL_CONTRIBUTION_TO",
                primary_evidence_id=evidence.id, observed_at=observed,
                confidence="EXACT", start_date=contribution_date,
                date_precision="day", amount=amount, currency="TWD",
                source_role=contribution_type)
        except LookupError as exc:
            report["skipped"].append({"source_record_id": record_id, "reason": str(exc)})
            continue
        except (InvalidOperation, TypeError, ValueError, KeyError):
            report["skipped"].append({"source_record_id": record_id,
                                      "reason": "invalid_source_fields"})
            continue
        bundle["evidence"].append(evidence.to_dict())
        bundle["relationships"].append(relationship.to_dict())
        bundle["relationship_evidence"].append({
            "relationship_id": relationship.id,
            "evidence_id": evidence.id,
            "support_type": "supports",
        })
    for key in ("evidence", "relationships"):
        bundle[key] = list({item["id"]: item for item in bundle[key]}.values())
    bundle["relationship_evidence"] = list({
        (item["relationship_id"], item["evidence_id"]): item
        for item in bundle["relationship_evidence"]
    }.values())
    report["counts"] = {key: len(value) for key, value in bundle.items()}
    return bundle, report
