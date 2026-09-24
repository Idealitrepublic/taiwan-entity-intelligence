#!/usr/bin/env python3
"""Build a bounded, source-backed Development review sample (never publish here).

The Control Yuan and Gazette do not supply LY lgno. This script records the
reviewed official-source chain explicitly; database publication still requires
the private crosswalk row and deferred constraints.
"""

import argparse
from datetime import date, datetime, timezone
import json
from urllib.parse import urlencode

from src.cloud_company import COMPANY_API, _moea_rows
from src.entities.models import Entity, evidence_from_projection, stable_id
from src.relationships.models import Relationship
from scripts.stage_asset_evidence_dev import extract as asset_extract
from scripts.stage_contribution_evidence_dev import records, normalize_row

UNIFORM = "29072066"
CONTRIBUTION_SERIAL = "886"
WANG_LGNO = "00007"
HUANG_LGNO = "00082"
WANG_CEC_URL = "https://web.cec.gov.tw/central/article/60070"
HUANG_LY_URL = "https://www.ly.gov.tw/Pages/List.aspx?nodeid=46830"


def empty_bundle():
    return {key: [] for key in ("entities", "identifiers", "evidence",
                                 "entity_evidence", "relationships",
                                 "relationship_evidence", "legacy_map")}


def prepare(*, wang_master_evidence_id, huang_master_evidence_id, reviewed_by,
            retrieved_at=None):
    retrieved_at = retrieved_at or datetime.now(timezone.utc).isoformat()
    company_rows = _moea_rows(COMPANY_API, UNIFORM, 1)
    if len(company_rows) != 1 or company_rows[0].get("Business_Accounting_NO") != UNIFORM:
        raise ValueError("MOEA company number is not an exact unique match")
    company_name = company_rows[0]["Company_Name"]
    if company_name != "都一處有限公司":
        raise ValueError("MOEA company name changed; review before publication")
    matching = [row for row in records() if row.get("序號") == CONTRIBUTION_SERIAL]
    if len(matching) != 1 or matching[0].get("擬參選人／政黨") != "王鴻薇" or \
       matching[0].get("身分證／統一編號") != UNIFORM:
        raise ValueError("Control Yuan filing row changed; review before publication")
    row = matching[0]
    staged = normalize_row(row, retrieved_at)
    if staged is None:
        raise ValueError("Control Yuan row is not a valid corporate donation")
    if row.get("選舉名稱") != "113年立法委員選舉":
        raise ValueError("Control Yuan election context changed")

    company_id = stable_id("entity", "tw:uniform_number", UNIFORM)
    wang_id = stable_id("entity", "tw:legislative_yuan:legislator_number", WANG_LGNO)
    huang_id = stable_id("entity", "tw:legislative_yuan:legislator_number", HUANG_LGNO)
    company = Entity(id=company_id, entity_type="Company", canonical_name=company_name,
                     display_name=company_name, source="MOEA/GCI", source_id=UNIFORM,
                     identity_status="EXACT")
    company_proof = evidence_from_projection(
        source_name="經濟部商工登記公示資料", source_record_id=f"moea:company:{UNIFORM}",
        source_class="Official Registry",
        source_url=COMPANY_API + "?" + urlencode({"$filter": f"Business_Accounting_NO eq {UNIFORM}"}),
        source_locator={"uniform_number": UNIFORM, "company_name": company_name,
                        "match_method": "exact_uniform_number"},
        title=f"公司登記：{company_name}", summary=f"統一編號 {UNIFORM}；{company_name}",
        observed_at=retrieved_at, retrieved_at=retrieved_at)
    company_bundle = empty_bundle()
    company_bundle["entities"] = [company.to_dict()]
    company_bundle["identifiers"] = [{"entity_id": company_id,
                                      "namespace": "tw:uniform_number", "value": UNIFORM,
                                      "confidence": "EXACT"}]
    company_bundle["evidence"] = [company_proof.to_dict()]
    company_bundle["entity_evidence"] = [{"entity_id": company_id,
                                           "evidence_id": company_proof.id,
                                           "fact_type": "company_registration"}]

    donation_crosswalk_id = stable_id("political_crosswalk", "control_yuan", staged["source_record_id"])
    donation_locator = dict(staged["source_locator"])
    donation_locator.update({"politician_match_method": "exact_official_identifier",
                            "politician_identifier_origin": "reviewed_crosswalk",
                            "politician_crosswalk_id": donation_crosswalk_id,
                            "politician_identifier_namespace": "tw:legislative_yuan:legislator_number",
                            "politician_identifier_value": WANG_LGNO,
                            "match_method": "exact_uniform_number",
                            "uniform_number": UNIFORM,
                            "contribution_year": 2023})
    donation_date = date(int(row["交易日期"][:3]) + 1911,
                         int(row["交易日期"][3:5]), int(row["交易日期"][5:])).isoformat()
    donation_proof = evidence_from_projection(
        source_name=staged["source_name"], source_record_id=staged["source_record_id"],
        source_class=staged["source_class"], source_url=staged["source_url"],
        source_locator=donation_locator, title=staged["title"], summary=staged["summary"],
        observed_at=staged["observed_at"], retrieved_at=retrieved_at)
    donation = Relationship(
        id=stable_id("relationship", "reviewed_political_contribution", staged["source_record_id"]),
        source_entity_id=company_id, target_entity_id=wang_id,
        relationship_type="POLITICAL_CONTRIBUTION_TO",
        primary_evidence_id=donation_proof.id,
        observed_at=donation_proof.observed_at, confidence="HIGH",
        start_date=donation_date, date_precision="day",
        amount=row["收入金額"], currency="TWD", source_role=row["收支科目"])
    donation_bundle = empty_bundle()
    donation_bundle["evidence"] = [donation_proof.to_dict()]
    donation_bundle["relationships"] = [donation.to_dict()]
    donation_bundle["relationship_evidence"] = [{"relationship_id": donation.id,
                                                  "evidence_id": donation_proof.id,
                                                  "support_type": "supports"}]

    staged_asset, asset = asset_extract()
    asset_crosswalk_id = stable_id("political_crosswalk", "control_yuan", staged_asset["source_record_id"])
    asset_locator = dict(staged_asset["source_locator"])
    asset_locator.update({"politician_match_method": "exact_official_identifier",
                          "politician_identifier_origin": "reviewed_crosswalk",
                          "politician_crosswalk_id": asset_crosswalk_id,
                          "politician_identifier_namespace": "tw:legislative_yuan:legislator_number",
                          "politician_identifier_value": HUANG_LGNO,
                          "declaration_key": asset["declaration_key"],
                          "declaration_version": 1})
    asset_proof = evidence_from_projection(
        source_name=staged_asset["source_name"],
        source_record_id=staged_asset["source_record_id"],
        source_class=staged_asset["source_class"],
        source_url=staged_asset["source_url"],
        source_locator=asset_locator, title=staged_asset["title"],
        summary=staged_asset["summary"],
        observed_at=staged_asset["observed_at"], retrieved_at=retrieved_at)
    asset_bundle = empty_bundle()
    asset_bundle["evidence"] = [asset_proof.to_dict()]

    def crosswalk(kind, source_record_id, proof, entity_id, lgno, master_id,
                  constituency, official_url, basis, company_entity_id=None):
        return {"id": donation_crosswalk_id if kind == "contribution" else asset_crosswalk_id,
                "source_kind": kind, "source_record_id": source_record_id,
                "source_subject_name": "王鴻薇" if kind == "contribution" else "黃珊珊",
                "source_evidence_id": proof.id, "politician_entity_id": entity_id,
                "official_legislator_number": lgno, "term_number": 11,
                "constituency": constituency, "master_evidence_id": master_id,
                "company_entity_id": company_entity_id,
                "company_uniform_number": UNIFORM if company_entity_id else None,
                "independent_official_url": official_url,
                "review_basis": basis, "reviewed_by": reviewed_by,
                "reviewed_at": retrieved_at, "status": "approved"}

    return {"company_bundle": company_bundle, "contribution_bundle": donation_bundle,
            "asset_bundle": asset_bundle, "asset_declaration_id": asset["id"],
            "asset_evidence_id": asset_proof.id,
            "crosswalks": [
                crosswalk("contribution", donation_proof.source_record_id, donation_proof,
                          wang_id, WANG_LGNO, wang_master_evidence_id,
                          "臺北市第3選舉區", WANG_CEC_URL,
                          "election_term_constituency", company_id),
                crosswalk("asset", asset_proof.source_record_id, asset_proof,
                          huang_id, HUANG_LGNO, huang_master_evidence_id,
                          "全國不分區及僑居國外國民", HUANG_LY_URL,
                          "office_term_date")],
            "quality": {"source_contribution_rows": 1, "source_asset_rows": 1,
                        "reviewed_crosswalks": 2,
                        "name_only_matches": 0,
                        "company_exact_uniform_matches": 1,
                        "politician_official_identifiers": [WANG_LGNO, HUANG_LGNO]}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wang-master-evidence-id", required=True)
    parser.add_argument("--huang-master-evidence-id", required=True)
    parser.add_argument("--reviewed-by", required=True)
    args = parser.parse_args()
    result = prepare(wang_master_evidence_id=args.wang_master_evidence_id,
                     huang_master_evidence_id=args.huang_master_evidence_id,
                     reviewed_by=args.reviewed_by)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
