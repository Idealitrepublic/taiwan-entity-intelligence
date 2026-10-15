"""Bounded, read-only company connections from verifiable public identifiers.

These are live observations for the company graph, not published relationships.
No person-name match is ever used to join two companies.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from src.cloud_company import DIRECTOR_API, _moea_rows
from src.company import get_company
from src.sources.procurement import lookup_co_awardees

SEARCH_API = "https://data.gcis.nat.gov.tw/od/data/api/6BBA2268-1367-4B42-9CCA-BC17499EBE8C"
MAX_CONNECTIONS = 6


def _normalized(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or ""))).casefold()


def _exact_name_rows(name):
    expression = f"Company_Name like {name} and Company_Status eq 01"
    params = urllib.parse.urlencode({"$format": "json", "$filter": expression,
                                     "$skip": "0", "$top": "20"})
    request = urllib.request.Request(
        SEARCH_API + "?" + params,
        headers={"Accept": "application/json", "User-Agent": "T.E.I./related-companies"})
    with urllib.request.urlopen(request, timeout=6) as response:
        rows = json.loads(response.read().decode("utf-8-sig", "replace"))
    return rows if isinstance(rows, list) else []


def _juristic_company(name, search_lookup):
    if (not isinstance(name, str) or len(name) > 100
            or not re.fullmatch(r"[\w\u4e00-\u9fff（）()．·・ &.-]+(?:股份有限公司|有限公司)", name)):
        return None
    exact = [row for row in search_lookup(name) if isinstance(row, dict)
             and _normalized(row.get("Company_Name")) == _normalized(name)
             and re.fullmatch(r"[0-9]{8}", str(row.get("Business_Accounting_NO") or ""))]
    uniforms = {str(row["Business_Accounting_NO"]) for row in exact}
    if len(uniforms) != 1:
        return None
    return {"uniform_number": uniforms.pop(), "company_name": exact[0]["Company_Name"]}


def related_companies(uniform, *, company_lookup=get_company, director_lookup=None,
                      name_lookup=_exact_name_rows, coaward_lookup=lookup_co_awardees):
    """Return at most six exact-ID company nodes with source evidence."""
    if not re.fullmatch(r"[0-9]{8}", str(uniform or "")):
        raise ValueError("Company uniform number must contain eight digits")
    director_lookup = director_lookup or (lambda value: _moea_rows(DIRECTOR_API, value, 100))
    with ThreadPoolExecutor(max_workers=3) as pool:
        root_job = pool.submit(company_lookup, uniform, timeout=6)
        director_job = pool.submit(director_lookup, uniform)
        award_job = pool.submit(coaward_lookup, uniform, limit=MAX_CONNECTIONS, timeout=6)
        try:
            root = root_job.result()
        except Exception as exc:
            raise RuntimeError("Official company registry unavailable") from exc
        if not isinstance(root, dict) or str(root.get("Business_Accounting_NO")) != uniform:
            return None
        try:
            directors = director_job.result()
            director_status = "ok"
        except Exception:
            directors, director_status = [], "partial"
        try:
            awards = award_job.result()
        except Exception:
            awards = {"status": "partial", "items": [], "limited": True}

    observed_at = datetime.now(timezone.utc).isoformat()
    candidates = {}
    for row in directors[:100] if isinstance(directors, list) else []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("Juristic_Person_Name") or "").strip()
        if name and name not in candidates:
            candidates[name] = row

    items = []
    names = list(candidates)[:MAX_CONNECTIONS]
    if names:
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {name: pool.submit(_juristic_company, name, name_lookup) for name in names}
            for name, job in jobs.items():
                try:
                    company = job.result()
                except Exception:
                    director_status = "partial"
                    continue
                if not company or company["uniform_number"] == uniform:
                    continue
                row = candidates[name]
                items.append({**company, "connection_type": "corporate_director",
                              "connection_label": "法人董監事所代表公司 / Corporate director's represented company",
                              "evidence": {
                                  "source_name": "經濟部公司登記董監事資料",
                                  "source_record_id": (f"Business_Accounting_NO={uniform};"
                                                       f"Juristic_Person_Name={name};"
                                                       f"Person_Position_Name={row.get('Person_Position_Name') or ''}"),
                                  "locator_type": "query_locator_not_official_record_id",
                                  "source_url": DIRECTOR_API + "?" + urllib.parse.urlencode({
                                      "$format": "json", "$filter": f"Business_Accounting_NO eq {uniform}",
                                      "$skip": "0", "$top": "100"}),
                                  "retrieved_at": observed_at,
                                  "match_method": "official_juristic_name_exact_to_unique_uniform",
                                  "role": row.get("Person_Position_Name") or None}})

    known = {item["uniform_number"] for item in items}
    coaward_rows = (awards.get("items") or [])[:MAX_CONNECTIONS] if isinstance(awards, dict) else []
    remaining = [row for row in coaward_rows if row.get("uniform_number") not in known]
    if remaining and len(items) < MAX_CONNECTIONS:
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = [(row, pool.submit(company_lookup, row["uniform_number"], timeout=6))
                    for row in remaining[:MAX_CONNECTIONS - len(items)]]
            for row, job in jobs:
                try:
                    registry = job.result()
                except Exception:
                    continue
                if (not isinstance(registry, dict)
                        or str(registry.get("Business_Accounting_NO")) != row["uniform_number"]
                        or _normalized(registry.get("Company_Name")) != _normalized(row.get("company_name"))):
                    continue
                notice = row.get("notice") or {}
                if not notice.get("source_url") or not notice.get("id"):
                    continue
                items.append({"uniform_number": row["uniform_number"],
                              "company_name": registry["Company_Name"],
                              "connection_type": "same_award_notice",
                              "connection_label": "同一決標公告得標廠商 / Co-winners in one award notice",
                              "shared_record": {"id": notice["id"],
                                                "title": notice.get("title") or "政府採購決標公告"},
                              "evidence": {"source_name": "政府電子採購網公告（OpenFun 結構化介接）",
                                           "source_record_id": notice["id"],
                                           "source_url": notice["source_url"],
                                           "original_source_url": notice.get("official_search_url"),
                                           "retrieved_at": observed_at,
                                           "match_method": "both_exact_bidder_uniforms_and_winner_roles"}})

    status = "partial" if director_status != "ok" or awards.get("status") != "ok" else "ok"
    return {"status": status, "uniform_number": uniform, "company_name": root.get("Company_Name"),
            "items": items[:MAX_CONNECTIONS], "limited": bool(awards.get("limited"))
            or len(candidates) > MAX_CONNECTIONS or len(items) > MAX_CONNECTIONS,
            "interpretation": "法人董監事或共同得標是公開紀錄中的特定連結，不代表母子公司、持股控制或其他未證實的關係。",
            "coverage_note": "僅查經濟部即時董監事及可取得的第一頁決標公告；未顯示不代表不存在其他關係。"}
