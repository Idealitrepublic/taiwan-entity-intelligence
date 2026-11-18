"""Bounded procurement lookup backed by a structured mirror of PCC notices."""
from __future__ import annotations

import json
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

API = "https://pcc-api.openfun.app/api/searchbycompanyid"
OFFICIAL_SEARCH = "https://web.pcc.gov.tw/prkms/tender/common/basic/indexTenderBasic"


def _json_get(url: str, timeout: int = 40) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "T.E.I./9.1"})
    deadline = time.monotonic() + timeout
    for attempt in range(2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Procurement request budget exhausted")
        try:
            with urllib.request.urlopen(request, timeout=min(8, remaining / (2 - attempt))) as response:
                data = json.loads(response.read().decode("utf-8-sig", "replace"))
            if not isinstance(data, dict) or not isinstance(data.get("records"), list):
                raise ValueError("Procurement response lacks a records array")
            return data
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            reason = getattr(exc, "reason", exc)
            # No blind HTTP/rate-limit retries or certificate-validation bypass.
            if (attempt or isinstance(exc, urllib.error.HTTPError)
                    or isinstance(reason, ssl.SSLError)):
                raise
            time.sleep(min(.25, max(0, deadline - time.monotonic())))
    raise TimeoutError("Procurement request budget exhausted")


def _source_error(exc):
    """Expose only error classes/codes, never exception text, headers or tokens."""
    reason = getattr(exc, "reason", exc)
    category = ("http" if isinstance(exc, urllib.error.HTTPError) else
                "format" if isinstance(exc, ValueError) else
                "tls" if isinstance(reason, ssl.SSLError) else
                "dns" if isinstance(reason, socket.gaierror) else
                "timeout" if isinstance(reason, TimeoutError) else "transport")
    return {"category": category, "error_type": type(exc).__name__,
            "reason_type": type(reason).__name__,
            "http_status": exc.code if isinstance(exc, urllib.error.HTTPError) else None,
            "errno": reason.errno if isinstance(getattr(reason, "errno", None), int) else None}


def _normalize(row: dict[str, Any], uniform: str) -> dict[str, Any]:
    brief = row.get("brief") if isinstance(row.get("brief"), dict) else {}
    companies = brief.get("companies") if isinstance(brief.get("companies"), dict) else {}
    names = companies.get("names") if isinstance(companies.get("names"), list) else []
    role = award_role(row, uniform)
    return {
        "id": f"{row.get('date')}:{row.get('filename')}",
        "date": str(row.get("date") or ""),
        "notice_type": brief.get("type") or "政府採購公告",
        "title": brief.get("title") or row.get("job_number") or "政府採購案件",
        "agency": row.get("unit_name"),
        "job_number": row.get("job_number"),
        "unit_id": row.get("unit_id"),
        "notice_filename": row.get("filename"),
        "budget_amount": row.get("budget_amount"),
        "total_award_amount": row.get("award_amount"),
        "company_names": names,
        "awardee_names": matched_names(row, uniform) if role == "winner" else [],
        "uniform_number": uniform,
        "source_url": (API.rsplit('/', 1)[0] + '/tender?' + urllib.parse.urlencode(
            {'unit_id': row.get('unit_id'), 'job_number': row.get('job_number')}))
        if row.get('unit_id') and row.get('job_number') else None,
        "award_role": role,
        "identity_status": "mirror_exact_bidder_id_unconfirmed_official" if role == "winner" else "unresolved",
        "publication_status": "source_candidate",
        "verification_scope": "mirror_exact_bidder_id_and_winner_role;official_notice_not_independently_checked",
        "official_search_url": OFFICIAL_SEARCH,
    }


def _notice_shape_valid(row):
    """Fail closed on role paths; preserve other notices in the source batch."""
    if not isinstance(row, dict) or not isinstance(row.get('brief') or {}, dict):
        return False
    companies = (row.get('brief') or {}).get('companies') or {}
    if not isinstance(companies, dict) or not isinstance(row.get('detail') or {}, dict):
        return False
    for name in ('id_key', 'name_key'):
        mapping = companies.get(name) or {}
        if not isinstance(mapping, dict) or any(
                not isinstance(key, str) or not isinstance(paths, list)
                or any(not isinstance(path, str) for path in paths)
                for key, paths in mapping.items()):
            return False
    return all(row.get(key) is None or isinstance(row[key], (str, int))
               for key in ('date', 'filename', 'unit_id', 'job_number'))


def matched_names(row: dict[str, Any], uniform: str) -> list[str]:
    """Use the bidder identifier's field path, never positional/name inference."""
    if not _notice_shape_valid(row):
        return []
    companies = (row.get('brief') or {}).get('companies') or {}
    prefixes = [key.rsplit(':', 1)[0] + ':'
                for key in (companies.get('id_key') or {}).get(uniform, [])]
    return [name for name, keys in (companies.get('name_key') or {}).items()
            if any(key.startswith(prefix) for key in keys for prefix in prefixes)]


def award_role(row: dict[str, Any], uniform: str) -> str:
    if not _notice_shape_valid(row):
        return 'unresolved'
    companies = (row.get('brief') or {}).get('companies') or {}
    names = list(dict.fromkeys(matched_names(row, uniform)))
    # The mirror groups role paths by name. If one name denotes multiple
    # bidders or contradictory roles, it cannot identify this bidder's award.
    if len(names) != 1:
        return 'unresolved'
    ids_for_name = [bidder_id for bidder_id in (companies.get('id_key') or {})
                    if names[0] in matched_names(row, bidder_id)]
    if ids_for_name != [uniform]:
        return 'unresolved'
    roles = (companies.get('name_key') or {}).get(names[0], [])
    winner = any(re.search(r':得標廠商\d+:', key) for key in roles)
    nonwinner = any(':未得標廠商' in key for key in roles)
    if winner and nonwinner:
        return 'unresolved'
    detail = row.get('detail') or {}
    bidder_paths = [key.rsplit(':', 1)[0] for key in (companies.get('id_key') or {}).get(uniform, [])
                    if key.startswith('投標廠商:')]
    declared_roles = {str(detail.get(path + ':是否得標')).strip()
                      for path in bidder_paths if detail.get(path + ':是否得標') is not None}
    if len(declared_roles) > 1 or ('是' in declared_roles and nonwinner) or ('否' in declared_roles and winner):
        return 'unresolved'
    if declared_roles == {'是'}:
        return 'winner'
    if declared_roles == {'否'}:
        return 'nonwinner'
    if winner:
        return 'winner'
    if nonwinner:
        return 'nonwinner'
    return 'unresolved'


def is_award_notice(row: dict[str, Any]) -> bool:
    """An unsuccessful-tender notice also contains 決標, but is not an award."""
    brief = row.get('brief') if isinstance(row, dict) else None
    return isinstance(brief, dict) and str(brief.get('type') or '').strip() == '決標公告'


def lookup_awards(uniform: str, limit: int = 100, timeout: int = 40) -> dict[str, Any]:
    if not uniform.isdigit() or len(uniform) != 8:
        raise ValueError("統編必須是 8 碼數字。")
    url = API + "?" + urllib.parse.urlencode({"query": uniform, "page": 1})
    try:
        payload = _json_get(url, timeout=timeout)
        rows = payload.get("records") if isinstance(payload.get("records"), list) else []
        notices = [row for row in rows if is_award_notice(row)]
        invalid_record_count = sum(not _notice_shape_valid(row) for row in rows)
        try:
            total_records = max(len(rows), int(payload.get('total_records') or 0))
        except (TypeError, ValueError, OverflowError):
            total_records = len(rows)
            invalid_record_count += 1
        # Select the latest notice before classifying: a correction can withdraw
        # a formerly successful award. Keep unknown keys separate, not merged.
        latest = {}
        ambiguous = set()
        for index, row in enumerate(sorted(notices, key=lambda item: str(item.get('date')))):
            key = (row.get('unit_id'), row.get('job_number'))
            if not all(isinstance(part, (str, int)) and part for part in key):
                key = ('notice', str(row.get('filename')), str(row.get('date')), index)
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
            "available_notices": total_records,
            "invalid_record_count": invalid_record_count,
            "records": awards[:limit],
            "returned_notices": len(rows),
            "award_notices": len(notices),
            "nonwinner_count": sum(award_role(row, uniform) == 'nonwinner' for row in classified),
            "unresolved_count": len(ambiguous) + sum(award_role(row, uniform) == 'unresolved' for row in classified),
            "limited": bool(invalid_record_count or total_records > len(rows) or len(awards) > limit),
            "source": "政府電子採購網公告（OpenFun 民間結構化介接）",
            "source_api": API, "official_search_url": OFFICIAL_SEARCH,
            "match_rule": "exact bidder identifier field path and explicit winner role; latest notice per job; first page only",
            "verification_scope": "structured_mirror_only;official_row_requires_separate_review",
        }
    except Exception as exc:
        return {
            "status": "partial", "matched": 0, "available_notices": 0,
            "records": [], "limited": False,
            "source": "政府電子採購網公告（OpenFun 民間結構化介接）",
            "official_search_url": OFFICIAL_SEARCH,
            "message": f"決標資料暫時無法讀取：{type(exc).__name__}",
            "source_error": _source_error(exc),
            "attempted_at": datetime.now(timezone.utc).isoformat(),
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
            if not isinstance(row, dict) or not is_award_notice(row):
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


def lookup_reviewed_awards(uniform: str, limit: int = 25, timeout: int = 12) -> dict[str, Any]:
    """Return only exact bidder records already compared with the official notice."""
    from src.entities.repository import EntityRepository, EntityStoreUnavailable

    if not re.fullmatch(r"[0-9]{8}", uniform):
        raise ValueError("Company ID must be eight digits")
    result = {"status": "ok", "records": [], "matched": 0, "limited": False,
              "source": "政府電子採購網 / Government e-Procurement",
              "official_search_url": OFFICIAL_SEARCH,
              "verification_scope": "reviewed_official_notices_only"}
    repository = EntityRepository(require_launch_scope=True)
    try:
        company = repository.company_for_uniform(uniform)
        graph = (repository.graph_neighbors(company["id"], limit=min(limit, 25),
                                            relationship_type="CONTRACT_WITH") if company else None)
    except EntityStoreUnavailable:
        return {**result, "status": "partial"}
    if not graph:
        return result
    records = []
    for edge in graph.get("edges", []):
        evidence = edge.get("primary_evidence") or {}
        source = evidence.get("source_locator") or {}
        if (edge.get("source_entity_id") != company["id"]
                or edge.get("relationship_type") != "CONTRACT_WITH"
                or source.get("review_method") != "official_row_compared_with_exact_bidder_id_and_award_role"
                or source.get("bidder_uniform_number") != uniform or source.get("winner") is not True
                or urllib.parse.urlsplit(evidence.get("source_url") or "").hostname != "web.pcc.gov.tw"
                or not all(source.get(key) for key in ("unit_id", "job_number", "notice_filename", "award_date"))):
            continue
        records.append({**{key: source.get(key) for key in ("title", "agency", "unit_id", "job_number", "amount", "notice_filename")},
                        "id": f"{source['unit_id']}:{source['job_number']}:{source['notice_filename']}",
                        "date": source["award_date"], "notice_type": "決標公告", "award_role": "winner",
                        "uniform_number": uniform, "source_url": evidence["source_url"],
                        "official_search_url": OFFICIAL_SEARCH, "retrieved_at": evidence.get("retrieved_at"),
                        "publication_status": "published", "identity_status": "verified_identifier",
                        "verification_scope": "reviewed_official_notice"})
    records.sort(key=lambda row: row["date"], reverse=True)
    return {**result, "records": records, "matched": len(records),
            "retrieved_at": max((r["retrieved_at"] for r in records if r["retrieved_at"]), default=None),
            "limited": bool(graph.get("has_more"))}


def lookup_company_awards(uniform: str, limit: int = 100, timeout: int = 8) -> dict[str, Any]:
    """Include exact-ID OpenFun observations and prefer independently reviewed notices."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        reviewed_job = pool.submit(lookup_reviewed_awards, uniform, limit=limit, timeout=timeout)
        mirror = lookup_awards(uniform, limit=limit, timeout=timeout)
        reviewed = reviewed_job.result()
    official_rows = reviewed["records"]
    official_keys = {(row["unit_id"], row["job_number"]) for row in official_rows}
    mirror_rows = [
        row for row in mirror["records"]
        if row.get("unit_id") and row.get("job_number") and row.get("source_url")
        and (row["unit_id"], row["job_number"]) not in official_keys
    ]
    records = [
        {**row, "source_name": source["source"],
         "retrieved_at": row.get("retrieved_at") or source.get("retrieved_at")}
        for source, rows in ((reviewed, official_rows), (mirror, mirror_rows)) for row in rows
    ]
    records.sort(key=lambda row: row["date"], reverse=True)
    partial = mirror["status"] != "ok" or reviewed["status"] != "ok"
    return {**mirror, "records": records[:limit], "matched": min(len(records), limit),
            "status": "partial" if partial and not records else "ok",
            "limited": partial or mirror["limited"] or reviewed["limited"] or len(records) > limit,
            "source": "政府電子採購網及 OpenFun 公告介接 / Government e-Procurement and OpenFun",
            "verification_scope": "per_record"}


def _notice_text(value):
    """Keep source wording (including zero/reasons), never infer a money unit."""
    if value is None or isinstance(value, (dict, list)):
        return None
    return re.sub(r'\s+', ' ', str(value)).strip() or None


def normalize_notice_detail(row):
    """Whitelisted source fields; bidder and item roles stay notice-scoped."""
    detail = row.get('detail') or {}
    if not isinstance(detail, dict):
        raise ValueError('Notice detail is malformed')

    def fields(pairs):
        return [{'label': label, 'value': text, 'source_field': key}
                for label, key in pairs if (text := _notice_text(detail.get(key))) is not None]

    summary = fields([
        ('預算金額 / Budget', '已公告資料:預算金額'),
        ('預算公開狀態 / Budget disclosure', '已公告資料:預算金額是否公開'),
        ('總決標金額 / Total award amount', '決標資料:總決標金額'),
        ('決標金額公開狀態 / Award disclosure', '決標資料:總決標金額是否公開'),
        ('招標方式 / Tender method', '已公告資料:招標方式'),
        ('決標方式 / Award method', '已公告資料:決標方式'),
        ('限制性招標依據 / Legal basis', '已公告資料:限制性招標依據之法條'),
        ('標的分類 / Procurement category', '已公告資料:標的分類'),
        ('決標日期 / Award date', '決標資料:決標日期'),
        ('公告日期 / Notice date', '決標資料:決標公告日期'),
        ('公告序號 / Notice sequence', '決標資料:決標公告序號'),
        ('公告更正序號 / Correction sequence', '已公告資料:公告更正序號'),
        ('投標家數 / Bidder count', '投標廠商:投標廠商家數'),
        ('附加說明 / Additional information', '決標資料:附加說明'),
    ])
    # Prefixes come from the source's exact paths, never a fuzzy company-name join.
    prefixes = sorted({m[1] for key in detail
                       if (m := re.fullmatch(r'(投標廠商:投標廠商\d+):[^:]+', key))},
                      key=lambda p: int(re.search(r'\d+$', p)[0]))
    bidders = []
    for prefix in prefixes:
        bidders.append(fields([(label, prefix + ':' + key) for label, key in [
            ('廠商名稱 / Bidder', '廠商名稱'), ('統編 / Company ID', '廠商代碼'),
            ('是否得標 / Awarded', '是否得標'), ('決標金額 / Award amount', '決標金額'),
            ('履約期間（來源原文） / Contract period', '履約起迄日期')]]))
    item_prefixes = sorted({m[1] for key in detail if
                            (m := re.fullmatch(r'(決標品項:第\d+品項:(?:未得標廠商|得標廠商)\d+):[^:]+', key))})
    items = []
    for prefix in item_prefixes:
        parent = prefix.rsplit(':', 1)[0]
        entry = fields([('品項 / Item', parent + ':品項名稱')])
        entry += [{'label': '品項角色 / Item role',
                   'value': '未得標 / Not awarded' if ':未得標廠商' in prefix else '得標 / Awarded',
                   'source_field': prefix}]
        entry += fields([(label, prefix + ':' + key) for label, key in [
            ('廠商 / Vendor', '得標廠商'), ('廠商 / Vendor', '未得標廠商'),
            ('原始投標金額 / Original bid', '得標廠商原始投標金額'),
            ('標價金額 / Bid price', '標價金額'), ('決標金額 / Award amount', '決標金額'),
            ('是否合格 / Qualified', '是否合格'), ('未得標原因 / Reason not awarded', '未得標原因'),
            ('評選序位或總評分 / Rank or score', '評選序位或總評分')]])
        items.append(entry)
    lifecycle = fields([
        ('履約地點 / Contract location', '已公告資料:履約地點'),
        ('契約編號 / Contract ID', '決標資料:契約編號'),
        ('契約變更 / Contract change', '決標資料:契約變更'),
        ('驗收結果 / Acceptance result', '決標資料:驗收結果'),
        ('結算金額 / Final settlement', '決標資料:結算金額'),
    ])
    official = str(detail.get('url') or '')
    try:
        parts = urllib.parse.urlsplit(official)
    except ValueError:
        parts = urllib.parse.urlsplit('')
    official = official if parts.scheme == 'https' and parts.hostname == 'web.pcc.gov.tw' and not parts.username else None
    return {'summary': summary, 'bidders': [b for b in bidders if b], 'items': items,
            'lifecycle': lifecycle, 'official_notice_url': official,
            'source_fetched_at': detail.get('fetched_at'),
            'coverage_note': '僅本公告公開欄位；未提供不代表零或未發生。附件、完整變更、驗收與結算若未載明，請至官方公告核對。 / Fields in this notice only; missing is not zero or proof of absence.'}


def lookup_notice_detail(unit_id, job_number, filename, timeout=8):
    """Fetch one exact notice version without changing publication or identity state."""
    if (not re.fullmatch(r'[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*', unit_id or '')
            or len(unit_id) > 80 or not re.fullmatch(r'[\w()./-]{1,100}', job_number or '')
            or not re.fullmatch(r'[\w-]{1,120}', filename or '')):
        raise ValueError('Invalid notice locator')
    url = API.rsplit('/', 1)[0] + '/tender?' + urllib.parse.urlencode(
        {'unit_id': unit_id, 'job_number': job_number})
    try:
        payload = _json_get(url, timeout=timeout)
        rows = [row for row in payload['records'] if isinstance(row, dict)
                and row.get('filename') == filename and row.get('unit_id') == unit_id
                and str(row.get('job_number')) == job_number]
        if len(rows) != 1 or not isinstance(rows[0].get('detail'), dict):
            return {'status': 'unavailable', 'message': '來源未提供此版本明細 / Exact notice detail unavailable'}
        detail = rows[0]['detail']
        if any(detail.get(key) is not None and str(detail[key]) != value for key, value in
               [('機關資料:機關代碼', unit_id), ('已公告資料:標案案號', job_number)]):
            return {'status': 'unavailable', 'message': '公告識別不一致 / Conflicting notice identifiers'}
        return {'status': 'ok', **normalize_notice_detail(rows[0]),
                'unit_id': unit_id, 'job_number': job_number, 'filename': filename,
                'source_url': url, 'source_name': '政府電子採購網公告（OpenFun 結構化介接）',
                'retrieved_at': datetime.now(timezone.utc).isoformat(),
                'verification_scope': 'structured_mirror_not_independently_verified_official'}
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return {'status': 'unavailable', 'message': '來源暫時無法讀取，可稍後重試 / Source unavailable; retry later',
                'source_error': _source_error(exc)}
