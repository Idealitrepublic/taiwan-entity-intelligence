"""Normalize official Control Yuan asset declarations into versioned draft facts."""
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import unicodedata

from src.entities.models import evidence_from_projection, stable_id, timestamp
from src.relationships.models import Relationship

SOURCE_NAME = "監察院廉政專刊財產申報資料"
SOURCE_URL = "https://sunshine.cy.gov.tw/"
LEGISLATOR_NUMBER_NAMESPACE = "tw:legislative_yuan:legislator_number"
ASSET_TYPES = (
    "REAL_ESTATE", "CASH", "DEPOSIT", "STOCK", "BOND", "FUND", "SECURITY",
    "CLAIM", "DEBT", "BUSINESS_INVESTMENT", "INSURANCE", "VEHICLE", "OTHER",
)
ASSET_TYPE_ALIASES = {
    "不動產": "REAL_ESTATE", "土地及建物": "REAL_ESTATE", "現金": "CASH",
    "存款": "DEPOSIT", "股票": "STOCK", "債券": "BOND", "基金": "FUND",
    "有價證券": "SECURITY", "債權": "CLAIM", "債務": "DEBT",
    "事業投資": "BUSINESS_INVESTMENT", "對各種事業之投資": "BUSINESS_INVESTMENT",
    "保險": "INSURANCE", "車輛": "VEHICLE", "汽車": "VEHICLE",
    "其他資產": "OTHER", "其他": "OTHER",
}
OWNERSHIP_TYPES = {"STOCK", "BOND", "FUND", "SECURITY"}
_ALIASES = {
    "source_record_id": ("source_record_id", "資料編號", "序號"),
    "filing_id": ("filing_id", "申報編號", "申報序號"),
    "line_number": ("line_number", "項次", "編號"),
    "politician_identifier_namespace": ("politician_identifier_namespace",),
    "politician_identifier_value": ("politician_identifier_value", "politician_source_id", "lgno"),
    "politician_name": ("politician_name", "申報人姓名", "姓名"),
    "declaration_year": ("declaration_year", "申報年度", "年度"),
    "declaration_version": ("declaration_version", "更正次數", "版本"),
    "supersedes_declaration_id": ("supersedes_declaration_id",),
    "asset_type": ("asset_type", "財產類別", "類別"),
    "asset_name": ("asset_name", "財產名稱", "名稱"),
    "amount": ("amount", "金額", "價額"),
    "currency": ("currency", "幣別"),
    "quantity": ("quantity", "數量"),
    "quantity_unit": ("quantity_unit", "單位"),
    "company_name": ("company_name", "公司名稱", "事業名稱"),
    "company_uniform_number": ("company_uniform_number", "統一編號", "營利事業統一編號"),
    "observed_at": ("observed_at", "申報日", "申報日期"),
    "publication": ("publication", "專刊", "刊期"),
    "source_url": ("source_url",),
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


def _asset_type(value):
    normalized = _text(value)
    normalized = ASSET_TYPE_ALIASES.get(normalized, normalized.upper())
    if normalized not in ASSET_TYPES:
        raise ValueError("unknown_asset_type")
    return normalized


def _decimal(value):
    if value is None or not _text(value):
        return None
    normalized = (_text(value).replace(",", "").replace("元", "")
                  .replace("$", "").replace("股", ""))
    number = Decimal(normalized)
    if not number.is_finite() or number < 0:
        raise ValueError("invalid_nonnegative_number")
    return format(number, "f")


def _uniform_number(value):
    normalized = re.sub(r"[\s-]", "", _text(value))
    return normalized if re.fullmatch(r"[0-9]{8}", normalized) else None


def _year(value):
    match = re.search(r"\d{3,4}", _text(value))
    if not match:
        raise ValueError("invalid_declaration_year")
    year = int(match.group())
    year = year + 1911 if year < 1911 else year
    if not 1912 <= year <= 2200:
        raise ValueError("invalid_declaration_year")
    return year


def _integer(value, default=1):
    if value is None or not _text(value):
        return default
    number = int(_text(value))
    if number < 1 or number > 999:
        raise ValueError("invalid_declaration_version")
    return number


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
    politician = next(iter(unique.values()))
    if _entity_value(politician, "entity_type") != "Politician":
        raise ValueError("resolved_declarant_not_politician")
    return politician


def _empty_bundle():
    return {key: [] for key in (
        "entities", "identifiers", "evidence", "entity_evidence", "relationships",
        "relationship_evidence", "legacy_map", "asset_declarations")}


def build_asset_declaration_bundle(rows, *, politicians_by_official_id=None,
                                   politicians_by_source_id=None,
                                   companies_by_uniform, retrieved_at):
    """Create versioned draft items; resolve people/companies by exact IDs only."""
    retrieved = timestamp(retrieved_at)
    politicians = politicians_by_official_id or politicians_by_source_id or {}
    companies = {_uniform_number(key): value for key, value in companies_by_uniform.items()
                 if _uniform_number(key)}
    bundle = _empty_bundle()
    report = {"skipped": [], "unresolved_companies": [], "quality_issues": [],
              "publication_status": "draft", "input_count": len(rows)}
    seen_records, seen_versions = {}, set()
    for index, row in enumerate(rows):
        record_id = _text(_field(row, "source_record_id"))
        try:
            filing_id = _text(_field(row, "filing_id"))
            line_number = _text(_field(row, "line_number")) or str(index + 1)
            if not record_id:
                if not filing_id:
                    raise ValueError("missing_source_record_id")
                record_id = f"{filing_id}:line:{line_number}"
            namespace = (_text(_field(row, "politician_identifier_namespace"))
                         or LEGISLATOR_NUMBER_NAMESPACE)
            politician_value = _text(_field(row, "politician_identifier_value"))
            if not politician_value:
                raise LookupError("missing_politician_identifier")
            politician = _politician_lookup(politicians, namespace, politician_value)
            declaration_year = _year(_field(row, "declaration_year"))
            declaration_version = _integer(_field(row, "declaration_version"))
            asset_type = _asset_type(_field(row, "asset_type"))
            asset_name = _text(_field(row, "asset_name"))
            if not asset_name:
                raise ValueError("missing_asset_name")
            amount, quantity = _decimal(_field(row, "amount")), _decimal(_field(row, "quantity"))
            currency = _text(_field(row, "currency")).upper() or "TWD" if amount is not None else None
            if currency is not None and not re.fullmatch(r"[A-Z]{3}", currency):
                raise ValueError("invalid_currency")
            quantity_unit = _text(_field(row, "quantity_unit")) or None
            if quantity is not None and quantity_unit is None:
                raise ValueError("missing_quantity_unit")
            company_name = _text(_field(row, "company_name")) or None
            raw_uniform = _field(row, "company_uniform_number")
            uniform = _uniform_number(raw_uniform)
            if raw_uniform is not None and not uniform:
                raise ValueError("invalid_company_uniform_number")
            company = companies.get(uniform) if uniform else None
            if company is not None and _entity_value(company, "entity_type") != "Company":
                raise ValueError("resolved_issuer_not_company")
            publication = _text(_field(row, "publication")) or "廉政專刊"
            observed = timestamp(_field(row, "observed_at"))
            declaration_key = hashlib.sha256(
                "|".join((filing_id or publication, line_number, asset_type)).encode()).hexdigest()
            version_key = (_entity_value(politician, "id"), declaration_year,
                           declaration_key, declaration_version)
            if version_key in seen_versions:
                raise ValueError("duplicate_declaration_version")
            seen_versions.add(version_key)
            fingerprint = (version_key, asset_name, amount, quantity, company_name, uniform)
            if record_id in seen_records:
                if seen_records[record_id] != fingerprint:
                    report["quality_issues"].append({"severity": "high",
                        "type": "conflicting_source_record", "source_record_id": record_id})
                raise ValueError("duplicate_source_record_id")
            seen_records[record_id] = fingerprint
            match_method = "exact_uniform_number" if company else (
                "unmatched_exact_identifier" if uniform else "no_exact_identifier")
            locator = {"publication": publication, "filing_id": filing_id,
                "line_number": line_number, "declaration_year": declaration_year,
                "declaration_version": declaration_version, "declaration_key": declaration_key,
                "asset_type": asset_type, "source_record_id": record_id,
                "politician_match_method": "exact_official_identifier",
                "politician_identifier_namespace": namespace,
                "politician_identifier_value": politician_value,
                "politician_name": _text(_field(row, "politician_name")),
                "company_match_method": match_method, "company_name": company_name}
            if uniform:
                locator["uniform_number"] = uniform
            evidence = evidence_from_projection(
                source_name=SOURCE_NAME, source_record_id=record_id,
                source_class="Primary Source",
                source_url=_text(_field(row, "source_url")) or SOURCE_URL,
                source_locator=locator,
                title=f"財產申報 / Asset declaration：{asset_name}",
                summary=(f"{_entity_value(politician, 'display_name')}；{declaration_year}；"
                         f"第{declaration_version}版；{asset_type}；{asset_name}"),
                observed_at=observed, retrieved_at=retrieved)
            relationship_type = ("BUSINESS_INVESTMENT" if asset_type == "BUSINESS_INVESTMENT"
                                 else "ASSET_OWNERSHIP" if asset_type in OWNERSHIP_TYPES else None)
            relationship = None
            if company and relationship_type:
                relationship = Relationship(
                    id=stable_id("relationship", "asset_declaration", f"{record_id}:{evidence.content_hash}"),
                    source_entity_id=_entity_value(politician, "id"),
                    target_entity_id=_entity_value(company, "id"),
                    relationship_type=relationship_type, primary_evidence_id=evidence.id,
                    observed_at=observed, confidence="EXACT",
                    start_date=f"{declaration_year}-01-01", date_precision="year",
                    amount=amount, currency=currency, quantity=quantity,
                    quantity_unit=quantity_unit, source_role=asset_type)
            item = {"id": stable_id("asset_declaration", SOURCE_NAME,
                                     f"{record_id}:{evidence.content_hash}"),
                "politician_id": _entity_value(politician, "id"),
                "declaration_year": declaration_year, "declaration_key": declaration_key,
                "declaration_version": declaration_version,
                "supersedes_declaration_id": _text(_field(row, "supersedes_declaration_id")) or None,
                "asset_type": asset_type, "asset_name": asset_name, "amount": amount,
                "currency": currency, "quantity": quantity, "quantity_unit": quantity_unit,
                "company_name": company_name,
                "company_entity_id": _entity_value(company, "id") if company else None,
                "relationship_id": relationship.id if relationship else None,
                "primary_evidence_id": evidence.id, "publication_status": "draft"}
        except (InvalidOperation, TypeError, ValueError, LookupError, KeyError) as exc:
            report["skipped"].append({"source_record_id": record_id or None, "row": index,
                                      "reason": str(exc) or "invalid_source_fields"})
            continue
        if company_name and not company:
            report["unresolved_companies"].append({"source_record_id": record_id,
                                                    "company_name": company_name,
                                                    "reason": match_method})
        bundle["evidence"].append(evidence.to_dict())
        bundle["asset_declarations"].append(item)
        if relationship:
            bundle["relationships"].append(relationship.to_dict())
            bundle["relationship_evidence"].append({"relationship_id": relationship.id,
                "evidence_id": evidence.id, "support_type": "supports"})
    for key in ("evidence", "relationships", "asset_declarations"):
        bundle[key] = list({item["id"]: item for item in bundle[key]}.values())
    accepted = len(bundle["asset_declarations"])
    covered_types = {item["asset_type"] for item in bundle["asset_declarations"]}
    company_rows = [item for item in bundle["asset_declarations"] if item["company_name"]]
    report["counts"] = {key: len(value) for key, value in bundle.items()}
    report["quality"] = {"accepted": accepted, "skipped": len(report["skipped"]),
        "row_acceptance_rate": accepted / len(rows) if rows else 0.0,
        "asset_type_coverage": len(covered_types) / len(ASSET_TYPES),
        "company_exact_match_rate": (sum(item["company_entity_id"] is not None
            for item in company_rows) / len(company_rows) if company_rows else None),
        "high_severity_issue_count": sum(issue["severity"] == "high"
            for issue in report["quality_issues"])}
    return bundle, report


def asset_declaration_batches(bundle, *, max_bytes=900_000):
    """Split line items with their Evidence/optional edge under ingestion limits."""
    evidence = {item["id"]: item for item in bundle["evidence"]}
    relationships = {item["id"]: item for item in bundle["relationships"]}
    links = {item["relationship_id"]: item for item in bundle["relationship_evidence"]}
    batches, current = [], _empty_bundle()
    for declaration in bundle["asset_declarations"]:
        group = _empty_bundle()
        group["asset_declarations"] = [declaration]
        group["evidence"] = [evidence[declaration["primary_evidence_id"]]]
        if declaration["relationship_id"]:
            group["relationships"] = [relationships[declaration["relationship_id"]]]
            group["relationship_evidence"] = [links[declaration["relationship_id"]]]
        candidate = {key: current[key] + group[key] for key in current}
        oversized = (len(candidate["asset_declarations"]) > 200 or
                     len(candidate["relationships"]) > 200 or
                     len(candidate["evidence"]) > 400 or
                     len(json.dumps(candidate, ensure_ascii=False).encode()) > max_bytes)
        if oversized:
            if not current["asset_declarations"]:
                raise ValueError("One asset declaration exceeds ingestion limits")
            batches.append(current)
            current = group
        else:
            current = candidate
    if current["asset_declarations"]:
        batches.append(current)
    return batches


def build_asset_declaration_batches(rows, **kwargs):
    max_bytes = kwargs.pop("max_bytes", 900_000)
    bundle, report = build_asset_declaration_bundle(rows, **kwargs)
    batches = asset_declaration_batches(bundle, max_bytes=max_bytes)
    report["batch_count"] = len(batches)
    return batches, report
