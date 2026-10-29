"""Import row-level MOI lobbying observations, without inferring person links."""
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ingest_civil_organizations_dev import apply_bundles  # noqa: E402
from src.entities.models import Entity, evidence_from_projection, stable_id  # noqa: E402

MARKER = re.compile(r"^\s*(\d{1,2})\s+(\d{2,3})\s*(?:年)?\s*(?:第)?", re.M)


def build(pages, *, source_url, source_title, snapshot_hash, retrieved_at):
    if not source_url.startswith("https://ws.moi.gov.tw/Download.ashx?"):
        raise ValueError("An official MOI document URL is required")
    text = "\n".join(pages)
    if "遊說者申請登記事項" not in text:
        raise ValueError("Not a lobbying registration table")
    markers = list(MARKER.finditer(text))
    if not markers or [int(m[1]) for m in markers] != list(range(1, len(markers) + 1)):
        raise ValueError("Source row numbering is missing or ambiguous")
    bundle = {key: [] for key in ("entities", "identifiers", "evidence", "entity_evidence", "relationships", "relationship_evidence", "legacy_map")}
    source_name = "內政部｜" + source_title.replace("[另開新視窗]", "").removesuffix(".pdf")
    for index, marker in enumerate(markers):
        body = text[marker.start():markers[index + 1].start() if index + 1 < len(markers) else None]
        fields = re.match(r"\s*\d+\s+(\d{2,3})\s*(?:年)?\s*第?\s*([1-4])\s*季\s*(.*?)\s*"
                          r"(部長|政務次長|常務次長)\s+([\u4e00-\u9fff]{2,4})\s+"
                          r"(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", body, re.S)
        if not fields:
            raise ValueError("Registration fields require layout review")
        year, quarter, applicant, role, target, approval_year, month, day = fields.groups()
        approval = date(int(approval_year) + 1911, int(month), int(day)).isoformat()
        applicant = re.sub(r"\s+", "", applicant)
        organization = any(label in applicant for label in ("法人", "公會", "工會", "聯合會", "協會", "基金會"))
        # Do not turn the natural-person list in a petition into a directory or
        # an inferred relationship to same-name people elsewhere in the graph.
        applicant_label = applicant if organization else "原表列示之自然人（未建立人物身分連結）"
        compact = re.sub(r"\s+", "", body)
        document = re.search(r"台內政風字第(\d+)號", compact)
        policy_subjects = [value for pair in re.findall(r"《([^》]+)》|「([^」]+)」", compact)
                           for value in pair if value]
        offset = 0
        source_pages = []
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        for page_index, page in enumerate(pages, 1):
            if offset < end and offset + len(page) >= marker.start():
                source_pages.append(page_index)
            offset += len(page) + 1
        record = f"moi-lobby:{snapshot_hash}:row:{marker[1]}"
        title = f"遊說登記事項｜{applicant_label}｜{int(year)+1911}年第{quarter}季｜來源第{marker[1]}筆"
        entity = Entity(id=stable_id("entity", "moi:lobby-registration-observation", record),
                        entity_type="LobbyingRecord", canonical_name=title, display_name=title,
                        source=source_name, source_id=record, identity_status="SOURCE_SCOPED", publication_status="published")
        proof = evidence_from_projection(source_name=source_name, source_record_id=record,
            source_class="Primary Source", source_url=source_url,
            source_locator={"snapshot_sha256": snapshot_hash, "pdf_pages": source_pages, "table_row": int(marker[1]),
                            "report_year": int(year)+1911, "quarter": int(quarter), "applicant_label": applicant_label,
                            "target_office_label": role, "target_name_in_source": target,
                            "approval_date": approval, "approval_document_number": document[0] if document else None,
                            "change_mentioned_in_source": "變更" in compact, "termination_mentioned_in_source": "終止" in compact,
                            "quoted_policy_subjects": policy_subjects,
                            "identity_scope": "registration_item_observation_not_person_or_case_merge"},
            title=title, summary=f"原表記載遊說登記／變更／終止事項；被遊說者欄：{role} {target}；核准日期欄：{approval}。"
                                + ("原表引述議題：" + "；".join(policy_subjects) + "。" if policy_subjects else "") +
                                "遊說目的、期間與備註請核對原始總表；不據此判定違法或合併人物／團體身分。",
            observed_at=approval + "T00:00:00+08:00", retrieved_at=retrieved_at, publication_status="published")
        bundle["entities"].append(entity.to_dict())
        bundle["evidence"].append(proof.to_dict())
        bundle["entity_evidence"].append({"entity_id": entity.id, "evidence_id": proof.id, "fact_type": "lobby_registration_observation"})
    return bundle, source_name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_directory", type=Path)
    parser.add_argument("--apply-dev", action="store_true")
    args = parser.parse_args()
    folder = args.snapshot_directory.resolve()
    if folder.is_relative_to(ROOT) or folder.stat().st_mode & 0o077:
        parser.error("Use owner-only official snapshots outside the repository")
    from pypdf import PdfReader
    seen, plans = set(), []
    for source in json.loads((folder / "lobby_inventory.json").read_text()):
        if source.get("status") != "downloaded" or source["sha256"] in seen:
            continue
        path = folder / source["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("Official document hash mismatch")
        pages = [page.extract_text() or "" for page in PdfReader(path).pages]
        bundle, source_name = build(pages, source_url=source["url"], source_title=source["title"],
            snapshot_hash=source["sha256"], retrieved_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat())
        plans.append((bundle, source_name))
        seen.add(source["sha256"])
    # Validate every document before any write.
    if args.apply_dev:
        for bundle, source_name in plans:
            apply_bundles([bundle], source_name=source_name)
    print(json.dumps({"applied_to_development": args.apply_dev, "unique_official_documents": len(plans),
                      "registration_item_observations": sum(len(bundle["entities"]) for bundle, _ in plans),
                      "relationships_created": 0, "scope": "MOI-listed totals only; not all agencies or unique lobbying cases"}))


if __name__ == "__main__":
    main()
