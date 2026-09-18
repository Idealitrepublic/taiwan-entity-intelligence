"""Conservative adapter for published Control Yuan asset declarations."""
from decimal import Decimal, InvalidOperation
import re
import unicodedata

from src.entities.models import evidence_from_projection, stable_id, timestamp
from src.relationships.models import Relationship

SOURCE_NAME = "監察院廉政專刊財產申報資料"
SOURCE_URL = "https://sunshine.cy.gov.tw/"
ASSET_TYPES = (
    "REAL_ESTATE", "CASH", "DEPOSIT", "STOCK", "BOND", "FUND", "SECURITY",
    "CLAIM", "DEBT", "BUSINESS_INVESTMENT", "INSURANCE", "VEHICLE", "OTHER",
)
ASSET_TYPE_ALIASES = {
    "不動產": "REAL_ESTATE", "現金": "CASH", "存款": "DEPOSIT", "股票": "STOCK",
    "債券": "BOND", "基金": "FUND", "有價證券": "SECURITY", "債權": "CLAIM",
    "債務": "DEBT", "事業投資": "BUSINESS_INVESTMENT", "保險": "INSURANCE",
    "車輛": "VEHICLE", "其他資產": "OTHER", "其他": "OTHER",
}
OWNERSHIP_TYPES = {"STOCK", "BOND", "FUND", "SECURITY"}


def _entity_value(entity, key):
    return entity.get(key) if isinstance(entity, dict) else getattr(entity, key)


def _asset_type(value):
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip()
    normalized = ASSET_TYPE_ALIASES.get(normalized, normalized.upper())
    if normalized not in ASSET_TYPES:
        raise ValueError("Unknown asset type")
    return normalized


def _decimal(value):
    if value is None or str(value).strip() == "":
        return None
    number = Decimal(str(value).replace(",", ""))
    if not number.is_finite() or number < 0:
        raise ValueError("Asset amount and quantity must be finite and nonnegative")
    return format(number, "f")


def _uniform_number(value):
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip()
    return normalized if re.fullmatch(r"[0-9]{8}", normalized) else None


def build_asset_declaration_bundle(rows, *, politicians_by_source_id,
                                   companies_by_uniform, retrieved_at):
    """Create draft declaration items; link companies only by exact uniform number."""
    retrieved = timestamp(retrieved_at)
    companies = {_uniform_number(key): value for key, value in companies_by_uniform.items()
                 if _uniform_number(key)}
    bundle = {key: [] for key in (
        "entities", "identifiers", "evidence", "entity_evidence", "relationships",
        "relationship_evidence", "legacy_map", "asset_declarations")}
    report = {"skipped": [], "unresolved_companies": [], "publication_status": "draft"}
    for row in rows:
        record_id = row.get("source_record_id")
        try:
            politician = politicians_by_source_id.get(str(row.get("politician_source_id") or ""))
            if politician is None or _entity_value(politician, "entity_type") != "Politician":
                raise LookupError("unmatched_politician_source_id")
            if not isinstance(record_id, str) or not record_id.strip():
                raise ValueError("source record ID is required")
            declaration_year = int(row.get("declaration_year"))
            if not 1912 <= declaration_year <= 2200:
                raise ValueError("declaration year must be Gregorian")
            asset_type = _asset_type(row.get("asset_type"))
            asset_name = str(row.get("asset_name") or "").strip()
            if not asset_name:
                raise ValueError("asset name is required")
            amount, quantity = _decimal(row.get("amount")), _decimal(row.get("quantity"))
            currency = str(row.get("currency") or "TWD").upper() if amount is not None else None
            if currency is not None and not re.fullmatch(r"[A-Z]{3}", currency):
                raise ValueError("invalid currency")
            quantity_unit = str(row.get("quantity_unit") or "").strip() or None
            if quantity is not None and quantity_unit is None:
                raise ValueError("quantity unit is required")
            company_name = str(row.get("company_name") or "").strip() or None
            uniform = _uniform_number(row.get("company_uniform_number"))
            company = companies.get(uniform) if uniform else None
            if company is not None and _entity_value(company, "entity_type") != "Company":
                raise ValueError("resolved issuer must be a Company")
            observed = timestamp(row.get("observed_at"))
            match_method = "exact_uniform_number" if company else (
                "unmatched_exact_identifier" if uniform else "no_exact_identifier")
            locator = {"publication": str(row.get("publication") or "廉政專刊"),
                       "declaration_year": declaration_year, "asset_type": asset_type,
                       "source_record_id": record_id, "company_match_method": match_method}
            if company:
                locator["uniform_number"] = uniform
            evidence = evidence_from_projection(
                source_name=SOURCE_NAME, source_record_id=record_id,
                source_class="Primary Source", source_url=row.get("source_url") or SOURCE_URL,
                source_locator=locator,
                title=f"財產申報 / Asset declaration：{asset_name}",
                summary=(f"{_entity_value(politician, 'display_name')}；{declaration_year}；"
                         f"{asset_type}；{asset_name}"),
                observed_at=observed, retrieved_at=retrieved)
            relationship = None
            relationship_type = ("BUSINESS_INVESTMENT" if asset_type == "BUSINESS_INVESTMENT"
                                 else "ASSET_OWNERSHIP" if asset_type in OWNERSHIP_TYPES else None)
            if company and relationship_type:
                relationship = Relationship(
                    id=stable_id("relationship", "asset_declaration",
                                 f"{record_id}:{evidence.content_hash}"),
                    source_entity_id=_entity_value(politician, "id"),
                    target_entity_id=_entity_value(company, "id"),
                    relationship_type=relationship_type,
                    primary_evidence_id=evidence.id, observed_at=observed,
                    confidence="EXACT", start_date=f"{declaration_year}-01-01",
                    date_precision="year", amount=amount, currency=currency,
                    quantity=quantity, quantity_unit=quantity_unit,
                    source_role=asset_type)
            item = {
                "id": stable_id("asset_declaration", SOURCE_NAME,
                                f"{record_id}:{evidence.content_hash}"),
                "politician_id": _entity_value(politician, "id"),
                "declaration_year": declaration_year, "asset_type": asset_type,
                "asset_name": asset_name, "amount": amount, "currency": currency,
                "quantity": quantity, "quantity_unit": quantity_unit,
                "company_name": company_name,
                "company_entity_id": _entity_value(company, "id") if company else None,
                "relationship_id": relationship.id if relationship else None,
                "primary_evidence_id": evidence.id, "publication_status": "draft",
            }
        except LookupError as exc:
            report["skipped"].append({"source_record_id": record_id, "reason": str(exc)})
            continue
        except (InvalidOperation, TypeError, ValueError, KeyError):
            report["skipped"].append({"source_record_id": record_id,
                                      "reason": "invalid_source_fields"})
            continue
        if company_name and not company:
            report["unresolved_companies"].append({"source_record_id": record_id,
                                                    "company_name": company_name,
                                                    "reason": match_method})
        bundle["evidence"].append(evidence.to_dict())
        bundle["asset_declarations"].append(item)
        if relationship:
            bundle["relationships"].append(relationship.to_dict())
            bundle["relationship_evidence"].append({
                "relationship_id": relationship.id, "evidence_id": evidence.id,
                "support_type": "supports"})
    for key in ("evidence", "relationships", "asset_declarations"):
        bundle[key] = list({item["id"]: item for item in bundle[key]}.values())
    report["counts"] = {key: len(value) for key, value in bundle.items()}
    return bundle, report
