"""Public-record connectors for GitHub Actions.

The connectors use official open-data endpoints, preserve provenance, and
separate observed evidence from later entity-resolution/inference.
"""

import csv
import hashlib
import io
import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional

from ..evidence import make_evidence

USER_AGENT = "Taiwan-Entity-Intelligence/0.1 (+https://github.com/Idealitrepublic/taiwan-entity-intelligence)"
DATAGOV_META = "https://data.gov.tw/api/v2/rest/dataset/{}"
DATAGOV_CATALOG = "https://data.gov.tw/datasets/export/csv"


def fetch(url: str, timeout: int = 90) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def parse_csv_bytes(payload: bytes) -> List[Dict[str, Any]]:
    return list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig", errors="replace"))))


def parse_json_bytes(payload: bytes) -> Any:
    return json.loads(payload.decode("utf-8-sig", errors="replace"))


def normalize_name(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def normalize_domain(value: Any) -> str:
    value = normalize_name(value).lower()
    value = re.sub(r"^https?://", "", value)
    return value.split("/", 1)[0]


def row_hash(source: str, row: Dict[str, Any]) -> str:
    canonical = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256((source + "|" + canonical).encode("utf-8")).hexdigest()


def dataset_meta(dataset_id: str) -> Dict[str, Any]:
    return parse_json_bytes(fetch(DATAGOV_META.format(dataset_id)))


def resource_urls(dataset_id: str, preferred_formats=("CSV", "JSON", "XML")) -> List[str]:
    """Resolve rotating official resource URLs through data.gov.tw metadata."""
    meta = dataset_meta(dataset_id)
    distributions = meta.get("distribution") or meta.get("distributions") or []
    if isinstance(distributions, dict):
        distributions = list(distributions.values())
    found: List[str] = []
    for item in distributions:
        if not isinstance(item, dict):
            continue
        url = item.get("resourceDownloadURL") or item.get("downloadURL") or item.get("url")
        fmt = str(item.get("format") or item.get("mediaType") or "").upper()
        if url and (not fmt or any(x in fmt for x in preferred_formats)):
            found.append(url)
    return list(dict.fromkeys(found))


def first_resource(dataset_id: str, preferred_formats=("CSV", "JSON", "XML")) -> str:
    urls = resource_urls(dataset_id, preferred_formats)
    if not urls:
        raise RuntimeError("data.gov.tw dataset {} 沒有可用的公開資源 URL".format(dataset_id))
    return urls[0]


def ingest_165_blocked_sites() -> List[Dict[str, Any]]:
    url = first_resource("176455", ("CSV",))
    rows = parse_csv_bytes(fetch(url))
    output = []
    for row in rows:
        domain = normalize_domain(row.get("網域"))
        rid = row_hash("police_165_blocked_site", row)
        output.append(make_evidence(
            source_type="fraud_signal",
            source_name="police_165_blocked_sites",
            source_record_id=rid,
            entity_id="domain:{}".format(domain) if domain else "record:{}".format(rid),
            entity_type="domain" if domain else "record",
            fact_type="fraud_signal",
            relation_type="blocked_by_authority",
            title="165 涉詐網站停止解析",
            summary="官方資料列示之遭停止解析涉詐網站；此為來源訊號，不等同於對公司或個人的犯罪認定。",
            source_url="https://data.gov.tw/dataset/176455",
            source_published_at=row.get("民國年月"),
            confidence=1.0,
            raw_payload=row,
        ))
    return output


def ingest_165_dataset(dataset_id: str, source_name: str, title: str, domain_fields=("網域", "網址")) -> List[Dict[str, Any]]:
    url = first_resource(dataset_id, ("CSV", "JSON"))
    payload = fetch(url)
    if url.lower().split("?", 1)[0].endswith(".json"):
        raw = parse_json_bytes(payload)
        rows = raw if isinstance(raw, list) else raw.get("data", raw.get("records", raw.get("items", [])))
    else:
        rows = parse_csv_bytes(payload)
    output = []
    for row in rows:
        domain = next((normalize_domain(row.get(f)) for f in domain_fields if row.get(f)), "")
        rid = row_hash(source_name, row)
        output.append(make_evidence(
            source_type="fraud_signal",
            source_name=source_name,
            source_record_id=rid,
            entity_id="domain:{}".format(domain) if domain else "record:{}".format(rid),
            entity_type="domain" if domain else "record",
            fact_type="fraud_signal",
            relation_type="listed_by_authority",
            title=title,
            source_url="https://data.gov.tw/dataset/{}".format(dataset_id),
            confidence=1.0,
            raw_payload=row,
        ))
    return output


def ingest_165_rumors() -> List[Dict[str, Any]]:
    return ingest_165_dataset("38262", "police_165_rumors", "165 詐騙闢謠")


def ingest_165_fake_investment() -> List[Dict[str, Any]]:
    return ingest_165_dataset("160055", "police_165_fake_investment", "165 假投資／博弈網站")


def discover_penalty_datasets() -> List[Dict[str, str]]:
    """Discover public datasets whose titles/metadata indicate actual penalties.

    This is intentionally a discovery layer rather than a claim that every
    government penalty dataset has been semantically resolved. Statistical
    aggregates are excluded because they do not identify an entity.
    """
    payload = fetch(DATAGOV_CATALOG)
    rows = parse_csv_bytes(payload)
    keywords = ("裁罰", "裁處", "罰鍰", "行政處分", "處分名單")
    exclude = ("統計", "件數", "金額", "概況", "數量")
    found = []
    for row in rows:
        title = str(row.get("title") or row.get("資料集名稱") or "").strip()
        if not title or not any(k in title for k in keywords):
            continue
        if any(k in title for k in exclude) and "名單" not in title:
            continue
        dataset_id = str(row.get("datasetid") or row.get("datasetId") or row.get("資料集識別碼") or "").strip()
        if dataset_id:
            found.append({"dataset_id": dataset_id, "title": title})
    # Stable de-duplication.
    unique = {}
    for item in found:
        unique[item["dataset_id"]] = item
    return list(unique.values())


def ingest_penalty_dataset(dataset_id: str, title: str) -> List[Dict[str, Any]]:
    urls = resource_urls(dataset_id, ("CSV", "JSON", "XML"))
    if not urls:
        return []
    url = urls[0]
    payload = fetch(url)
    if "JSON" in url.upper() or url.lower().split("?", 1)[0].endswith(".json"):
        raw = parse_json_bytes(payload)
        rows = raw if isinstance(raw, list) else raw.get("data", raw.get("records", raw.get("items", [])))
    elif "XML" in url.upper() or url.lower().split("?", 1)[0].endswith(".xml"):
        # XML parsing is deliberately deferred when a CSV/JSON alternative exists.
        return []
    else:
        rows = parse_csv_bytes(payload)

    output = []
    for row in rows:
        name = normalize_name(row.get("受處分人") or row.get("行為人名稱") or row.get("name") or row.get("名稱") or row.get("業者名稱") or row.get("公司名稱"))
        if not name:
            # Aggregate/statistical rows are not useful as entity evidence.
            continue
        rid = str(row.get("編號") or row.get("no") or row.get("序號") or row_hash("penalty:{}".format(dataset_id), row))
        date = row.get("裁罰日期") or row.get("date") or row.get("違反處分時間") or row.get("處分日期")
        output.append(make_evidence(
            source_type="administrative_penalty",
            source_name="data_gov_penalty_{}".format(dataset_id),
            source_record_id=rid,
            entity_id="name:{}".format(name),
            entity_type="organization_or_person",
            fact_type="administrative_penalty",
            relation_type="penalized_by",
            title=title,
            summary=row.get("違反事實") or row.get("fact") or row.get("案件名稱") or row.get("case"),
            source_url="https://data.gov.tw/dataset/{}".format(dataset_id),
            source_published_at=date,
            confidence=1.0,
            raw_payload=row,
        ))
    return output


def evidence_rows() -> Iterable[Dict[str, Any]]:
    for loader in (ingest_165_blocked_sites, ingest_165_rumors, ingest_165_fake_investment):
        try:
            yield from loader()
        except Exception as exc:
            print("[WARN] {}: {}".format(loader.__name__, exc))

    try:
        penalty_datasets = discover_penalty_datasets()
        print("[INFO] discovered penalty datasets: {}".format(len(penalty_datasets)))
        for dataset in penalty_datasets:
            try:
                yield from ingest_penalty_dataset(dataset["dataset_id"], dataset["title"])
            except Exception as exc:
                print("[WARN] penalty {} {}: {}".format(dataset["dataset_id"], dataset["title"], exc))
    except Exception as exc:
        print("[WARN] penalty discovery: {}".format(exc))
