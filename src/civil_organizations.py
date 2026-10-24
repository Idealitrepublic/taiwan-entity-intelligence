"""Source-scoped civil-organization observations from the MOI historical roster.

The roster has no durable registration identifier. A row is never equated with
another snapshot, a company, a person, or another organization by name alone.
"""
import csv
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from src.entities.models import Entity, evidence_from_projection, stable_id, timestamp


SOURCE_NAME = "MOI nationwide people's associations roster"
SOURCE_URL = "https://data.gov.tw/dataset/13603"
DOWNLOAD_URL = ("https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
                "DA99D92C-531A-40B2-AFF6-D5C1C7AEE022/resource/"
                "6CD84A67-522B-4811-96B8-3E7942AE3C1B/download")
EXPECTED_COLUMNS = {"SeqNo", "Name", "Date_of_Establishment", "address", "Chairman", "session"}


def roster_bundles(path: Path, *, retrieved_at: str, batch_size: int = 75,
                   publication_status: str = "draft"):
    """Yield bounded ingestion bundles; omit address/chairperson and all name joins.

    `publication_status='published'` means the historical row is published, not
    that the organization is currently registered or legally an NGO.
    """
    timestamp(retrieved_at)
    if publication_status not in ("draft", "published") or not 1 <= batch_size <= 100:
        raise ValueError("Invalid publication state or batch size")
    snapshot_hash = sha256(path.read_bytes()).hexdigest()
    seen = set()
    bundle = {"entities": [], "evidence": [], "entity_evidence": []}
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not EXPECTED_COLUMNS.issubset(reader.fieldnames or []):
            raise ValueError("Unexpected MOI roster columns")
        for row_number, row in enumerate(reader, 2):
            seq = (row.get("SeqNo") or "").strip()
            name = (row.get("Name") or "").strip()
            if seq == "序號" and name == "協會名稱":
                continue
            if not seq.isascii() or not seq.isdecimal() or not name or len(name) > 500:
                raise ValueError(f"Invalid MOI roster row {row_number}")
            if seq in seen:
                raise ValueError(f"Duplicate MOI roster sequence {seq}")
            seen.add(seq)
            source_id = f"{snapshot_hash}:{seq}"
            entity = Entity(id=stable_id("entity", SOURCE_NAME, source_id),
                            entity_type="CivilOrganization", canonical_name=name,
                            display_name=name, source=SOURCE_NAME, source_id=source_id,
                            identity_status="SOURCE_SCOPED",
                            publication_status=publication_status)
            locator = {"dataset_id": "13603", "download_url": DOWNLOAD_URL,
                       "snapshot_sha256": snapshot_hash, "csv_row": row_number,
                       "source_seq_no": seq, "establishment_date_raw":
                       (row.get("Date_of_Establishment") or "").strip(),
                       "scope": "historical_roster_not_current_registration"}
            evidence = evidence_from_projection(
                source_name=SOURCE_NAME, source_record_id=source_id,
                source_class="Government Open Data", source_url=SOURCE_URL,
                source_locator=locator, title=f"內政部團體名冊歷史紀錄：{name}",
                summary="官方名冊歷史收錄紀錄；不證明現行登記、營運狀態或與同名實體相同。",
                observed_at=retrieved_at, retrieved_at=retrieved_at,
                publication_status=publication_status)
            bundle["entities"].append(entity.to_dict())
            bundle["evidence"].append(evidence.to_dict())
            bundle["entity_evidence"].append({"entity_id": entity.id,
                                              "evidence_id": evidence.id,
                                              "fact_type": "historical_roster_entry"})
            if len(bundle["entities"]) == batch_size:
                yield bundle
                bundle = {"entities": [], "evidence": [], "entity_evidence": []}
    if bundle["entities"]:
        yield bundle


def utc_now():
    return datetime.now(timezone.utc).isoformat()
