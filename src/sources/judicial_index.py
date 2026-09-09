"""Build and query a compact company index from Judicial Yuan JDoc evidence."""
from __future__ import annotations

import json
import re
import urllib.parse
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX = ROOT / "data" / "judicial_company_index.json"
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
    for match in COMPANY_PATTERN.findall(text or ""):
        name = LEADING_ROLE.sub("", match).strip()
        if name not in {"股份有限公司", "有限公司"} and 4 <= len(name) <= 50:
            names.add(name)
    return sorted(names)


def build_index(rows: Iterable[dict[str, Any]], generated_at: str | None = None) -> dict[str, Any]:
    records = []
    for row in rows:
        source = row.get("source") or {}
        fact = row.get("fact") or {}
        if source.get("type") != "judicial" or fact.get("type") != "court_record":
            continue
        summary = str(fact.get("summary") or "")
        names = company_names(" ".join((str(fact.get("title") or ""), summary)))
        if not names:
            continue
        jid = str(source.get("record_id") or "")
        records.append({
            "jid": jid,
            "title": fact.get("title") or "司法院裁判書",
            "date": source.get("published_at"),
            "companies": names,
            "summary": summary[:700],
            "source_url": judgment_url(jid),
        })
    records.sort(key=lambda row: str(row.get("date") or ""), reverse=True)
    return {"generated_at": generated_at, "source": "司法院資料開放平台 JList / JDoc API", "records": records}


@lru_cache(maxsize=1)
def load_index(path: str = str(DEFAULT_INDEX)) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"records": []}
    except (OSError, json.JSONDecodeError):
        return {"generated_at": None, "source": None, "records": []}


def records_for_company(company_name: str, limit: int = 50) -> dict[str, Any]:
    index = load_index()
    exact = []
    for row in index.get("records") or []:
        haystack = " ".join(row.get("companies") or []) + " " + str(row.get("summary") or "")
        if company_name and company_name in haystack:
            exact.append(row)
    return {
        "status": "ok" if index.get("source") else "not_available",
        "matched": len(exact),
        "records": exact[:limit],
        "limited": len(exact) > limit,
        "source": index.get("source"),
        "generated_at": index.get("generated_at"),
        "match_rule": "exact company-name occurrence in official API document text",
        "interpretation": "名稱出現在裁判書不代表該公司為被告或敗訴；請閱讀當事人欄與主文。",
    }
