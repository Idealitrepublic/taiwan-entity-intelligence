"""Materialize existing MOL records only with explicit, registry-verified IDs."""
from datetime import datetime
import re
import unicodedata

from src.entities.models import Entity, evidence_from_projection, stable_id


def explicit_company_identifier(record):
    raw = record.get("raw") or {}
    values = [record.get("uniform_number")]
    values.extend(raw.get(key) for key in ("統一編號", "統編", "Business_Accounting_NO"))
    label = unicodedata.normalize("NFKC", str(raw.get("事業單位名稱或負責人") or ""))
    # Only a separated terminal identifier; HTML numeric references and case numbers
    # are not company identifiers. Never extract an arbitrary eight-digit substring.
    terminal = re.search(r"(?:\t|統一編號\s*[:：]?|統編\s*[:：]?)\s*([0-9]{8})\s*$", label)
    if terminal:
        values.append(terminal.group(1))
    identifiers = {unicodedata.normalize("NFKC", str(v)).strip() for v in values if v}
    if len(identifiers) != 1:
        return None
    value = identifiers.pop()
    return value if re.fullmatch(r"[0-9]{8}", value) else None


def _date(value):
    value = str(value).strip()
    if not re.fullmatch(r"[0-9]{8}", value):
        raise ValueError("Official disposition date required")
    return datetime.strptime(value, "%Y%m%d").date().isoformat()


def build_penalty_bundle(record, registry, *, registry_retrieved_at, company_entity_id=None):
    uniform = explicit_company_identifier(record)
    if not uniform or str(registry.get("Business_Accounting_NO")) != uniform:
        raise ValueError("Explicit MOL identifier and exact MOEA confirmation required")
    name = str(registry.get("Company_Name") or "").strip()
    label = unicodedata.normalize("NFKC", str(record["raw"].get("事業單位名稱或負責人") or ""))
    labor_name = re.split(r"[\t(（]|統一編號|統編", label, maxsplit=1)[0].strip()
    if not name or unicodedata.normalize("NFKC", name) != labor_name:
        raise ValueError("Registry name conflicts with the source identity; review required")
    raw = record["raw"]
    day = _date(raw.get("處分日期"))
    observed = day + "T00:00:00+08:00"
    retrieved = record.get("indexed_at")
    if not record.get("source_file_id") or not record.get("source_url") or not retrieved:
        raise ValueError("Indexed source provenance required")
    company_id = company_entity_id or stable_id("entity", "tw:uniform_number", uniform)
    penalty_id = stable_id("entity", "MOL/penalties", record["id"])
    registry_evidence = evidence_from_projection(
        source_name="MOEA/GCI", source_record_id=uniform, source_class="Official Registry",
        source_url="https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6",
        source_locator={"uniform_number": uniform, "company_name": name,
                        "query": {"Business_Accounting_NO": uniform}},
        title=name, summary="經濟部公司統編與正式名稱確認", observed_at=registry_retrieved_at,
        retrieved_at=registry_retrieved_at, publication_status="published").to_dict()
    penalty_evidence = evidence_from_projection(
        source_name="MOL/penalties", source_record_id=record["id"],
        source_class="Government Open Data", source_url=record["source_url"],
        source_locator={"source_record_id": record["id"], "source_file_id": record["source_file_id"],
                        "match_method": "explicit_uniform_number_verified_moea",
                        "uniform_number": uniform, "disposition_number": raw.get("處分字號"),
                        "authority": raw.get("主管機關"), "disposition_date": day,
                        "source_company_label": raw.get("事業單位名稱或負責人"),
                        "law": raw.get("違法法規法條"), "violation": raw.get("違反法規內容"),
                        "source_amount": raw.get("罰鍰金額")},
        title=str(raw.get("處分字號") or record["id"]),
        summary=str(raw.get("違反法規內容") or raw.get("違法法規法條") or ""),
        observed_at=observed, retrieved_at=retrieved, publication_status="published").to_dict()
    relationship_id = stable_id("relationship", "MOL/penalties", record["id"])
    amount_text = str(raw.get("罰鍰金額") or "").replace(",", "").strip()
    amount = int(amount_text) if re.fullmatch(r"[0-9]+", amount_text) else None
    relationship = dict(id=relationship_id, source_entity_id=company_id,
                        target_entity_id=penalty_id, relationship_type="RELATED_TO_PENALTY",
                        primary_evidence_id=penalty_evidence["id"], observed_at=observed,
                        start_date=day, date_precision="day", confidence="EXACT", status="published",
                        amount=amount, currency="TWD" if amount is not None else None)
    return {
        "entities": ([] if company_entity_id else
                     [Entity(company_id, "Company", name, name, "MOEA/GCI", uniform,
                             "EXACT", "published").to_dict()]) +
                    [Entity(penalty_id, "Penalty", penalty_evidence["title"],
                            penalty_evidence["title"], "MOL/penalties", record["id"],
                            "SOURCE_SCOPED", "published").to_dict()],
        "identifiers": [{"entity_id": company_id, "namespace": "tw:uniform_number", "value": uniform}],
        "evidence": [registry_evidence, penalty_evidence],
        "entity_evidence": [{"entity_id": company_id, "evidence_id": registry_evidence["id"], "fact_type": "IDENTITY"},
                            {"entity_id": company_id, "evidence_id": penalty_evidence["id"], "fact_type": "PENALTY"},
                            {"entity_id": penalty_id, "evidence_id": penalty_evidence["id"], "fact_type": "PENALTY"}],
        "relationships": [relationship],
        "relationship_evidence": [{"relationship_id": relationship_id, "evidence_id": penalty_evidence["id"]}],
        "legacy_map": [{"legacy_namespace": "source_records:penalties", "legacy_id": record["id"], "entity_id": penalty_id}],
    }
