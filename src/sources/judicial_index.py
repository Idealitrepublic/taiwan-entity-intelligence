"""Build and query a compact company index from Judicial Yuan JDoc evidence."""
from __future__ import annotations

import json
import re
import urllib.parse
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX = ROOT / "data" / "judicial_company_index.json"
VERIFIED_CASES = ROOT / "data" / "judicial_verified_cases.json"
COMPANY_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9・．·（）()]{2,50}(?:股份有限公司|有限公司)")
LEADING_ROLE = re.compile(
    r"^(?:原告|被告|上訴人|被上訴人|聲請人|相對人|債權人|債務人|參加人|"
    r"關係人|再審原告|再審被告|因積欠|向最大債權銀行|上列原告與被告|"
    r"另應提出被告|起訴請求被告)"
)


def judgment_url(jid: str) -> str:
    return "https://judgment.judicial.gov.tw/FJUD/printData.aspx?id=" + urllib.parse.quote(jid, safe="")


def company_names(text: str) -> list[str]:
    names = set()
    for match in COMPANY_PATTERN.findall(_normalized(text)):
        name = LEADING_ROLE.sub("", match).strip()
        if name not in {"股份有限公司", "有限公司"} and 4 <= len(name) <= 50:
            names.add(name)
    return sorted(names)


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or ""))).casefold()


def build_index(rows: Iterable[dict[str, Any]], generated_at: str | None = None) -> dict[str, Any]:
    records_by_jid = {}
    latest = {}
    for row in rows:
        source = row.get("source") or {}
        fact = row.get("fact") or {}
        if source.get("type") != "judicial" or fact.get("type") not in {"court_record", "court_record_status"}:
            continue
        jid = str(source.get("record_id") or "")
        if not jid:
            continue
        if jid not in latest or str(row.get("retrieved_at") or "") > str(latest[jid].get("retrieved_at") or ""):
            latest[jid] = row
    removed_jids = []
    unindexable_docs = 0
    for jid, row in latest.items():
        fact = row.get("fact") or {}
        if fact.get("type") != "court_record" or row.get("status") == "removed":
            removed_jids.append(jid)
            continue
        summary = str(fact.get("summary") or "")
        if not summary:
            unindexable_docs += 1
        names = company_names(" ".join((str(fact.get("title") or ""), summary)))
        if not names:
            continue
        records_by_jid[jid] = {
            "jid": jid,
            "title": fact.get("title") or "司法院裁判書",
            "date": source.get("published_at"),
            "companies": names,
            "summary": summary[:700],
            "source_url": judgment_url(jid),
            "retrieved_at": row.get("retrieved_at"),
            "evidence_id": row.get("evidence_id"),
            "source_record_id": jid,
            "provenance": "official_jdoc_api",
        }
    records = list(records_by_jid.values())
    records.sort(key=lambda row: str(row.get("date") or ""), reverse=True)
    return {"generated_at": generated_at, "source": "司法院資料開放平台 JList / JDoc API",
            "records": records, "removed_jids": sorted(removed_jids),
            "jdoc_record_count": len(latest), "unindexable_without_text": unindexable_docs}


@lru_cache(maxsize=1)
def load_index(path: str = str(DEFAULT_INDEX), verified_path: str = str(VERIFIED_CASES)) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Invalid judicial index")
    except (OSError, ValueError):
        data = {"generated_at": None, "source": None, "records": []}
    try:
        verified = json.loads(Path(verified_path).read_text(encoding="utf-8"))
        rows = verified.get("records", [])
    except (OSError, ValueError, AttributeError):
        rows = []
    merged = {str(row.get("jid")): row for row in data.get("records", [])
              if isinstance(row, dict) and row.get("jid")}
    removed = set(data.get("removed_jids") or [])
    for row in rows:
        if isinstance(row, dict) and row.get("jid") and row["jid"] not in removed:
            jid = str(row["jid"])
            if jid in merged:
                for field in ("source_record_id", "retrieved_at", "provenance"):
                    if not merged[jid].get(field):
                        merged[jid][field] = row.get(field)
            else:
                merged[jid] = row
    return {**data, "records": list(merged.values()),
            "source": data.get("source") or ("Official court verified cases" if rows else None),
            "verified_case_count": len(rows)}


def records_for_company(company_name: str, limit: int = 50) -> dict[str, Any]:
    index = load_index()
    exact = []
    needle = _normalized(company_name)
    for row in index.get("records") or []:
        candidates = row.get("companies") or []
        if needle and len(needle) >= 4 and any(needle in _normalized(name) for name in candidates):
            exact.append(row)
    exact.sort(key=lambda row: str(row.get("date") or ""), reverse=True)
    return {
        "status": ("partial" if index.get("source") else "not_available") if not exact else "ok",
        "matched": len(exact),
        "records": exact[:limit],
        "limited": len(exact) > limit,
        "source": index.get("source"),
        "generated_at": index.get("generated_at"),
        "match_rule": "NFKC exact full company-name occurrence in indexed official judgment",
        "coverage_note": "此為部分 JList/JDoc 索引與官方核對案例，並非完整裁判書查詢；零筆不代表沒有裁判紀錄。",
        "interpretation": "名稱出現在裁判書不代表該公司為被告或敗訴；請閱讀當事人欄與主文。",
    }
