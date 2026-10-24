"""Other official civil-group rosters; observations are source scoped, not joins."""
import csv
from hashlib import sha256
from pathlib import Path

from src.entities.models import Entity, evidence_from_projection, stable_id, timestamp


SOURCES = {
    "moi_foundations": {
        "name": "MOI national civil foundations roster",
        "dataset": "152434",
        "url": "https://data.gov.tw/dataset/152434",
        "download": "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/470F5551-E9B0-48A8-929C-F5395BFA4978/resource/F70DDD2B-4B3B-4AEA-8A91-7203808147EF/download",
        "columns": {"序號", "類型", "團體名稱", "成立日期", "負責人", "地址"},
        "name_column": "團體名稱", "description": "MOI foundation roster",
    },
    "mol_direct": ("mMY", "MOL directly supervised unions"),
    "mol_national": ("ZX7", "MOL national union federations"),
    "mol_province": ("Khk", "MOL provincial union federations"),
    "mol_county": ("pOZ", "MOL county/city union federations"),
    "mol_industry": ("yzf", "MOL national industry union federations"),
}
for _key, _value in list(SOURCES.items()):
    if isinstance(_value, tuple):
        _code, _name = _value
        SOURCES[_key] = {
            "name": _name, "dataset": "6278", "url": "https://data.gov.tw/dataset/6278",
            "download": f"https://apiservice.mol.gov.tw/OdService/download/A17000000J-020047-{_code}",
            "columns": {"序號", "工會名稱", "地址", "電話", "傳真"},
            "name_column": "工會名稱", "description": "MOL union roster",
        }


def official_roster_bundles(path: Path, source_key: str, *, retrieved_at: str,
                            batch_size: int = 75, publication_status: str = "draft"):
    """Ingest one complete snapshot with no person/address/phone or name-only link."""
    timestamp(retrieved_at)
    if source_key not in SOURCES or publication_status not in ("draft", "published"):
        raise ValueError("Invalid official source or publication state")
    if not 1 <= batch_size <= 100:
        raise ValueError("Invalid batch size")
    source = SOURCES[source_key]
    snapshot_hash = sha256(path.read_bytes()).hexdigest()
    seen = set()
    bundle = {"entities": [], "evidence": [], "entity_evidence": []}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not source["columns"].issubset(reader.fieldnames or []):
            raise ValueError("Unexpected official roster columns")
        for row_number, row in enumerate(reader, 2):
            seq = (row.get("序號") or "").strip()
            name = (row.get(source["name_column"]) or "").strip()
            if not seq.isascii() or not seq.isdecimal() or not name or len(name) > 500:
                raise ValueError(f"Invalid official roster row {row_number}")
            if seq in seen:
                raise ValueError(f"Duplicate official roster sequence {seq}")
            seen.add(seq)
            source_id = f"{snapshot_hash}:{seq}"
            entity = Entity(id=stable_id("entity", source["name"], source_id),
                            entity_type="CivilOrganization", canonical_name=name,
                            display_name=name, source=source["name"], source_id=source_id,
                            identity_status="SOURCE_SCOPED", publication_status=publication_status)
            locator = {"dataset_id": source["dataset"], "download_url": source["download"],
                       "snapshot_sha256": snapshot_hash, "csv_row": row_number,
                       "source_seq_no": seq, "source_scope": source["description"]}
            if source_key == "moi_foundations":
                locator["foundation_type"] = (row.get("類型") or "").strip()
                locator["establishment_date_raw"] = (row.get("成立日期") or "").strip()
            evidence = evidence_from_projection(
                source_name=source["name"], source_record_id=source_id,
                source_class="Government Open Data", source_url=source["url"],
                source_locator=locator, title=f"官方團體清冊紀錄：{name}",
                summary="來源範圍內的團體名冊紀錄；現行狀態及與其他清冊同名實體的身分尚未核對。",
                observed_at=retrieved_at, retrieved_at=retrieved_at,
                publication_status=publication_status)
            bundle["entities"].append(entity.to_dict())
            bundle["evidence"].append(evidence.to_dict())
            bundle["entity_evidence"].append({"entity_id": entity.id,
                                              "evidence_id": evidence.id,
                                              "fact_type": "official_roster_entry"})
            if len(bundle["entities"]) == batch_size:
                yield bundle
                bundle = {"entities": [], "evidence": [], "entity_evidence": []}
    if bundle["entities"]:
        yield bundle
