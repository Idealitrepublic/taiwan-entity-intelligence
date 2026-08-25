"""Public-record connectors used by the GitHub data-sync workflow.

The connectors intentionally preserve source provenance and raw rows. They do
not infer guilt or wrongdoing. Entity matching is a later, separate step.
"""

import csv
import hashlib
import io
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from ..evidence import make_evidence

USER_AGENT = "Taiwan-Entity-Intelligence/0.1 (+https://github.com/Idealitrepublic/taiwan-entity-intelligence)"


def fetch(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_text(url: str) -> str:
    return fetch(url).decode("utf-8-sig", errors="replace")


def parse_csv_bytes(payload: bytes) -> List[Dict[str, Any]]:
    text = payload.decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


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


def ingest_165_blocked_sites() -> List[Dict[str, Any]]:
    """警政署 165 遭停止解析涉詐網站。"""
    url = "https://opdadm.moi.gov.tw/api/v1/dataset/176455/resource"
    try:
        meta = parse_json_bytes(fetch(url))
        resources = meta.get("result", {}).get("resources", []) if isinstance(meta, dict) else []
        csv_url = next((r.get("download_url") or r.get("resourceDownloadUrl") for r in resources if str(r.get("format", "")).upper() == "CSV"), None)
    except Exception:
        csv_url = None
    if not csv_url:
        # Fallback: keep this URL configurable because data.gov.tw may rotate resource URLs.
        csv_url = os.environ.get("TEI_165_CSV_URL", "")
    if not csv_url:
        raise RuntimeError("找不到 165 CSV 資源 URL；請設定 TEI_165_CSV_URL。")

    rows = parse_csv_bytes(fetch(csv_url))
    output = []
    for row in rows:
        domain = normalize_domain(row.get("網域"))
        record_id = row_hash("police_165_blocked_site", row)
        output.append(make_evidence(
            source_type="fraud_signal",
            source_name="police_165_blocked_sites",
            source_record_id=record_id,
            entity_id="domain:{}".format(domain) if domain else "record:{}".format(record_id),
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


def ingest_165_rumors() -> List[Dict[str, Any]]:
    """165 詐騙闢謠專區。"""
    url = os.environ.get("TEI_165_RUMOR_CSV_URL", "")
    if not url:
        return []
    rows = parse_csv_bytes(fetch(url))
    output = []
    for row in rows:
        rid = row_hash("police_165_rumor", row)
        output.append(make_evidence(
            source_type="fraud_signal",
            source_name="police_165_rumors",
            source_record_id=rid,
            entity_id="fraud-record:{}".format(rid),
            entity_type="fraud_record",
            fact_type="fraud_signal",
            title=row.get("標題") or "165 詐騙闢謠",
            summary=row.get("發佈內容"),
            source_url="https://data.gov.tw/dataset/38262",
            source_published_at=row.get("發佈時間"),
            confidence=1.0,
            raw_payload=row,
        ))
    return output


def ingest_165_fake_investment() -> List[Dict[str, Any]]:
    """165 假投資／博弈網站。URL is configurable because the resource can rotate."""
    url = os.environ.get("TEI_165_FAKE_INVESTMENT_CSV_URL", "")
    if not url:
        return []
    rows = parse_csv_bytes(fetch(url))
    output = []
    for row in rows:
        domain = normalize_domain(row.get("網域") or row.get("網址"))
        rid = row_hash("police_165_fake_investment", row)
        output.append(make_evidence(
            source_type="fraud_signal",
            source_name="police_165_fake_investment",
            source_record_id=rid,
            entity_id="domain:{}".format(domain) if domain else "record:{}".format(rid),
            entity_type="domain" if domain else "record",
            fact_type="fraud_signal",
            relation_type="listed_by_authority",
            title="165 假投資／博弈網站",
            source_url="https://data.gov.tw/dataset/160055",
            confidence=1.0,
            raw_payload=row,
        ))
    return output


def ingest_environmental_penalties() -> List[Dict[str, Any]]:
    """環境部裁罰處分；優先使用官方 JSON URL 環境變數。"""
    url = os.environ.get("TEI_MOENV_PENALTY_JSON_URL", "")
    if not url:
        return []
    payload = parse_json_bytes(fetch(url))
    rows = payload if isinstance(payload, list) else payload.get("data", payload.get("records", []))
    output = []
    for row in rows:
        name = normalize_name(row.get("name"))
        rid = str(row.get("no") or row_hash("moenv_penalty", row))
        output.append(make_evidence(
            source_type="administrative_penalty",
            source_name="moenv_penalties",
            source_record_id=rid,
            entity_id="name:{}".format(name) if name else "record:{}".format(rid),
            entity_type="organization_or_person",
            fact_type="administrative_penalty",
            relation_type="penalized_by",
            title=row.get("case") or "環境部裁罰處分",
            summary=row.get("fact"),
            source_url="https://data.gov.tw/dataset/10165",
            source_published_at=row.get("date"),
            confidence=1.0,
            raw_payload=row,
        ))
    return output


def evidence_rows() -> Iterable[Dict[str, Any]]:
    """Yield all configured public-record evidence rows."""
    for loader in (ingest_165_blocked_sites, ingest_165_rumors, ingest_165_fake_investment, ingest_environmental_penalties):
        try:
            yield from loader()
        except Exception as exc:
            print("[WARN] {}: {}".format(loader.__name__, exc))
