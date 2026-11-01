"""One explicitly reviewed corporate case-role crosswalk, not news name mining.

Co-mentions alone, private people and personal criminal profiles are excluded.
This module never accepts an arbitrary company name or infers other links.
"""
from datetime import date
from hashlib import sha256
import json

from src.company_registry_materialization import build_registry_company_bundle
from src.entities.models import evidence_from_projection, stable_id, timestamp
from src.relationships.models import Relationship
from src.sources.court_notices import SOURCE, _Text, _normalize


ROLE_SOURCE = "法院公告法人角色核對 / Reviewed corporate case role"
UNIFORM = "59066479"
LEGAL_NAME = "頂新製油實業股份有限公司"
NOTICE_ID = "688053"


def _verified_original(directory, filename, expected_url=None):
    rows = json.loads((directory / "acquisition.json").read_text())
    matching = [r for r in rows if r["file"] == filename]
    if len(matching) != 1:
        raise ValueError("Unique original acquisition proof required")
    entry = matching[0]
    raw = (directory / filename).read_bytes()
    if (len(raw) > 2_000_000 or entry["bytes"] != len(raw)
            or entry["sha256"] != sha256(raw).hexdigest()
            or (expected_url and entry["source_url"] != expected_url)):
        raise ValueError("Corporate crosswalk original hash or URL mismatch")
    timestamp(entry["retrieved_at"])
    return raw, entry


def add_reviewed_corporate_link(bundle, directory):
    """Attach exactly the reviewed Company→case role, preserving existing IDs.

    The registry verifies the Company's identifier, not a person's identity or
    every assertion in a news story. The court supplies the specific case role.
    HIGH denotes this reviewed cross-source corporate association, not guilt.
    """
    matches = [e for e in bundle["evidence"] if e["source_name"] == SOURCE
               and e["source_record_id"] == "judicial-news:" + NOTICE_ID]
    if len(matches) != 1:
        raise ValueError("Reviewed target announcement is missing or ambiguous")
    notice = matches[0]
    case_ids = [e["id"] for e in bundle["entities"] if e["source"] == SOURCE
                and e["source_id"] == notice["source_record_id"]]
    if len(case_ids) != 1:
        raise ValueError("Reviewed target case identity is ambiguous")
    raw, acquired = _verified_original(directory, "wei-case.html", notice["source_url"])
    parser = _Text()
    parser.feed(raw.decode("utf-8"))
    content = _normalize(" ".join(parser.parts))
    for proof in (LEGAL_NAME + "（下稱頂新公司）", "頂新公司不服", "對頂新公司科以罰金刑"):
        if _normalize(proof) not in content:
            raise ValueError("A mere co-mention cannot establish a corporate case role")
    registry_raw, registry_acquired = _verified_original(directory, "registry-59066479.json")
    # A captured response must be from the official exact-ID endpoint, not a
    # page or a search result supplied under a misleading filename.
    from urllib.parse import parse_qs, urlsplit
    url = urlsplit(registry_acquired["source_url"])
    query = parse_qs(url.query)
    if (url.scheme != "https" or url.hostname != "data.gcis.nat.gov.tw"
            or url.username or url.password or url.port
            or url.path != "/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6"
            or query.get("$filter") != ["Business_Accounting_NO eq " + UNIFORM]):
        raise ValueError("An official exact-identifier registry response is required")
    records = json.loads(registry_raw)
    if not isinstance(records, list) or len(records) != 1:
        raise ValueError("Unique official registry identity required")
    registry = records[0]
    setup = str(registry.get("Company_Setup_Date") or "")
    if len(setup) != 7 or not setup.isascii() or not setup.isdecimal():
        raise ValueError("Official incorporation date required for temporal review")
    incorporated = date(int(setup[:3]) + 1911, int(setup[3:5]), int(setup[5:]))
    finality = date.fromisoformat(notice["source_locator"]["finality_announced_on"])
    if incorporated > finality:
        raise ValueError("Company incorporation postdates the historical case")
    company = build_registry_company_bundle(registry, uniform=UNIFORM, expected_name=LEGAL_NAME,
                                            retrieved_at=registry_acquired["retrieved_at"])
    status = notice["publication_status"]
    for row in company["entities"] + company["evidence"]:
        row["publication_status"] = status
    company_id = company["entities"][0]["id"]
    source_id = UNIFORM + ":judicial-news:" + NOTICE_ID
    role = "法院公告當事法人 / Corporate party in court announcement"
    proof = evidence_from_projection(
        source_name=ROLE_SOURCE, source_record_id=source_id, source_class="Court Record",
        source_url=notice["source_url"], title=LEGAL_NAME + "｜" + role,
        summary=("法院公告列明此法人為本案上訴當事人。經人工核對完整法人名稱、官方統編登記及設立時間；"
                 "僅表達該案件角色，不把共同提及、交易往來或其他關聯者視為共犯或有罪。 / "
                 "Reviewed corporate party in this historical case; co-mentions and associations do not imply guilt."),
        source_locator={"uniform_number": UNIFORM, "company_name": LEGAL_NAME,
                        "notice_id": NOTICE_ID, "case_role": role,
                        "judicial_snapshot_sha256": acquired["sha256"],
                        "registry_snapshot_sha256": registry_acquired["sha256"],
                        "registry_source_url": registry_acquired["source_url"],
                        "company_incorporated_on": incorporated.isoformat(),
                        "event_date": finality.isoformat(),
                        "matching_method": "reviewed_legal_name_official_uniform_and_temporal_consistency",
                        "review_status": "reviewed_corporate_role_only", "confidence": "HIGH",
                        "person_identity_matching": "not_performed", "news_comention_is_relationship": False},
        observed_at=notice["observed_at"], retrieved_at=max(acquired["retrieved_at"], registry_acquired["retrieved_at"]),
        publication_status=status)
    relationship = Relationship(
        stable_id("relationship", ROLE_SOURCE, source_id), company_id, case_ids[0],
        "RELATED_TO_JUDGMENT", proof.id, notice["observed_at"], confidence="HIGH",
        status="published" if status == "published" else "draft",
        start_date=finality.isoformat(), end_date=finality.isoformat(), date_precision="day",
        source_role=role).to_dict()
    for key, rows in company.items():
        bundle.setdefault(key, []).extend(rows)
    bundle["evidence"].append(proof.to_dict())
    for entity_id in (company_id, case_ids[0]):
        bundle["entity_evidence"].append({"entity_id": entity_id, "evidence_id": proof.id,
                                          "fact_type": "reviewed_corporate_case_role"})
    bundle.setdefault("relationships", []).append(relationship)
    bundle.setdefault("relationship_evidence", []).extend([
        {"relationship_id": relationship["id"], "evidence_id": proof.id, "support_type": "supports"},
        {"relationship_id": relationship["id"], "evidence_id": company["evidence"][0]["id"],
         "support_type": "context"},
    ])
    return bundle
