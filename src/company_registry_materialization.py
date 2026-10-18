"""Publish an exact-ID MOEA company identity with registry Evidence only.

This never creates a person or cross-company Relationship from a name match.
"""
from datetime import datetime, timezone, timedelta
import re
import unicodedata
from urllib.parse import urlencode

from src.entities.models import Entity, evidence_from_projection, stable_id, timestamp
from src.entities.repository import MOEA_COMPANY_API


TAIWAN_TIME = timezone(timedelta(hours=8))


def _official_observed_at(value, retrieved_at):
    if not re.fullmatch(r"[0-9]{7}", str(value or "")):
        return retrieved_at
    year = int(str(value)[:3]) + 1911
    month = int(str(value)[3:5])
    day = int(str(value)[5:7])
    return datetime(year, month, day, tzinfo=TAIWAN_TIME).isoformat()


def build_registry_company_bundle(registry, *, uniform, expected_name, retrieved_at):
    """Require a unique, active official ID/name pair before publication."""
    if not re.fullmatch(r"[0-9]{8}", uniform):
        raise ValueError("An exact eight-digit company identifier is required")
    if not isinstance(registry, dict) or str(registry.get("Business_Accounting_NO")) != uniform:
        raise ValueError("Official registry identifier mismatch")
    name = str(registry.get("Company_Name") or "").strip()
    if not name or unicodedata.normalize("NFKC", name) != unicodedata.normalize("NFKC", expected_name):
        raise ValueError("Official registry company name mismatch")
    if registry.get("Company_Status_Desc") != "核准設立":
        raise ValueError("Only active registered companies are eligible for this batch")
    retrieved = timestamp(retrieved_at)
    observed = _official_observed_at(registry.get("Change_Of_Approval_Data"), retrieved)
    entity = Entity(stable_id("entity", "tw:uniform_number", uniform), "Company", name,
                    name, "MOEA/GCI", uniform, "EXACT", "published")
    source_url = MOEA_COMPANY_API + "?" + urlencode({
        "$format": "json", "$filter": f"Business_Accounting_NO eq {uniform}", "$top": "1"})
    evidence = evidence_from_projection(
        source_name="MOEA/GCI", source_record_id=uniform, source_class="Official Registry",
        source_url=source_url,
        source_locator={"dataset": "company_registry", "uniform_number": uniform,
                        "company_name": name, "company_status": "核准設立",
                        "registry_change_date": registry.get("Change_Of_Approval_Data") or None},
        title=f"公司登記 / Company registration：{name}",
        summary=f"統一編號 / Company ID：{uniform}；公司狀態 / Status：核准設立",
        observed_at=observed, retrieved_at=retrieved,
        publication_status="published")
    return {
        "entities": [entity.to_dict()],
        "identifiers": [{"entity_id": entity.id, "namespace": "tw:uniform_number", "value": uniform}],
        "evidence": [evidence.to_dict()],
        "entity_evidence": [{"entity_id": entity.id, "evidence_id": evidence.id,
                             "fact_type": "IDENTITY"}],
    }
