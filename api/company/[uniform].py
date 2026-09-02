from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request


COMPANY_API = "https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6"
DIRECTOR_API = "https://data.gcis.nat.gov.tw/od/data/api/4E5F7653-1B91-4DDC-99D5-468530FAE396"


def _json_get(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": "T.E.I./5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8-sig", "replace"))


def _rows(api: str, uniform: str, top: int):
    params = urllib.parse.urlencode({"$format": "json", "$filter": f"Business_Accounting_NO eq {uniform}", "$skip": "0", "$top": str(top)})
    payload = _json_get(api + "?" + params)
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("records", "data", "result", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def _company(uniform: str, rows: list[dict]):
    basic = rows[0] if rows else {"Business_Accounting_NO": uniform}
    name = basic.get("Company_Name") or basic.get("Juristic_Person_Name") or uniform
    people_rows = _rows(DIRECTOR_API, uniform, 1000)
    people = []
    nodes = [{"id": f"company:{uniform}", "type": "company", "label": name, "properties": {"uniform_number": uniform, "source": "經濟部商工行政資料開放平台"}}]
    edges = []
    for idx, row in enumerate(people_rows[:50], 1):
        person = row.get("Person_Name") or row.get("person_name")
        if not person:
            continue
        position = row.get("Person_Position_Name") or row.get("position") or "董監事"
        shares = row.get("Person_Shareholding") or row.get("shares")
        representative = row.get("Representative") or row.get("representative")
        people.append({"uniform_number": uniform, "company_name": name, "person_name": person, "position": position, "shares": shares, "representative": representative})
        pid = f"person:{person}:{idx}"
        nodes.append({"id": pid, "type": "person", "label": person, "properties": {"position": position, "shares": shares, "representative": representative, "source": "經濟部公司登記董監事資料"}})
        edges.append({"source": f"company:{uniform}", "target": pid, "relationship": position, "properties": {"source": "MOEA_DIRECTOR_API", "live": True}})

    evidence_status = {}
    evidence = []
    try:
        from src.public_evidence import collect_public_evidence
        result = collect_public_evidence(name, [p["person_name"] for p in people])
        if isinstance(result, tuple) and len(result) == 2:
            evidence, evidence_status = result
        elif isinstance(result, dict):
            evidence = result.get("evidence") or []
            evidence_status = result.get("statuses") or {}
        else:
            evidence_status = {"Gateway": {"status": "error", "matched": 0, "message": "來源回傳格式無法解析"}}
    except Exception as exc:
        evidence_status = {"Gateway": {"status": "error", "matched": 0, "message": f"公開來源查詢失敗：{type(exc).__name__}: {exc}"}}

    return {
        "uniform_number": uniform,
        "company": basic,
        "company_name": name,
        "people": people,
        "graph": {"nodes": nodes, "edges": edges},
        "evidence": evidence if isinstance(evidence, list) else [],
        "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
        "local_context": {"configured": False, "evidence": [], "evidence_count": 0},
        "evidence_status": evidence_status,
        "website_crosscheck": {"status": "not_checked", "matched": 0, "message": "公司網址交叉比對由來源層獨立處理。"},
        "judicial_search_url": "https://judgment.judicial.gov.tw/FJUD/qryresult.aspx?kw=" + urllib.parse.quote_plus(name) + "&judtype=JUDBOOK",
        "data_mode": "live_moea_plus_public_sources",
        "evidence_note": "來源讀取成功與是否命中是兩個不同指標；公開紀錄不直接等於法律結論。",
    }


def handler(request):
    path_value = None
    if isinstance(request, dict):
        path_value = (request.get("path") or "").rstrip("/").split("/")[-1]
        if not path_value and request.get("queryStringParameters"):
            path_value = request["queryStringParameters"].get("uniform")
    uniform = str(path_value or "").strip()
    if not re.fullmatch(r"\d{8}", uniform):
        return {"statusCode": 400, "headers": {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}, "body": json.dumps({"error": "統編必須是 8 碼數字。"}, ensure_ascii=False)}
    try:
        company_rows = _rows(COMPANY_API, uniform, 1)
        payload = _company(uniform, company_rows)
        return {"statusCode": 200, "headers": {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}, "body": json.dumps(payload, ensure_ascii=False)}
    except urllib.error.HTTPError as exc:
        return {"statusCode": 502, "headers": {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}, "body": json.dumps({"error": "公司資料來源查詢失敗", "detail": str(exc)}, ensure_ascii=False)}
    except Exception as exc:
        return {"statusCode": 502, "headers": {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}, "body": json.dumps({"error": "公司查詢失敗", "detail": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)}
