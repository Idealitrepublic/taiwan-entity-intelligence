"""Review numeric lines in one official declaration, without name-based issuers.

The pinned official PDF and an already approved filing/office/date crosswalk
are mandatory. Unknown values, blank categories and unparsed rows are not zero.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ingest_civil_organizations_dev import development_environment  # noqa: E402
from scripts.stage_asset_evidence_dev import SOURCE_URL, SOURCE_NAME  # noqa: E402
from src.entities.models import evidence_from_projection, stable_id  # noqa: E402

PDF_HASH = "f5889dacf9f6d0b855c91c372bb77856d93ecc342e0af986701e22485339596e"
NUMBER = r"[\d,]+(?:\.\d+)?"


def decimal(value):
    return Decimal(value.replace(",", ""))


def parse_numeric_lines(pages):
    deposits = [(41, pages[41].split("（七）存款", 1)[1]),
                (42, pages[42].split("（八）有價證券", 1)[0])]
    sections = [(42, "STOCK", pages[42].split("1.股票", 1)[1].split("2.債券", 1)[0]),
                (42, "FUND", pages[42].split("3.基金受益憑證", 1)[1]),
                (43, "FUND", pages[43].split("4.其他有價證券", 1)[0])]
    rows = []
    for page, text in deposits:
        for line in text.splitlines():
            m = re.fullmatch(r"(.+?)\s+(綜合存款|活期儲蓄存款|定期存款|活期存款|支票存款|活儲證券戶)\s+"
                             r"(新臺幣|紐西蘭幣|美元|日圓|澳幣)\s+黃珊珊.*?\s+(" + NUMBER + r")\s*", line)
            if m:
                rows.append({"asset_type": "DEPOSIT", "asset_name": f"{m[1].strip()}｜{m[2]}｜{m[3]}",
                             "amount": str(decimal(m[4])), "quantity": None, "quantity_unit": None,
                             "company_name": None, "pdf_page": page})
    for page, asset_type, text in sections:
        for line in text.splitlines():
            m = re.fullmatch(r"(.+?)\s+黃珊珊\s+(.*?)\s*(" + NUMBER + r")\s+(" + NUMBER + r")\s*(美元)?\s+(" + NUMBER + r")\s*", line)
            if m:
                name = m[1].strip()
                if name == "Vanguard S&P 500":
                    if not re.search(r"^ETF\s*$", text, re.M):
                        raise ValueError("Wrapped fund name missing")
                    name += " ETF"
                rows.append({"asset_type": asset_type, "asset_name": name + (f"｜{m[2].strip()}" if m[2].strip() else ""),
                             "amount": str(decimal(m[6])), "quantity": str(decimal(m[3])),
                             "quantity_unit": "股" if asset_type == "STOCK" else "單位",
                             "company_name": name if asset_type == "STOCK" else None, "pdf_page": page})
    for line in pages[44].splitlines():
        m = re.match(r"授信\s+黃珊珊\s+(.+?)\s+([\d,]+)\s+\d+年", line)
        if m:
            rows.append({"asset_type": "DEBT", "asset_name": f"授信｜{m[1].strip()}", "amount": str(decimal(m[2])),
                         "quantity": None, "quantity_unit": None, "company_name": None, "pdf_page": 44})
    expected = {"DEPOSIT": (28, Decimal("933062.10")), "STOCK": (6, Decimal("8373692")),
                "FUND": (6, Decimal("914669.05")), "DEBT": (7, Decimal("20762820"))}
    for kind, (count, total) in expected.items():
        selected = [row for row in rows if row["asset_type"] == kind]
        if len(selected) != count or sum(decimal(row["amount"]) for row in selected) != total:
            raise ValueError(f"Official {kind} row count/amount reconciliation failed")
    return rows


def parse_unvalued_lines(pages):
    rows = []
    land = pages[40].split("1.土地", 1)[1].split("2.建物", 1)[0]
    buildings = pages[40].split("2.建物", 1)[1].split("（三）", 1)[0]
    for kind, text, expected in (("土地", land, 3), ("建物", buildings, 6)):
        chunks = re.split(r"(?=^(?:新北市汐止區金龍段|臺北市北投區行義段四小段))", text, flags=re.M)[1:]
        if len(chunks) != expected or any("黃珊珊" not in chunk or "(超過五年)" not in chunk for chunk in chunks):
            raise ValueError("Property row identity/count/value-marker mismatch")
        for index, chunk in enumerate(chunks, 1):
            location = chunk.splitlines()[0].split()[0]
            rows.append({"asset_type": "REAL_ESTATE", "asset_name": f"{kind}｜{location}｜來源第{index}筆",
                         "amount": None, "quantity": None, "quantity_unit": None,
                         "company_name": None, "pdf_page": 40})
    section = pages[43].split("2.保險", 1)[1].split("3.虛擬資產", 1)[0]
    chunks = re.split(r"(?=^(?:南\s*山|國\s*泰|富\s*邦)\s*人\s*壽\s*保\s*險)", section, flags=re.M)[1:]
    if len(chunks) != 6:
        raise ValueError("Insurance row count changed")
    for chunk in chunks:
        if "黃珊珊" not in chunk or "○" not in chunk:
            raise ValueError("Insurance ownership/redaction marker missing")
        insurer, remaining = chunk.split("股份有限公司", 1)
        insurer = re.sub(r"\s+", "", insurer) + "股份有限公司"
        name = re.sub(r"\s+", "", remaining.split("○", 1)[0])
        if not name or len(name) > 100:
            raise ValueError("Insurance name parse failed")
        rows.append({"asset_type": "INSURANCE", "asset_name": f"{insurer}｜{name}", "amount": None,
                     "quantity": None, "quantity_unit": None, "company_name": insurer, "pdf_page": 43})
    return rows


def prepare(rows, crosswalk, *, retrieved_at):
    if (crosswalk.get("source_kind") != "asset" or crosswalk.get("status") != "approved"
            or crosswalk.get("source_subject_name") != "黃珊珊" or crosswalk.get("official_legislator_number") != "00082"):
        raise ValueError("Missing previously reviewed filing identity")
    bundle = {key: [] for key in ("entities", "identifiers", "evidence", "entity_evidence", "relationships",
                                  "relationship_evidence", "legacy_map", "asset_declarations")}
    crosswalks = []
    counts = {}
    for row in rows:
        kind = row["asset_type"]
        counts[kind] = counts.get(kind, 0) + 1
        record = f"gazette:319:printed-page-{row['pdf_page']-4}:huang-shan-shan:{kind.lower()}-{counts[kind]}"
        key = hashlib.sha256(record.encode()).hexdigest()
        crosswalk_id = stable_id("political_crosswalk", "control_yuan", record)
        locator = {"gazette_issue": 319, "pdf_page": row["pdf_page"], "printed_page": row["pdf_page"] - 4,
                   "pdf_sha256": PDF_HASH, "declarant_name": "黃珊珊", "office": "立法委員",
                   "declaration_date": "2026-02-01", "declaration_key": key, "declaration_version": 1,
                   "asset_type": kind, "section_row": counts[kind], "amount": row["amount"],
                   "quantity": row["quantity"], "quantity_unit": row["quantity_unit"],
                   "valuation_basis": "source_reported_twd_equivalent" if row["amount"] is not None else "not_provided_in_source",
                   "politician_match_method": "exact_official_identifier",
                   "politician_identifier_origin": "reviewed_crosswalk", "politician_crosswalk_id": crosswalk_id,
                   "politician_identifier_namespace": "tw:legislative_yuan:legislator_number",
                   "politician_identifier_value": "00082", "company_match_method": "no_exact_identifier"}
        proof = evidence_from_projection(source_name=SOURCE_NAME, source_record_id=record,
            source_class="Primary Source", source_url=SOURCE_URL, source_locator=locator,
            title=f"廉政專刊第319期：黃珊珊｜{row['asset_name']}",
            summary=f"申報日2026-02-01；{row['asset_name']}；" +
                    (f"申報新臺幣價額 {row['amount']} TWD" if row["amount"] is not None else "來源未載明價額；不得當作零元"),
            observed_at="2026-02-01T00:00:00+08:00", retrieved_at=retrieved_at)
        bundle["evidence"].append(proof.to_dict())
        bundle["asset_declarations"].append({"id": stable_id("asset_declaration", SOURCE_NAME, record),
            "politician_id": crosswalk["politician_entity_id"], "declaration_year": 2026,
            "declaration_key": key, "declaration_version": 1, "supersedes_declaration_id": None,
            **{k: row[k] for k in ("asset_type", "asset_name", "amount", "quantity", "quantity_unit", "company_name")},
            "currency": "TWD" if row["amount"] is not None else None, "company_entity_id": None, "relationship_id": None,
            "primary_evidence_id": proof.id, "publication_status": "draft"})
        crosswalks.append({**crosswalk, "id": crosswalk_id, "source_record_id": record,
                           "source_evidence_id": proof.id, "reviewed_at": retrieved_at,
                           "reviewed_by": "Codex: same official filing hash, office/date and exact LY identifier review"})
    return bundle, crosswalks


def transaction(bundle, crosswalks):
    literal = json.dumps(bundle, ensure_ascii=False).replace("'", "''")
    lines = ["BEGIN; SET LOCAL standard_conforming_strings=on; SET LOCAL statement_timeout='90s';",
             "DO $$BEGIN IF pg_database_size(current_database())>480000000 THEN RAISE EXCEPTION 'Development capacity guard'; END IF; END$$; SET LOCAL ROLE service_role;",
             f"SELECT public.tei_ingest_asset_declaration_bundle('{literal}'::jsonb);"]
    for crosswalk in crosswalks:
        review = json.dumps(crosswalk, ensure_ascii=False).replace("'", "''")
        lines.append("INSERT INTO public.political_identity_crosswalks SELECT (jsonb_populate_record(NULL::public.political_identity_crosswalks,"
                     f"'{review}'::jsonb)).* ON CONFLICT DO NOTHING;")
    for row in bundle["asset_declarations"]:
        lines.extend([f"UPDATE public.evidence_records SET publication_status='published' WHERE id='{row['primary_evidence_id']}' AND publication_status='draft';",
                      f"UPDATE public.asset_declarations SET publication_status='published' WHERE id='{row['id']}' AND publication_status='draft';"])
    return "\n".join(lines + ["SET CONSTRAINTS ALL IMMEDIATE; COMMIT;"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_directory", type=Path)
    parser.add_argument("--apply-dev", action="store_true")
    args = parser.parse_args()
    folder = args.snapshot_directory.resolve()
    if folder.is_relative_to(ROOT) or folder.stat().st_mode & 0o077:
        parser.error("Use owner-only snapshots outside repository")
    path = folder / "gazette319.pdf"
    if hashlib.sha256(path.read_bytes()).hexdigest() != PDF_HASH:
        parser.error("Official filing changed; review required")
    from pypdf import PdfReader
    pdf = PdfReader(path)
    if not all(marker in (pdf.pages[39].extract_text() or "") for marker in
               ("申報人姓名  黃珊珊", "立法委員", "115 年 02 月 01 日")):
        parser.error("Official declarant/office/date changed")
    pages = {i + 1: pdf.pages[i].extract_text(extraction_mode="layout") for i in range(39, 44)}
    rows = parse_numeric_lines(pages) + parse_unvalued_lines({i + 1: pdf.pages[i].extract_text() for i in range(39, 44)})
    before = json.loads((folder / "development_before.json").read_text())
    crosswalk = next(row for row in before["crosswalks"] if row["source_kind"] == "asset")
    bundle, crosswalks = prepare(rows, crosswalk,
                                retrieved_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat())
    for item in crosswalks:
        item["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    if args.apply_dev:
        result = subprocess.run(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1"], input=transaction(bundle, crosswalks),
                                text=True, capture_output=True, env=development_environment(), timeout=180)
        if result.returncode:
            raise RuntimeError("Development asset transaction rolled back; connection details suppressed")
    from collections import Counter
    report = {"applied_to_development": args.apply_dev, "reviewed_rows": len(rows),
              "by_type": dict(Counter(row["asset_type"] for row in rows)), "company_relationships_created": 0,
              "source_date": "2026-02-01", "pdf_sha256": PDF_HASH,
              "source_rounding_difference_twd": {"DEPOSIT": "0.10", "FUND": "0.05"},
              "remaining": "Vehicle already published; source-empty categories are not fabricated. This is one filing, not national coverage."}
    output = folder / "asset_review_result.json"
    output.write_text(json.dumps(report, ensure_ascii=False))
    output.chmod(0o600)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
