"""Publish a bounded Taipei corporate-donation review using CEC + LY identities.

Only the official term-11 election winners, exact constituency/term/party and
published exact company identifiers qualify. Source personal donors are never
projected. Other candidates and conflicting labels remain unresolved.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ingest_civil_organizations_dev import development_environment  # noqa: E402
from scripts.stage_contribution_evidence_dev import normalize_row  # noqa: E402
from src.entities.models import evidence_from_projection, stable_id  # noqa: E402
from src.relationships.models import Relationship  # noqa: E402

CEC_URL = "https://web.cec.gov.tw/api/file/4a5b0001-a14d-4319-8dc1-676f5312c702.pdf"
CEC_HASH = "3d1cd84e4642cd5dd717acea7f9ea60ebffc085a30a02235bb73b25ecc7692f3"


def reviewed_candidates(cec_text, before):
    if not ("113年1月19日" in cec_text and "第 11 屆立法委員選舉當選人名單" in cec_text):
        raise ValueError("Official election/date context missing")
    pattern = r"臺北市第\s*([1-8])\s*選舉區\s+(\S+)\s+[男女]\s+\S+\s+(\S+)\s+[\d,]+"
    winners = re.findall(pattern, cec_text)
    if len(winners) != 8 or len({row[0] for row in winners}) != 8:
        raise ValueError("Expected eight unambiguous Taipei constituency records")
    entities = {row["id"]: row for row in before["entities"]}
    result = {}
    for district, name, party in winners:
        constituency = f"臺北市第{district}選舉區"
        matches = [term for term in before["politician_terms"]
                   if term["term_number"] == 11 and term["constituency"] == constituency
                   and term.get("legislator_number") and term["start_date"] == "2024-02-01"
                   and term["publication_status"] == "published"
                   and entities[term["politician_entity_id"]]["display_name"] == name
                   and entities[term["politician_entity_id"]]["identity_status"] == "EXACT"
                   and entities.get(term["party_entity_id"], {}).get("display_name") == party]
        if len(matches) != 1 or name in result:
            raise ValueError("CEC district/party does not uniquely match an exact official LY term")
        result[name] = matches[0]
    return result


def review_rows(rows, candidates, companies, before, *, retrieved_at, archive_hash):
    by_uniform = {}
    for company in companies:
        key = company["uniform_number"]
        if key in by_uniform:
            raise ValueError("Ambiguous company identifier")
        by_uniform[key] = company
    known = {row["source_record_id"] for row in before["crosswalks"] if row["source_kind"] == "contribution"}
    bundles, crosswalks, skipped = [], [], []
    seen = set()
    for csv_row, row in enumerate(rows, 2):
        if row.get("收支科目") != "營利事業捐贈收入":
            continue
        evidence = normalize_row(row, retrieved_at)
        if evidence is None:
            skipped.append("invalid_corporate_record")
            continue
        record_id = evidence["source_record_id"]
        if record_id in seen:
            raise ValueError("Duplicate official source serial")
        seen.add(record_id)
        if row.get("返還/繳庫"):
            skipped.append("returned_or_remitted_record_requires_distinct_presentation")
            continue
        if row.get("金錢類") != "金錢" or row.get("更正註記") or row.get("資料更正日期"):
            skipped.append("noncash_or_corrected_record_requires_review")
            continue
        if record_id in known:
            skipped.append("already_published_crosswalk")
            continue
        term = candidates.get(row.get("擬參選人／政黨"))
        if term is None or row.get("選舉名稱") != "113年立法委員選舉" or row.get("申報序號／年度") != "首次申報":
            skipped.append("candidate_without_reviewed_election_identity")
            continue
        company = by_uniform.get(row.get("身分證／統一編號"))
        if not company or company.get("confidence") != "EXACT":
            skipped.append("company_without_published_exact_identifier")
            continue
        if company["name"] != row.get("捐贈者／支出對象"):
            skipped.append("donor_registry_label_conflict_requires_review")
            continue
        crosswalk_id = stable_id("political_crosswalk", "control_yuan", record_id)
        locator = {**evidence["source_locator"], "csv_row": csv_row, "snapshot_sha256": archive_hash,
                   "cec_source_url": CEC_URL, "cec_snapshot_sha256": CEC_HASH, "cec_pdf_page": 1,
                   "constituency": term["constituency"], "term_number": 11,
                   "politician_match_method": "exact_official_identifier",
                   "politician_identifier_origin": "reviewed_crosswalk",
                   "politician_crosswalk_id": crosswalk_id,
                   "politician_identifier_namespace": "tw:legislative_yuan:legislator_number",
                   "politician_identifier_value": term["legislator_number"],
                   "match_method": "exact_uniform_number", "uniform_number": company["uniform_number"],
                   "contribution_year": int(evidence["observed_at"][:4]),
                   "return_status": row.get("返還/繳庫") or "not_marked_returned_in_source",
                   "money_type": row.get("金錢類"), "donation_method": row.get("捐贈方式"),
                   "resolution_status": "reviewed_election_term_constituency_company_identifier"}
        proof = evidence_from_projection(
            **{k: evidence[k] for k in ("source_name", "source_record_id", "source_class", "source_url", "title", "summary", "observed_at", "retrieved_at")},
            source_locator=locator)
        relationship = Relationship(
            id=stable_id("relationship", "reviewed_political_contribution", record_id),
            source_entity_id=company["id"], target_entity_id=term["politician_entity_id"],
            relationship_type="POLITICAL_CONTRIBUTION_TO", primary_evidence_id=proof.id,
            observed_at=proof.observed_at, confidence="HIGH", start_date=proof.observed_at[:10],
            date_precision="day", amount=row["收入金額"], currency="TWD", source_role=row["收支科目"])
        bundles.append({"entities": [], "identifiers": [], "evidence": [proof.to_dict()], "entity_evidence": [],
                        "relationships": [relationship.to_dict()], "legacy_map": [],
                        "relationship_evidence": [{"relationship_id": relationship.id, "evidence_id": proof.id, "support_type": "supports"}]})
        crosswalks.append({"id": crosswalk_id, "source_kind": "contribution", "source_record_id": record_id,
                          "source_subject_name": row["擬參選人／政黨"], "source_evidence_id": proof.id,
                          "politician_entity_id": term["politician_entity_id"], "official_legislator_number": term["legislator_number"],
                          "term_number": 11, "constituency": term["constituency"], "master_evidence_id": term["primary_evidence_id"],
                          "company_entity_id": company["id"], "company_uniform_number": company["uniform_number"],
                          "independent_official_url": CEC_URL, "review_basis": "election_term_constituency",
                          "reviewed_by": "Codex: CEC constituency/term/party + LY official identifier review",
                          "reviewed_at": retrieved_at, "status": "approved"})
    from collections import Counter
    return bundles, crosswalks, {"corporate_source_rows": len(seen), "reviewed_publishable_rows": len(bundles),
                                 "dispositions": dict(Counter(skipped)), "name_only_matches": 0}


def transaction(bundles, crosswalks):
    pieces = ["BEGIN; SET LOCAL standard_conforming_strings=on; SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='90s';",
              "DO $$BEGIN IF pg_database_size(current_database())>480000000 THEN RAISE EXCEPTION 'Development capacity guard'; END IF; END$$; SET LOCAL ROLE service_role;"]
    for bundle, crosswalk in zip(bundles, crosswalks, strict=True):
        payload = json.dumps(bundle, ensure_ascii=False).replace("'", "''")
        review = json.dumps(crosswalk, ensure_ascii=False).replace("'", "''")
        proof_id = bundle["evidence"][0]["id"]
        relationship_id = bundle["relationships"][0]["id"]
        pieces.extend([f"SELECT public.tei_ingest_bundle('{payload}'::jsonb);",
                       "INSERT INTO public.political_identity_crosswalks SELECT (jsonb_populate_record(NULL::public.political_identity_crosswalks,"
                       f"'{review}'::jsonb)).* ON CONFLICT DO NOTHING;",
                       f"UPDATE public.evidence_records SET publication_status='published' WHERE id='{proof_id}' AND publication_status='draft';",
                       f"UPDATE public.relationships SET status='published' WHERE id='{relationship_id}' AND status='draft';"])
    pieces.append("SET CONSTRAINTS ALL IMMEDIATE; COMMIT;")
    return "\n".join(pieces)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_directory", type=Path)
    parser.add_argument("--apply-dev", action="store_true")
    args = parser.parse_args()
    folder = args.snapshot_directory.resolve()
    if folder.is_relative_to(ROOT) or folder.stat().st_mode & 0o077:
        parser.error("Use an owner-only snapshot directory outside the repository")
    cec = (folder / "cec-term11.pdf").read_bytes()
    if hashlib.sha256(cec).hexdigest() != CEC_HASH:
        parser.error("CEC source changed; review before publication")
    from pypdf import PdfReader
    text = PdfReader(io.BytesIO(cec)).pages[0].extract_text()
    before = json.loads((folder / "development_before.json").read_text())
    candidates = reviewed_candidates(text, before)
    raw = (folder / "contributions_taipei.zip").read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        with archive.open("incomes.csv") as stream:
            rows = list(csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig")))
    companies = json.loads((folder / "companies_before.json").read_text())
    bundles, crosswalks, report = review_rows(rows, candidates, companies, before,
        retrieved_at=datetime.fromtimestamp((folder / "contributions_taipei.zip").stat().st_mtime, timezone.utc).isoformat(),
        archive_hash=hashlib.sha256(raw).hexdigest())
    for crosswalk in crosswalks:
        crosswalk["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    if args.apply_dev and bundles:
        result = subprocess.run(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1"], input=transaction(bundles, crosswalks),
                                text=True, capture_output=True, env=development_environment(), timeout=180)
        if result.returncode:
            raise RuntimeError("Development contribution transaction rolled back; details suppressed")
    report["applied_to_development"] = args.apply_dev
    output = folder / "contribution_review_result.json"
    output.write_text(json.dumps(report, ensure_ascii=False))
    output.chmod(0o600)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
