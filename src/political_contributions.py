"""Normalize official Control Yuan contribution rows into reviewable graph facts."""
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re
import unicodedata

from src.entities.models import evidence_from_projection, stable_id, timestamp
from src.relationships.models import Relationship

SOURCE_NAME = "監察院政治獻金公開查閱平臺"
SOURCE_URL = "https://ardata.cy.gov.tw/"
DEFAULT_DATASET = "control_yuan_political_contributions"
LEGISLATOR_NUMBER_NAMESPACE = "tw:legislative_yuan:legislator_number"
_ALIASES = {
    "source_record_id": ("source_record_id", "序號"),
    "filing_id": ("filing_id", "申報序號", "申報序號／年度", "申報序號/年度"),
    "candidate_name": ("candidate_name", "擬參選人", "擬參選人／政黨", "擬參選人/政黨"),
    "politician_identifier_namespace": ("politician_identifier_namespace",),
    "politician_identifier_value": ("politician_identifier_value", "politician_source_id", "lgno"),
    "donor_name": ("donor_name", "捐贈者", "捐贈者／支出對象", "捐贈者/支出對象"),
    "donor_uniform_number": ("donor_uniform_number", "身分證／統一編號", "身分證/統一編號"),
    "date": ("date", "交易日期"), "amount": ("amount", "收入金額"),
    "contribution_type": ("contribution_type", "收支科目"),
    "year": ("year", "年度"), "source_url": ("source_url",),
    "dataset": ("dataset", "dataset_id"),
}


def _entity_value(entity, key):
    return entity.get(key) if isinstance(entity, dict) else getattr(entity, key)


def _text(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _field(row, name):
    for key in _ALIASES[name]:
        if key in row and _text(row[key]):
            return row[key]
    return None


def _uniform_number(value):
    normalized = re.sub(r"[\s-]", "", _text(value))
    if not re.fullmatch(r"[0-9]{8}", normalized):
        raise ValueError("invalid_company_uniform_number")
    return normalized


def _money(value):
    amount = Decimal(_text(value).replace(",", "").replace("$", "").replace("元", ""))
    if not amount.is_finite() or amount <= 0:
        raise ValueError("invalid_amount")
    return format(amount, "f")


def _date(value):
    normalized = _text(value).replace("年", "/").replace("月", "/").replace("日", "")
    parts = re.split(r"[-/.]", normalized)
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("invalid_date")
    year, month, day = map(int, parts)
    if year < 1911:
        year += 1911
    return date(year, month, day).isoformat()


def _year(value, contribution_date):
    normalized = _text(value)
    if not normalized:
        return int(contribution_date[:4])
    match = re.search(r"\d{3,4}", normalized)
    if not match:
        raise ValueError("invalid_year")
    year = int(match.group())
    return year + 1911 if year < 1911 else year


def _politician_lookup(index, namespace, value):
    matches = []
    for key in ((namespace, value), f"{namespace}:{value}", value):
        if key in index:
            item = index[key]
            matches.extend(item if isinstance(item, (list, tuple)) else [item])
    unique = {_entity_value(item, "id"): item for item in matches}
    if len(unique) != 1:
        raise LookupError("ambiguous_politician_identifier" if unique else
                          "unmatched_politician_identifier")
    return next(iter(unique.values()))


def _empty_bundle():
    return {"entities": [], "identifiers": [], "evidence": [], "entity_evidence": [],
            "relationships": [], "relationship_evidence": [], "legacy_map": []}


def build_political_contribution_bundle(rows, *, companies_by_uniform,
                                        politicians_by_official_id=None,
                                        politicians_by_source_id=None, retrieved_at):
    """Build draft facts; compatibility source IDs remain exact identifiers, never names."""
    retrieved = timestamp(retrieved_at)
    companies = {_uniform_number(key): entity for key, entity in companies_by_uniform.items()}
    politicians = politicians_by_official_id or politicians_by_source_id or {}
    bundle = _empty_bundle()
    report = {"publication_status": "draft",
              "matching_strategy": "exact_uniform_and_official_politician_identifier",
              "input_count": len(rows), "skipped": [], "quality_issues": []}
    seen = {}
    for index, row in enumerate(rows):
        record_id = _text(_field(row, "source_record_id"))
        try:
            filing_id = _text(_field(row, "filing_id"))
            if not record_id:
                if not filing_id:
                    raise ValueError("missing_source_record_id")
                record_id = f"{filing_id}:row:{index + 1}"
            uniform = _uniform_number(_field(row, "donor_uniform_number"))
            company = companies.get(uniform)
            if company is None:
                raise LookupError("unmatched_company_uniform_number")
            namespace = (_text(_field(row, "politician_identifier_namespace"))
                         or LEGISLATOR_NUMBER_NAMESPACE)
            politician_value = _text(_field(row, "politician_identifier_value"))
            if not politician_value:
                raise LookupError("missing_politician_identifier")
            politician = _politician_lookup(politicians, namespace, politician_value)
            if _entity_value(company, "entity_type") != "Company":
                raise ValueError("resolved_donor_not_company")
            if _entity_value(politician, "entity_type") != "Politician":
                raise ValueError("resolved_recipient_not_politician")
            contribution_date = _date(_field(row, "date"))
            contribution_year = _year(_field(row, "year"), contribution_date)
            amount = _money(_field(row, "amount"))
            contribution_type = _text(_field(row, "contribution_type"))
            if not contribution_type:
                raise ValueError("missing_contribution_type")
            donor_name = _text(_field(row, "donor_name"))
            candidate_name = _text(_field(row, "candidate_name"))
            fingerprint = (uniform, namespace, politician_value, contribution_date,
                           amount, contribution_type, filing_id)
            if record_id in seen:
                if seen[record_id] != fingerprint:
                    report["quality_issues"].append({"severity": "high",
                        "type": "conflicting_source_record", "source_record_id": record_id})
                raise ValueError("duplicate_source_record_id")
            seen[record_id] = fingerprint
            observed = f"{contribution_date}T00:00:00+00:00"
            locator = {"dataset": _text(_field(row, "dataset")) or DEFAULT_DATASET,
                "filing_id": filing_id, "source_record_id": record_id,
                "match_method": "exact_uniform_number", "uniform_number": uniform,
                "politician_match_method": "exact_official_identifier",
                "politician_identifier_namespace": namespace,
                "politician_identifier_value": politician_value,
                "candidate_name": candidate_name, "donor_name": donor_name,
                "contribution_year": contribution_year}
            evidence = evidence_from_projection(
                source_name=SOURCE_NAME, source_record_id=record_id,
                source_class="Government Open Data",
                source_url=_text(_field(row, "source_url")) or SOURCE_URL,
                source_locator=locator,
                title=f"政治獻金 / Political contribution：{_entity_value(company, 'display_name')}",
                summary=(f"{donor_name or _entity_value(company, 'display_name')} → "
                         f"{candidate_name or _entity_value(politician, 'display_name')}；"
                         f"{amount} TWD；{contribution_type}；{contribution_date}"),
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
        except (InvalidOperation, TypeError, ValueError, LookupError, KeyError) as exc:
            report["skipped"].append({"source_record_id": record_id or None,
                                      "row": index,
                                      "reason": str(exc) or "invalid_source_fields"})
            continue
        bundle["evidence"].append(evidence.to_dict())
        bundle["relationships"].append(relationship.to_dict())
        bundle["relationship_evidence"].append({"relationship_id": relationship.id,
            "evidence_id": evidence.id, "support_type": "supports"})
    for key in ("evidence", "relationships"):
        bundle[key] = list({item["id"]: item for item in bundle[key]}.values())
    bundle["relationship_evidence"] = list({
        (item["relationship_id"], item["evidence_id"]): item
        for item in bundle["relationship_evidence"]}.values())
    accepted = len(bundle["relationships"])
    report["counts"] = {key: len(value) for key, value in bundle.items()}
    report["quality"] = {"accepted": accepted, "skipped": len(report["skipped"]),
        "exact_match_coverage": accepted / len(rows) if rows else 0.0,
        "high_severity_issue_count": sum(
            issue["severity"] == "high" for issue in report["quality_issues"])}
    return bundle, report


def political_contribution_batches(bundle, *, max_bytes=900_000):
    """Split facts into dependency-complete batches under core RPC limits."""
    relationships = {item["id"]: item for item in bundle["relationships"]}
    evidence = {item["id"]: item for item in bundle["evidence"]}
    links = {item["relationship_id"]: item for item in bundle["relationship_evidence"]}
    batches, current = [], _empty_bundle()
    for relationship_id, relationship in relationships.items():
        group = _empty_bundle()
        group["relationships"] = [relationship]
        group["evidence"] = [evidence[relationship["primary_evidence_id"]]]
        group["relationship_evidence"] = [links[relationship_id]]
        candidate = {key: current[key] + group[key] for key in current}
        oversized = (len(candidate["relationships"]) > 200 or
                     len(candidate["evidence"]) > 400 or
                     len(json.dumps(candidate, ensure_ascii=False).encode()) > max_bytes)
        if oversized:
            if not current["relationships"]:
                raise ValueError("One political contribution exceeds ingestion limits")
            batches.append(current)
            current = group
        else:
            current = candidate
    if current["relationships"]:
        batches.append(current)
    return batches


def build_political_contribution_batches(rows, **kwargs):
    max_bytes = kwargs.pop("max_bytes", 900_000)
    bundle, report = build_political_contribution_bundle(rows, **kwargs)
    batches = political_contribution_batches(bundle, max_bytes=max_bytes)
    report["batch_count"] = len(batches)
    return batches, report
