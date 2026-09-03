from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request


COMPANY_API = "https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6"
DIRECTOR_API = "https://data.gcis.nat.gov.tw/od/data/api/4E5F7653-1B91-4DDC-99D5-468530FAE396"


def _json_get(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": "T.E.I./6.3", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8-sig", "replace"))


def _rows(api: str, uniform: str, top: int):
    params = urllib.parse.urlencode({"$format": "json", "$filter": f"Business_Accounting_NO eq {uniform}", "$skip": "0", "$top": str(top)})
    payload = _json_get(api + "?" + params)
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("records", "data", "result", "items", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def _company(uniform: str, rows: list[dict]):
    basic = rows[0] if rows else {"Business_Accounting_NO": uniform}
    name = basic.get("Company_Name") or basic.get("Juristic_Person_Name") or uniform

    try:
        people_rows = _rows(DIRECTOR_API, uniform, 1000)
        director_error = None
    except Exception as exc:
        people_rows = []
        director_error = f"董監事來源暫時不可用：{type(exc).__name__}: {exc}"

    people = []
    nodes = [{"id": f"company:{uniform}", "type": "company", "label": name, "properties": {"uniform_number": uniform, "source": "經濟部商工行政資料開放平台"}}]
    edges = []
    for idx, row in enumerate(people_rows[:50], 1):
        person = row.get("Person_Name") or row.get("person_name") or row.get("Name")
        if not person:
            continue
        position = row.get("Person_Position_Name") or row.get("position") or row.get("Position") or "董監事"
        shares = row.get("Person_Shareholding") or row.get("shares")
        representative = row.get("Representative") or row.get("representative")
        people.append({"uniform_number": uniform, "company_name": name, "person_name": person, "position": position, "shares": shares, "representative": representative})
        pid = f"person:{person}:{idx}"
        nodes.append({"id": pid, "type": "person", "label": person, "properties": {"position": position, "shares": shares, "representative": representative, "source": "經濟部公司登記董監事資料"}})
        edges.append({"source": f"company:{uniform}", "target": pid, "relationship": position, "properties": {"source": "MOEA_DIRECTOR_API", "live": True}})

    # The Vercel company route is deliberately core-only. The previous implementation
    # executed the slow multi-source public evidence collector here; one upstream
    # parser failure could bubble into a production 500 (the observed tuple-index error).
    # Evidence collection remains available through the Supabase T.E.I. console.
    evidence_status = {
        "公司登記": {"status": "ok", "matched": 1},
        "董監事": {
            "status": "ok" if people_rows else ("partial" if director_error else "ok"),
            "matched": len(people),
            **({"message": director_error} if director_error else {}),
        },
        "裁罰": {"status": "not_available_in_public_runtime", "matched": 0, "message": "請使用 Supabase T.E.I. console 取得即時公開裁罰資料。"},
        "165": {"status": "not_available_in_public_runtime", "matched": 0, "message": "請使用 Supabase T.E.I. console 取得即時反詐資料。"},
        "標案": {"status": "not_available_in_public_runtime", "matched": 0, "message": "請使用 Supabase T.E.I. console 取得即時標案資料。"},
        "司法院": {"status": "link", "matched": 0, "message": "官方裁判書查詢入口"},
    }

    return {
        "status": "ok",
        "uniform_number": uniform,
        "company": basic,
        "company_name": name,
        "people": people,
        "graph": {"nodes": nodes, "edges": edges},
        "evidence": [],
        "evidence_count": 0,
        "local_context": {"configured": False, "evidence": [], "evidence_count": 0, "message": "本路由維持核心資料隔離；證據層由 Supabase T.E.I. console 提供。"},
        "evidence_status": evidence_status,
        "website_crosscheck": {"status": "not_available_in_public_runtime", "matched": 0, "message": "網址×165 交叉比對由 Supabase T.E.I. console 執行。"},
        "judicial_search_url": "https://judgment.judicial.gov.tw/FJUD/qryresult.aspx?kw=" + urllib.parse.quote_plus(name) + "&judtype=JUDBOOK",
        "data_mode": "live_moea_core",
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
        if not company_rows:
            return {"statusCode": 404, "headers": {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}, "body": json.dumps({"status": "not_found", "uniform_number": uniform}, ensure_ascii=False)}
        payload = _company(uniform, company_rows)
        return {"statusCode": 200, "headers": {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}, "body": json.dumps(payload, ensure_ascii=False)}
    except urllib.error.HTTPError as exc:
        return {"statusCode": 502, "headers": {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}, "body": json.dumps({"error": "公司資料來源查詢失敗", "detail": str(exc)}, ensure_ascii=False)}
    except Exception as exc:
        return {"statusCode": 502, "headers": {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}, "body": json.dumps({"error": "公司查詢失敗", "detail": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)}
