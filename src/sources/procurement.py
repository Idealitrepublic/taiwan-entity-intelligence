"""Bounded procurement lookup backed by a structured mirror of PCC notices."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
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
        "awardee_names": matched_names(row, uniform),
        "uniform_number": uniform,
        "source_url": (API.rsplit('/', 1)[0] + '/tender?' + urllib.parse.urlencode(
            {'unit_id': row.get('unit_id'), 'job_number': row.get('job_number')}))
        if row.get('unit_id') and row.get('job_number') else None,
        "award_role": award_role(row, uniform),
        "official_search_url": OFFICIAL_SEARCH,
    }


def matched_names(row: dict[str, Any], uniform: str) -> list[str]:
    """Use the bidder identifier's field path, never positional/name inference."""
    companies = (row.get('brief') or {}).get('companies') or {}
    prefixes = [key.rsplit(':', 1)[0] + ':'
                for key in (companies.get('id_key') or {}).get(uniform, [])]
    return [name for name, keys in (companies.get('name_key') or {}).items()
            if any(key.startswith(prefix) for key in keys for prefix in prefixes)]


def award_role(row: dict[str, Any], uniform: str) -> str:
    companies = (row.get('brief') or {}).get('companies') or {}
    roles = [key for name in matched_names(row, uniform)
             for key in (companies.get('name_key') or {}).get(name, [])]
    if any(re.search(r':得標廠商\d+:', key) for key in roles):
        return 'winner'
    if any(':未得標廠商' in key for key in roles):
        return 'nonwinner'
    return 'unresolved'


def lookup_awards(uniform: str, limit: int = 100, timeout: int = 40) -> dict[str, Any]:
    if not uniform.isdigit() or len(uniform) != 8:
        raise ValueError("統編必須是 8 碼數字。")
    url = API + "?" + urllib.parse.urlencode({"query": uniform, "page": 1})
    try:
        payload = _json_get(url, timeout=timeout)
        rows = payload.get("records") if isinstance(payload.get("records"), list) else []
        notices = [row for row in rows if isinstance(row, dict)
                   and '決標' in str((row.get('brief') or {}).get('type') or '')]
        # Select the latest notice before classifying: a correction can withdraw
        # a formerly successful award. Keep unknown keys separate, not merged.
        latest = {}
        ambiguous = set()
        for row in sorted(notices, key=lambda item: str(item.get('date'))):
            key = (row.get('unit_id'), row.get('job_number'))
            if not all(key):
                key = ('notice', row.get('filename'), row.get('date'))
            previous = latest.get(key)
            if previous and previous.get('date') == row.get('date'):
                if award_role(previous, uniform) != award_role(row, uniform):
                    ambiguous.add(key)
            else:
                ambiguous.discard(key)
            latest[key] = row
        classified = [row for key, row in latest.items() if key not in ambiguous]
        awards = [_normalize(row, uniform) for row in classified
                  if award_role(row, uniform) == 'winner']
        awards.sort(key=lambda row: row['date'], reverse=True)
        return {
            "status": "ok", "matched": len(awards[:limit]),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "available_notices": int(payload.get("total_records") or len(rows)),
            "records": awards[:limit],
            "returned_notices": len(rows),
            "award_notices": len(notices),
            "nonwinner_count": sum(award_role(row, uniform) == 'nonwinner' for row in classified),
            "unresolved_count": len(ambiguous) + sum(award_role(row, uniform) == 'unresolved' for row in classified),
            "limited": int(payload.get("total_records") or 0) > len(rows) or len(awards) > limit,
            "source": "政府電子採購網公告（OpenFun 民間結構化介接）",
            "source_api": API, "official_search_url": OFFICIAL_SEARCH,
            "match_rule": "exact bidder identifier field path and explicit winner role; latest notice per job; first page only",
        }
    except Exception as exc:
        return {
            "status": "partial", "matched": 0, "available_notices": 0,
            "records": [], "limited": False,
            "source": "政府電子採購網公告（OpenFun 民間結構化介接）",
            "official_search_url": OFFICIAL_SEARCH,
            "message": f"決標資料暫時無法讀取：{type(exc).__name__}",
        }


def lookup_co_awardees(uniform: str, limit: int = 6, timeout: int = 8) -> dict[str, Any]:
    """Find other exact-ID winners in the same notice, never name-only bidders.

    This is a bounded observation, not a corporate-affiliation assertion. The
    source API returns one page, so an empty result is not a coverage claim.
    """
    if not re.fullmatch(r"[0-9]{8}", uniform) or not 1 <= limit <= 10:
        raise ValueError("Invalid company ID or co-awardee limit")
    try:
        url = API + "?" + urllib.parse.urlencode({"query": uniform, "page": 1})
        payload = _json_get(url, timeout=timeout)
        rows = payload.get("records") if isinstance(payload.get("records"), list) else []
        latest = {}
        ambiguous = set()
        for row in sorted(rows, key=lambda item: str(item.get("date") or "")
                          if isinstance(item, dict) else ""):
            if not isinstance(row, dict) or "決標" not in str((row.get("brief") or {}).get("type") or ""):
                continue
            key = (row.get("unit_id"), row.get("job_number"))
            if not all(key):
                key = ("notice", row.get("filename"), row.get("date"))
            previous = latest.get(key)
            if previous and row.get("date") == previous.get("date"):
                if (row.get("brief") or {}).get("companies") != (previous.get("brief") or {}).get("companies"):
                    ambiguous.add(key)
            else:
                ambiguous.discard(key)
            latest[key] = row
        found = {}
        for row in sorted((row for key, row in latest.items() if key not in ambiguous),
                          key=lambda item: str(item.get("date") or ""), reverse=True):
            if award_role(row, uniform) != "winner":
                continue
            notice = _normalize(row, uniform)
            if not notice.get("source_url"):
                continue
            companies = (row.get("brief") or {}).get("companies") or {}
            for other_id in (companies.get("id_key") or {}):
                if (not isinstance(other_id, str) or not re.fullmatch(r"[0-9]{8}", other_id)
                        or other_id == uniform or award_role(row, other_id) != "winner"):
                    continue
                names = matched_names(row, other_id)
                if len(set(names)) != 1:
                    continue
                found.setdefault(other_id, {
                    "uniform_number": other_id, "company_name": names[0],
                    "notice": notice,
                })
        items = list(found.values())
        return {"status": "ok", "items": items[:limit],
                "limited": int(payload.get("total_records") or 0) > len(rows)
                or len(items) > limit}
    except Exception:
        return {"status": "partial", "items": [], "limited": True}
