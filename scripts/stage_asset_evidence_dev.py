#!/usr/bin/env python3
"""Extract one source-verified, unpublished asset line from Gazette 319.

The Gazette names an office holder but supplies no Legislative Yuan ``lgno``.
This Development-only audit sample remains draft until a reviewed crosswalk
supports publication. It never creates a company ownership Relationship.
"""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import subprocess

from src.entities.models import evidence_from_projection, stable_id


SOURCE_URL = ("https://www-ws.cy.gov.tw/Download.ashx?icon=..pdf"
              "&n=44CQ5buJ5pS%2F5bCI5YiK56ysMzE55pyf44CRLnBkZg%3D%3D"
              "&u=LzAwMS9VcGxvYWQvMS9yZWxmaWxlLzg4NjEvMzc0MzMv"
              "ZjBjMzcyMDEtMDgwYy00YzE2LTk3ZDQtMDlmODI3NjUyY2VhLnBkZg%3D%3D")
SOURCE_NAME = "監察院廉政專刊財產申報資料"
SOURCE_RECORD_ID = "gazette:319:printed-page-37:huang-shan-shan:vehicle-1"
POLITICIAN_ID = stable_id("entity", "tw:legislative_yuan:legislator_number", "00082")


def extract():
    from pypdf import PdfReader
    raw = subprocess.check_output(
        ["curl", "--fail", "--silent", "--show-error", "--location", SOURCE_URL],
        timeout=90)
    pdf = PdfReader(io.BytesIO(raw))
    if len(pdf.pages) <= 40:
        raise ValueError("Gazette PDF is missing the expected declaration pages")
    identity_page = pdf.pages[39].extract_text() or ""
    asset_page = pdf.pages[40].extract_text() or ""
    if not all(value in identity_page for value in
               ("申報人姓名  黃珊珊", "立法委員", "115 年 02 月 01 日")):
        raise ValueError("Gazette declarant, office, or date changed")
    if not all(value in asset_page for value in ("汽車", "Tesla 2,790 黃珊珊", "1,985,400")):
        raise ValueError("Gazette vehicle row changed")
    retrieved = datetime.now(timezone.utc).isoformat()
    pdf_hash = sha256(raw).hexdigest()
    evidence = evidence_from_projection(
        source_name=SOURCE_NAME, source_record_id=SOURCE_RECORD_ID,
        source_class="Primary Source", source_url=SOURCE_URL,
        source_locator={"gazette_issue": 319, "pdf_page": 41,
                        "printed_page": 37, "pdf_sha256": pdf_hash,
                        "declarant_name": "黃珊珊", "office": "立法委員",
                        "declaration_date": "2026-02-01",
                        "politician_match_method": "reviewed_name_office_date_pending_crosswalk",
                        "legislative_yuan_identifier_candidate": "00082",
                        "publication_status": "draft"},
        title="廉政專刊第319期：黃珊珊汽車申報",
        summary="汽車 Tesla；申報取得價額 1,985,400 TWD；申報日 2026-02-01",
        observed_at="2026-02-01T00:00:00+08:00", retrieved_at=retrieved)
    declaration_key = sha256(SOURCE_RECORD_ID.encode()).hexdigest()
    asset = {"id": stable_id("asset_declaration", SOURCE_NAME, SOURCE_RECORD_ID),
             "politician_id": POLITICIAN_ID, "declaration_year": 2026,
             "declaration_key": declaration_key, "declaration_version": 1,
             "asset_type": "VEHICLE", "asset_name": "Tesla 汽車",
             "amount": "1985400", "currency": "TWD", "quantity": None,
             "quantity_unit": None, "company_name": None,
             "company_entity_id": None, "relationship_id": None,
             "primary_evidence_id": evidence.id, "publication_status": "draft"}
    return evidence.to_dict(), asset


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    evidence, asset = extract()
    if args.report:
        print(json.dumps({"gazette_issue": 319, "draft_assets": 1,
                          "public_assets": 0, "pdf_sha256": evidence["source_locator"]["pdf_sha256"],
                          "reason": "official Gazette does not contain legislator ID"}))
    else:
        print(json.dumps({"evidence": evidence, "asset_declaration": asset},
                         ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
