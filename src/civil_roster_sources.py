"""Other official civil-group rosters; observations are source scoped, not joins."""
import csv
from hashlib import sha256
import json
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
    "moi_civic_foundations": {
        "name": "MOI national civic foundations roster", "dataset": "173726",
        "url": "https://data.gov.tw/dataset/173726",
        "download": "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/B8F8C953-9D8C-4973-BD95-51A4E5C76536/resource/9EE8AAE9-0948-4BA5-BF96-FF4C398EA1F6/download",
        "columns": {"編號", "全國性民政財團法人名稱", "許可設立日期", "許可設立文號",
                    "法人代表", "法人代表性別", "主事務所地址", "聯絡電話"},
        "sequence_column": "編號", "name_column": "全國性民政財團法人名稱",
        "description": "MOI civic foundation permit roster",
    },
    "taipei": {
        "name": "Taipei City people's organizations roster", "dataset": "121714",
        "url": "https://data.gov.tw/dataset/121714",
        "download": "https://data.taipei/api/dataset/72417af0-7dec-4fad-b762-5f2baafcf084/resource/e194f151-adfa-4ab2-b0e0-8f64f470ef40/download",
        "columns": {"機關代碼", "名稱", "地址", "電話", "成立日期"},
        "sequence_column": None, "name_column": "名稱",
        "description": "Taipei local organizations roster",
    },
    "tainan": {
        "name": "Tainan City people's organizations roster", "dataset": "53472",
        "url": "https://data.gov.tw/dataset/53472",
        "download": "https://data.tainan.gov.tw/File/ResourceCsvDownload/37b5bf89-7f27-4b20-bd2a-9eabf90cb8bb",
        "columns": {"連結網址", "團體類別", "團體名稱", "縣市別代碼", "地址-行政區域代碼",
                    "會所住址", "電話", "理事長", "成立年月", "公告解散年月", "立案字號"},
        "sequence_column": None, "name_column": "團體名稱",
        "description": "Tainan local organizations roster",
    },
    "pingtung": {
        "name": "Pingtung County people's organizations roster", "dataset": "142753",
        "url": "https://data.gov.tw/dataset/142753",
        "download": "https://www-ws.pthg.gov.tw/Upload/2015pthg/0/relfile/0/0/4a1a8427-34bc-4ac7-8f1f-69b895f5eb75.csv",
        "columns": {"name", "address", "phone"},
        "sequence_column": None, "name_column": "name",
        "description": "Pingtung local people's organizations roster",
    },
    "mol_foundations": {
        "name": "MOL labor foundations roster", "dataset": "11214",
        "url": "https://data.gov.tw/dataset/11214",
        "download": "https://apiservice.mol.gov.tw/OdService/download/A17000000J-020083-YtL",
        "columns": {"財團法人名稱", "許可設立日期及文號", "督導單位"},
        "sequence_column": None, "name_column": "財團法人名稱",
        "description": "MOL-supervised labor foundations roster",
    },
    "moe_foundations": {
        "name": "MOE education foundations roster", "dataset": "117679",
        "url": "https://data.gov.tw/dataset/117679",
        "download": "https://ws.moe.edu.tw/Download.ashx?u=LzAwMS9VcGxvYWQvNi9yZWxmaWxlLzc4NTYvOTQ5NDYvNjIxYTk4ZjYtYzFlMC00MjQ4LTg1ZTAtODFkZmU2N2Y1NTVhLmNzdg%3D%3D&n=5YWo5ZyL5oCn5pWZ6IKy5rOV5Lq65Z%2B65pys6LOH5paZLmNzdg%3D%3D&icon=..csv",
        "columns": {"基金會名稱", "設立許可文號", "基金會狀態"},
        "sequence_column": None, "name_column": "基金會名稱",
        "encoding": "cp950", "description": "MOE-supervised education foundations roster",
    },
    "newtaipei_community": {
        "name": "New Taipei City community associations roster", "dataset": "124618",
        "url": "https://data.gov.tw/dataset/124618",
        "download": "https://data.ntpc.gov.tw/api/datasets/d424ae39-edea-4aa6-92c3-e8e69938704d/csv/file",
        "columns": {"seqno", "title", "county"},
        "sequence_column": None, "name_column": "title",
        "description": "New Taipei community-association subset, not all local groups",
    },
    "taichung_academic": {
        "name": "Taichung City academic-cultural groups roster", "dataset": "159897",
        "url": "https://data.gov.tw/dataset/159897",
        "download": "https://newdatacenter.taichung.gov.tw/api/v1/no-auth/resource.download?rid=0db97e68-2f55-4d00-b0a9-f7acc127dec6",
        "columns": {"單位名稱", "單位類型", "最後更新日期"},
        "sequence_column": None, "name_column": "單位名稱",
        "description": "Taichung academic-cultural category only, not all local groups",
    },
    "kaohsiung_charity": {
        "name": "Kaohsiung City charity groups roster", "dataset": "128181",
        "url": "https://data.gov.tw/dataset/128181",
        "download": "https://data.kcg.gov.tw/File/DirectDownload/93a27634-3da7-4b05-bc47-614d264cb595",
        "columns": {"id", "org_name", "dataOrg"},
        "sequence_column": None, "name_column": "org_name",
        "description": "Kaohsiung social-service and charity category only, not all local groups",
    },
    "keelung_ods": {
        "name": "Official roster 165174: 基隆市立案人民團體名冊",
        "dataset": "165174", "url": "https://data.gov.tw/dataset/165174",
        "download": "https://www.klcg.gov.tw/wSite/public/Attachment/01304/f1690513718231.ods",
        "columns": {"團體名稱", "ods_sheet", "ods_row", "ods_sha256"},
        "sequence_column": None, "name_column": "團體名稱",
        "description": "Keelung ODS official roster; converted with original ODS hash and sheet/row provenance",
        "locator_fields": ["ods_sheet", "ods_row", "ods_sha256", "成立日期", "團體分類"],
        "expected_rows": 823,
    },
    "yilan_20260930": {
        "name": "Yilan County people's organizations roster 2026-09-30",
        "dataset": "Yilan Social Affairs 2026-09-30",
        "url": "https://sntroot.e-land.gov.tw/cp.aspx?n=10437",
        "download": "https://www-ws.e-land.gov.tw/Download.ashx?n=4peP5a6c6Jit57ij5Lq65rCR5ZyY6auU5ZCN5YaKMTE1MDkzMOeri%2BahiOabtOaWsC5jc3Y%3D&u=LzAwMS9VcGxvYWQvNDQ1L3JlbGZpbGUvMTI3OTIvMTgwMC80NzM5OWM3Mi1jZDRlLTRmYzUtYjlmYy0xYTU4NDE0YjRjZDcuY3N2",
        "columns": {"序號", "人民團體名冊", "團體類別"},
        "sequence_column": "序號", "name_column": "人民團體名冊",
        "description": "Yilan local roster; official page dated 2026-09-30",
        "locator_fields": ["團體類別"], "expected_rows": 1619,
    },
    "yunlin_20260713": {
        "name": "Yunlin County people's organizations roster 2026-07-13",
        "dataset": "Yunlin Social Affairs 2026-07-13",
        "url": "https://social.yunlin.gov.tw/News_Content.aspx?n=746&s=578203",
        "download": "https://ws.yunlin.gov.tw/Download.ashx?u=LzAwMS9VcGxvYWQvNDE0L3JlbGZpbGUvOTM0MC81NzgyMDMvMGZjM2ZhYTctZTY3Yi00OGJlLWIyNzEtMjUwYzMzMDk4OGM0Lnhsc3g%3d&n=6Zuy5p6X57ij5Lq65rCR5ZyY6auU5riF5YaKMTE1LjcuMTMueGxzeA%3d%3d",
        "columns": {"團體名稱", "團體類別", "官方編號", "xlsx_sheet", "xlsx_row", "xlsx_sha256"},
        "sequence_column": None, "name_column": "團體名稱",
        "description": "Yunlin local roster; official XLSX dated 2026-07-13; status not certified",
        "locator_fields": ["團體類別", "官方編號", "xlsx_sheet", "xlsx_row", "xlsx_sha256"],
        "expected_rows": 1881,
    },
    "hsinchu_city_20261025": {
        "name": "Hsinchu City social organizations category pages 2026-10-25",
        "dataset": "Hsinchu City Social Affairs live categories",
        "url": "https://society.hccg.gov.tw/ch/home.jsp?id=161&parentpath=0,3,34",
        "download": "https://society.hccg.gov.tw/ch/home.jsp?id=161&parentpath=0,3,34",
        "columns": {"團體名稱", "團體類別", "官方序號", "來源更新日期", "來源網址",
                    "json_category", "json_row", "json_sha256"},
        "sequence_column": None, "name_column": "團體名稱",
        "description": "Hsinchu City official HTML category pages; each category has its own update date",
        "locator_fields": ["團體類別", "官方序號", "來源更新日期", "來源網址",
                           "json_category", "json_row", "json_sha256"],
        "expected_rows": 1023,
    },
    "miaoli_society_20261025": {
        "name": "Miaoli County social organizations official ODS 2026-10-25",
        "dataset": "Miaoli County Social Affairs live roster",
        "url": "https://sas.miaoli.gov.tw/roster_society",
        "download": "https://sas.miaoli.gov.tw/roster/roster_society?sort_by_date=&group_id=&town_id=&word=",
        "columns": {"團體名稱", "團體類別", "立案日期", "ods_sheet", "ods_row", "ods_sha256"},
        "sequence_column": None, "name_column": "團體名稱",
        "description": "Miaoli official society ODS; site updated 2026-10-22, source status is not independently certified",
        "locator_fields": ["團體類別", "立案日期", "ods_sheet", "ods_row", "ods_sha256"],
        "expected_rows": 2388,
    },
    "changhua_society_20261025": {
        "name": "Changhua County society roster 2026-10-16",
        "dataset": "Changhua Social Affairs 2026-10-16",
        "url": "https://www.chcg.gov.tw/DTO/social/07other/other01_con.aspx?cate_id=5105&data_id=20273&topsn=716",
        "download": "https://www.chcg.gov.tw/DTO/social/getFile.aspx?did=20273&file=6&file_id=560399&type=2",
        "columns": {"團體名稱", "團體類別", "官方編號", "ods_sheet", "ods_row", "ods_sha256"},
        "sequence_column": None, "name_column": "團體名稱",
        "description": "Changhua official society ODS dated 2026-10-16; includes historical status annotations",
        "locator_fields": ["團體類別", "官方編號", "ods_sheet", "ods_row", "ods_sha256"],
        "expected_rows": 2375,
    },
    "kinmen_society_20261025": {
        "name": "Kinmen County social organizations official XLSX 2026-10-25",
        "dataset": "Kinmen Social Affairs roster",
        "url": "https://social.kinmen.gov.tw/Content_List.aspx?n=5953401623861323",
        "download": "https://ws.kinmen.gov.tw/Download.ashx?u=LzAwMS9VcGxvYWQvMzAzL3JlbGZpbGUvMC8yNjE3Ny80OWUxMmY2ZS1lNDMyLTQ3YzktYjM0ZS0zYTlhM2UxMWIxN2UueGxzeA%3d%3d&n=6YeR6ZaA57ij56S%2b5pyD5ZyY6auULnhsc3g%3d",
        "columns": {"團體名稱", "官方編號", "成立日期", "最後更新時間", "xlsx_sheet", "xlsx_row", "xlsx_sha256"},
        "sequence_column": None, "name_column": "團體名稱",
        "description": "Kinmen official social-group XLSX; source-specific identities, no current-status inference",
        "locator_fields": ["官方編號", "成立日期", "最後更新時間", "xlsx_sheet", "xlsx_row", "xlsx_sha256"],
        "expected_rows": 498,
    },
    "hsinchu_county_20261005": {
        "name": "Hsinchu County people's organizations official XLSX 2026-10-05",
        "dataset": "Hsinchu County Social Affairs 2026-10-05",
        "url": "https://social.hsinchu.gov.tw/News.aspx?n=218&sms=8679",
        "download": "https://ws.hsinchu.gov.tw/Download.ashx?u=LzAwMS9VcGxvYWQvOC9yZWxmaWxlLzg2NzkvMTk3ODY5LzIxNTEzYjRlLTJkNTYtNDU4ZS1hMWFiLWYwNGExYWVjZDFlMC54bHN4&n=5Lq65rCR5ZyY6auU5ZCN5YaKMTE1LjEwLjUueGxzeA%3d%3d",
        "columns": {"團體名稱", "團體類別", "官方編號", "成立日期", "xlsx_sheet", "xlsx_row", "xlsx_sha256"},
        "sequence_column": None, "name_column": "團體名稱",
        "description": "Hsinchu County official 2026-10-05 multi-category XLSX; source observations, not live status",
        "locator_fields": ["團體類別", "官方編號", "成立日期", "xlsx_sheet", "xlsx_row", "xlsx_sha256"],
        "expected_rows": 2181,
        "category_counts": {
            "工商職業團體": 70, "醫療職業團體": 14, "教育職業團體": 51,
            "自由職業團體": 8, "社會團體─學術文化團體": 509,
            "社會團體─宗教團體": 54, "社會團體─體育運動團體": 266,
            "社會團體─社會服務及慈善團體": 698,
            "社會團體─經濟業務團體": 120, "社會團體─國際團體": 71,
            "社會團體─同鄉會": 3, "社會團體─同學校友會": 39,
            "社會團體─宗親會": 277, "其他": 1,
        },
    },
    "tainan_social_foundations_json": {
        "name": "Official roster 102929: 臺南市財團法人名冊(社福基金會類)",
        "dataset": "102929", "url": "https://data.gov.tw/dataset/102929",
        "download": "https://soa.tainan.gov.tw/Api/Service/Get/656dcf3d-93da-4915-82b5-a791c7b87e33",
        "columns": {"基金會名稱", "設立許可日期", "設立許可文號", "狀態/備註", "json_row", "json_sha256"},
        "sequence_column": None, "name_column": "基金會名稱",
        "description": "Tainan social-welfare foundation JSON; original hash and item location retained",
        "locator_fields": ["設立許可日期", "設立許可文號", "狀態/備註", "json_row", "json_sha256"],
        "expected_rows": 93,
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

# Curated official catalog snapshots remain independent source observations.
# The manifest is intentionally explicit: a catalog search hit alone cannot
# silently become a published organization or a cross-source identity match.
_manifest = json.loads((Path(__file__).with_name("civil_roster_manifest.json")).read_text(encoding="utf-8"))
if set(_manifest) & set(SOURCES):
    raise ValueError("Duplicate official roster key")
SOURCES.update(_manifest)
_penghu_manifest = json.loads((Path(__file__).with_name("civil_roster_penghu_manifest.json")).read_text(encoding="utf-8"))
if set(_penghu_manifest) & set(SOURCES):
    raise ValueError("Duplicate official Penghu roster key")
SOURCES.update(_penghu_manifest)


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
    with path.open(encoding=source.get("encoding", "utf-8-sig"), newline="") as handle:
        reader = csv.DictReader(handle)
        reader.fieldnames = [field.lstrip("\ufeff").strip() for field in reader.fieldnames or []]
        if not set(source["columns"]).issubset(reader.fieldnames or []):
            raise ValueError("Unexpected official roster columns")
        for row_number, row in enumerate(reader, 2):
            # Some official CSVs end with empty comma-delimited records. Do not
            # publish them as organizations; keep the original CSV row locator.
            if not any((value or "").strip() for value in row.values()):
                continue
            sequence_column = source.get("sequence_column", "序號")
            seq = (row.get(sequence_column) or "").strip() if sequence_column else str(row_number - 1)
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
            elif source_key == "moi_civic_foundations":
                locator["permit_number_raw"] = (row.get("許可設立文號") or "").strip()
                locator["permit_date_raw"] = (row.get("許可設立日期") or "").strip()
            elif source_key == "taipei":
                locator["establishment_date_raw"] = (row.get("成立日期") or "").strip()
            elif source_key == "tainan":
                locator["filing_number_raw"] = (row.get("立案字號") or "").strip()
                locator["dissolution_date_raw"] = (row.get("公告解散年月") or "").strip()
                locator["establishment_date_raw"] = (row.get("成立年月") or "").strip()
            elif source_key == "mol_foundations":
                locator["permit_date_and_number_raw"] = (row.get("許可設立日期及文號") or "").strip()
                locator["supervising_unit_raw"] = (row.get("督導單位") or "").strip()
            elif source_key == "moe_foundations":
                locator["permit_number_raw"] = (row.get("設立許可文號") or "").strip()
                locator["foundation_status_raw"] = (row.get("基金會狀態") or "").strip()
            elif source_key == "taichung_academic":
                locator["source_last_updated_raw"] = (row.get("最後更新日期") or "").strip()
            for field in source.get("locator_fields", []):
                value = (row.get(field) or "").strip()
                if value:
                    locator[field] = value
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
