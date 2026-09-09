"""Bounded procurement lookup backed by a structured mirror of PCC notices."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

API = "https://pcc-api.openfun.app/api/searchbycompanyid"
OFFICIAL_SEARCH = "https://web.pcc.gov.tw/prkms/tender/common/basic/indexTenderBasic"


def _json_get(url: str, timeout: int = 40) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "T.E.I./9.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8-sig", "replace"))
    return data if isinstance(data, dict) else {}


def _normalize(row: dict[str, Any], uniform: str) -> dict[str, Any]:
    brief = row.get("brief") if isinstance(row.get("brief"), dict) else {}
    companies = brief.get("companies") if isinstance(brief.get("companies"), dict) else {}
    names = companies.get("names") if isinstance(companies.get("names"), list) else []
    return {
        "id": f"{row.get('date')}:{row.get('filename')}",
        "date": str(row.get("date") or ""),
        "notice_type": brief.get("type") or "政府採購公告",
        "title": brief.get("title") or row.get("job_number") or "政府採購案件",
        "agency": row.get("unit_name"),
        "job_number": row.get("job_number"),
        "unit_id": row.get("unit_id"),
        "company_names": names,
        "uniform_number": uniform,
        "source_url": row.get("tender_api_url"),
        "official_search_url": OFFICIAL_SEARCH,
    }


def lookup_awards(uniform: str, limit: int = 100) -> dict[str, Any]:
    if not uniform.isdigit() or len(uniform) != 8:
        raise ValueError("統編必須是 8 碼數字。")
    url = API + "?" + urllib.parse.urlencode({"query": uniform, "page": 1})
    try:
        payload = _json_get(url)
        rows = payload.get("records") if isinstance(payload.get("records"), list) else []
        awards = [_normalize(row, uniform) for row in rows if isinstance(row, dict) and "決標" in str((row.get("brief") or {}).get("type") or "")]
        return {
            "status": "ok", "matched": len(awards[:limit]),
            "available_notices": int(payload.get("total_records") or len(rows)),
            "records": awards[:limit],
            "limited": int(payload.get("total_records") or 0) > len(rows) or len(awards) > limit,
            "source": "政府電子採購網公告（OpenFun 民間結構化介接）",
            "source_api": API, "official_search_url": OFFICIAL_SEARCH,
            "match_rule": "company uniform number in procurement notice; award notices only",
        }
    except Exception as exc:
        return {
            "status": "partial", "matched": 0, "available_notices": 0,
            "records": [], "limited": False,
            "source": "政府電子採購網公告（OpenFun 民間結構化介接）",
            "official_search_url": OFFICIAL_SEARCH,
            "message": f"決標資料暫時無法讀取：{type(exc).__name__}",
        }
