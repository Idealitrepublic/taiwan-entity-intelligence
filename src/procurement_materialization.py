"""Stage a bounded award observation for an already verified company.

The OpenFun record is a structured copy of a PCC notice, not independent
official row-level confirmation. Keep the bundle draft until the original PCC
notice has been checked. A company name or bid alone is never publishable.
"""
from datetime import datetime
import re
import unicodedata
from urllib.parse import urlencode, urlsplit

from src.entities.models import Entity, evidence_from_projection, stable_id, timestamp
from src.sources.procurement import award_role, is_award_notice, matched_names, OFFICIAL_SEARCH


SOURCE = "政府電子採購網公告（OpenFun 結構化介接）"
API = "https://pcc-api.openfun.app/api/tender"


def _company_name(value):
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    return re.sub(r"\s*\([^()]*\)\s*$", "", text).strip()


def _award_day(value):
    match = re.fullmatch(r"(\d{2,3})/(\d{2})/(\d{2})", str(value or ""))
    if not match:
        raise ValueError("PCC award date is missing or malformed")
    return datetime(int(match[1]) + 1911, int(match[2]), int(match[3])).date().isoformat()


def build_contract_bundle(notice, *, company_entity_id, company_uniform,
                          company_name, retrieved_at):
    """Require exact bidder ID, winner role, and a stable notice locator."""
    if not re.fullmatch(r"[0-9]{8}", company_uniform):
        raise ValueError("Verified company uniform number required")
    detail = notice.get("detail") or {}
    unit_id = str(notice.get("unit_id") or "")
    job_number = str(notice.get("job_number") or "")
    filename = str(notice.get("filename") or "")
    if (not re.fullmatch(r"[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*", unit_id)
            or not re.fullmatch(r"[\w-]+", job_number)
            or not re.fullmatch(r"[\w-]+", filename)
            or not is_award_notice(notice)
            or award_role(notice, company_uniform) != "winner"):
        raise ValueError("Stable PCC award notice and exact winner role required")
    names = matched_names(notice, company_uniform)
    if len(names) != 1 or _company_name(names[0]) != _company_name(company_name):
        raise ValueError("Bidder name conflicts with the verified company")
    # The detailed bidder role must agree with the brief's ID-key mapping.
    matching_positions = [index for index in range(1, 51)
                          if detail.get(f"投標廠商:投標廠商{index}:廠商代碼") == company_uniform]
    if len(matching_positions) != 1:
        raise ValueError("Detailed notice has no unique exact bidder identifier")
    prefix = f"投標廠商:投標廠商{matching_positions[0]}"
    if (detail.get(prefix + ":是否得標") != "是"
            or _company_name(detail.get(prefix + ":廠商名稱")) != _company_name(company_name)):
        raise ValueError("Detailed bidder record does not prove an award")
    if (str(detail.get("已公告資料:標案案號") or "") != job_number
            or str(detail.get("機關資料:機關代碼") or "") != unit_id):
        raise ValueError("Notice and detailed case identifiers conflict")
    award_day = _award_day(detail.get("決標資料:決標日期"))
    published = str(notice.get("date") or "")
    if not re.fullmatch(r"\d{8}", published):
        raise ValueError("Notice publication date required")
    published_day = datetime.strptime(published, "%Y%m%d").date().isoformat()
    if published_day < award_day:
        raise ValueError("Notice predates its award")
    title = str(detail.get("已公告資料:標案名稱") or "").strip()
    agency = str(detail.get("機關資料:機關名稱") or "").strip()
    if not title or not agency or len(title) > 300:
        raise ValueError("Case title and agency required")
    amount_text = str(detail.get(prefix + ":決標金額") or "")
    amount_match = re.fullmatch(r"([0-9][0-9,]*)元", amount_text)
    amount = int(amount_match[1].replace(",", "")) if amount_match else None
    retrieved = timestamp(retrieved_at)
    source_id = f"{unit_id}:{job_number}:{filename}"
    contract_id = stable_id("entity", "PCC/OpenFun", source_id)
    edge_id = stable_id("relationship", "PCC/OpenFun", f"{source_id}:{company_uniform}")
    url = API + "?" + urlencode({"unit_id": unit_id, "job_number": job_number})
    evidence = evidence_from_projection(
        source_name=SOURCE, source_record_id=source_id, source_class="Derived Data",
        source_url=url,
        source_locator={"unit_id": unit_id, "job_number": job_number,
                        "notice_filename": filename, "notice_date": published_day,
                        "award_date": award_day, "bidder_uniform_number": company_uniform,
                        "bidder_field": prefix + ":廠商代碼",
                        "winner_field": prefix + ":是否得標",
                        "amount_field": prefix + ":決標金額" if amount is not None else None,
                        "official_search_url": OFFICIAL_SEARCH,
                        "match_method": "exact_bidder_id_and_winner_role_in_same_latest_notice",
                        "mirror_warning": "Structured mirror; verify against the official PCC portal"},
        title=title, summary=f"{agency}；得標廠商：{company_name}（{company_uniform}）",
        observed_at=award_day + "T00:00:00+08:00", retrieved_at=retrieved,
        publication_status="draft").to_dict()
    contract = Entity(contract_id, "Contract", title, title, "PCC/OpenFun", source_id,
                      "SOURCE_SCOPED", "draft").to_dict()
    relationship = {
        "id": edge_id, "source_entity_id": company_entity_id,
        "target_entity_id": contract_id, "relationship_type": "CONTRACT_WITH",
        "primary_evidence_id": evidence["id"], "observed_at": evidence["observed_at"],
        "confidence": "HIGH", "status": "draft", "start_date": award_day,
        "date_precision": "day", "amount": amount, "currency": "TWD" if amount is not None else None,
        "source_role": "得標廠商",
    }
    return {
        "entities": [contract], "evidence": [evidence],
        "entity_evidence": [{"entity_id": company_entity_id, "evidence_id": evidence["id"], "fact_type": "CONTRACT"},
                            {"entity_id": contract_id, "evidence_id": evidence["id"], "fact_type": "CONTRACT"}],
        "relationships": [relationship],
        "relationship_evidence": [{"relationship_id": edge_id, "evidence_id": evidence["id"]}],
        "legacy_map": [{"legacy_namespace": "PCC/OpenFun:award", "legacy_id": source_id,
                        "entity_id": contract_id}],
    }


def build_official_award_bundle(notice, *, official, company_entity_id,
                                company_uniform, company_name, retrieved_at):
    """Publish only after independently matching the original PCC award row.

    `official` is a reviewed transcription of the original notice, not a
    mirror lookup. The caller must retain the row URL for human rechecking.
    """
    draft = build_contract_bundle(
        notice, company_entity_id=company_entity_id,
        company_uniform=company_uniform, company_name=company_name,
        retrieved_at=retrieved_at)
    contract, mirror = draft["entities"][0], draft["evidence"][0]
    locator = mirror["source_locator"]
    source_url = str(official.get("source_url") or "")
    parsed = urlsplit(source_url)
    if (parsed.scheme != "https" or parsed.hostname != "web.pcc.gov.tw"
            or not parsed.path.endswith("/QueryAtmAwardDetailHist")
            or not parsed.query):
        raise ValueError("Original PCC award-row URL required")
    expected = {
        "unit_id": locator["unit_id"], "job_number": locator["job_number"],
        "notice_filename": locator["notice_filename"],
        "notice_date": locator["notice_date"],
        "award_date": locator["award_date"],
        "bidder_uniform_number": company_uniform,
        "amount": draft["relationships"][0]["amount"],
        "title": contract["display_name"],
    }
    if (any(official.get(key) != value for key, value in expected.items())
            or _company_name(official.get("bidder_name")) != _company_name(company_name)
            or official.get("winner") is not True
            or not str(official.get("agency") or "").strip()):
        raise ValueError("Official notice conflicts with the mirror or company ID")
    source_id = mirror["source_record_id"]
    proof = evidence_from_projection(
        source_name="政府電子採購網", source_record_id=source_id,
        source_class="Primary Source", source_url=source_url,
        source_locator={**expected, "bidder_name": official["bidder_name"],
                        "winner": True, "agency": official["agency"],
                        "mirror_url": mirror["source_url"],
                        "review_method": "official_row_compared_with_exact_bidder_id_and_award_role"},
        title=contract["display_name"],
        summary=f"{official['agency']}；得標廠商：{company_name}（{company_uniform}）",
        observed_at=locator["award_date"] + "T00:00:00+08:00",
        retrieved_at=retrieved_at, publication_status="published").to_dict()
    edge = {**draft["relationships"][0],
            "id": stable_id("relationship", "PCC official", f"{source_id}:{company_uniform}"),
            "primary_evidence_id": proof["id"], "status": "published"}
    return {
        "entities": [{**contract, "publication_status": "published"}],
        "evidence": [proof],
        "entity_evidence": [
            {"entity_id": company_entity_id, "evidence_id": proof["id"], "fact_type": "CONTRACT"},
            {"entity_id": contract["id"], "evidence_id": proof["id"], "fact_type": "CONTRACT"},
        ],
        "relationships": [edge],
        "relationship_evidence": [{"relationship_id": edge["id"], "evidence_id": proof["id"]}],
    }
