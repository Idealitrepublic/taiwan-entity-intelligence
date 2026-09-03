from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
import urllib.error
import urllib.request

COMPANY_API = "https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6"
DIRECTOR_API = "https://data.gcis.nat.gov.tw/od/data/api/4E5F7653-1B91-4DDC-99D5-468530FAE396"
SUPABASE = os.environ.get("SUPABASE_URL", "https://rztdbdurkjfrirsrrhtu.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("VITE_SUPABASE_ANON_KEY")
ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def _response(status: int, payload, content_type: str = "application/json; charset=utf-8"):
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return {
        "statusCode": status,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "content-type, authorization, apikey",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
            "Content-Type": content_type,
            "Cache-Control": "no-store",
        },
        "body": body,
    }


def _path(request) -> str:
    if isinstance(request, dict):
        return str(request.get("path") or request.get("rawPath") or "/")
    for key in ("path", "raw_path", "url"):
        value = getattr(request, key, None)
        if value:
            return str(value).split("?", 1)[0]
    return "/"


def _query(request) -> dict[str, str]:
    if isinstance(request, dict):
        q = request.get("queryStringParameters") or {}
        if isinstance(q, dict):
            return {str(k): str(v) for k, v in q.items() if v is not None}
        raw = str(request.get("rawQueryString") or "")
    else:
        raw = urlparse(str(getattr(request, "url", ""))).query
    return {k: v[-1] if isinstance(v, list) else v for k, v in parse_qs(raw).items()}


def _json_get(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": "T.E.I./6.3", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8-sig", "replace"))


def _rows(payload):
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("data", "records", "items", "result", "value", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def _moea_rows(api: str, uniform: str, top: int):
    query = f"$format=json&$filter=Business_Accounting_NO%20eq%20{uniform}&$skip=0&$top={top}"
    return _rows(_json_get(f"{api}?{query}"))


def _company(uniform: str):
    rows = _moea_rows(COMPANY_API, uniform, 1)
    if not rows:
        return {"status": "not_found", "uniform_number": uniform, "company": {}, "company_name": uniform, "people": [], "graph": {"nodes": [], "edges": []}, "evidence": [], "evidence_count": 0, "evidence_status": {}}
    company = rows[0]
    name = company.get("Company_Name") or company.get("Juristic_Person_Name") or uniform
    try:
        directors = _moea_rows(DIRECTOR_API, uniform, 1000)
        director_error = None
    except Exception as exc:
        directors = []
        director_error = f"{type(exc).__name__}: {exc}"

    people, nodes, edges = [], [{"id": f"company:{uniform}", "type": "company", "label": name, "properties": {"uniform_number": uniform, "source": "經濟部商工行政資料開放平台"}}], []
    seen_people = set()
    for idx, row in enumerate(directors, 1):
        person = str(row.get("Person_Name") or row.get("person_name") or row.get("Name") or "").strip()
        if not person:
            continue
        position = str(row.get("Person_Position_Name") or row.get("position") or row.get("Position") or "董監事").strip()
        key = (person, position)
        if key in seen_people:
            continue
        seen_people.add(key)
        people.append({"uniform_number": uniform, "company_name": name, "person_name": person, "position": position})
        pid = f"person:{person}:{len(people)}"
        nodes.append({"id": pid, "type": "person", "label": person, "properties": {"position": position, "source": "經濟部公司登記董監事資料"}})
        edges.append({"source": f"company:{uniform}", "target": pid, "relationship": position, "properties": {"source": "MOEA_DIRECTOR_API", "live": True}})

    return {
        "status": "ok",
        "uniform_number": uniform,
        "company": company,
        "company_name": name,
        "people": people,
        "graph": {"nodes": nodes, "edges": edges},
        "evidence": [],
        "evidence_count": 0,
        "local_context": {"configured": False, "evidence": [], "evidence_count": 0, "message": "核心 Vercel 路由隔離證據層；完整 evidence 由 Supabase T.E.I. console 提供。"},
        "evidence_status": {
            "公司登記": {"status": "ok", "matched": 1},
            "董監事": {"status": "ok" if directors else ("partial" if director_error else "ok"), "matched": len(people), **({"message": director_error} if director_error else {})},
            "裁罰": {"status": "not_available_in_public_runtime", "matched": 0, "message": "Supabase T.E.I. console"},
            "165": {"status": "not_available_in_public_runtime", "matched": 0, "message": "Supabase T.E.I. console"},
            "標案": {"status": "not_available_in_public_runtime", "matched": 0, "message": "Supabase T.E.I. console"},
            "裁判書": {"status": "link", "matched": 0, "message": "官方裁判書查詢入口"},
        },
        "judicial_search_url": "https://judgment.judicial.gov.tw/FJUD/qryresult.aspx?kw=" + __import__("urllib.parse", fromlist=["quote_plus"]).quote_plus(name) + "&judtype=JUDBOOK",
        "data_mode": "live_moea_core",
        "evidence_note": "來源讀取成功與是否命中是兩個不同指標；公開紀錄不直接等於法律結論。",
    }


def _status():
    return {
        "status": "ok",
        "version": "6.4-standard-handler",
        "supabase": {"configured": bool(SUPABASE_KEY)},
        "routes": ["/api/status", "/api/company/{uniform}", "/api/company-sources"],
        "source_mode": "standard Vercel Python handler + live MOEA core",
    }


def handler(request):
    if isinstance(request, dict) and request.get("httpMethod") == "OPTIONS":
        return _response(204, "")
    if str(getattr(request, "method", "GET")).upper() == "OPTIONS":
        return _response(204, "")

    path = _path(request)
    query = _query(request)
    try:
        if path == "/":
            html = (WEB / "index.html").read_text(encoding="utf-8")
            return _response(200, html, "text/html; charset=utf-8")
        if path == "/app.js":
            js_path = WEB / "app.js"
            if not js_path.exists():
                return _response(404, "app.js not found", "text/plain; charset=utf-8")
            return _response(200, js_path.read_text(encoding="utf-8"), "application/javascript; charset=utf-8")
        if path == "/tei-enhancements.js":
            js_path = WEB / "tei-enhancements.js"
            if not js_path.exists():
                return _response(404, "tei-enhancements.js not found", "text/plain; charset=utf-8")
            return _response(200, js_path.read_text(encoding="utf-8"), "application/javascript; charset=utf-8")
        if path == "/api/status":
            return _response(200, _status())
        if path == "/api/company-sources":
            uniform = str(query.get("uniform") or "").strip()
            if not uniform.isdigit() or len(uniform) != 8:
                return _response(400, {"status": "error", "error": "uniform must be 8 digits"})
            data = _company(uniform)
            return _response(200, {"status": data.get("status"), "uniform_number": uniform, "company_name": data.get("company_name"), "sources": data.get("evidence_status", {})})
        if path.startswith("/api/company/"):
            uniform = unquote(path.split("/api/company/", 1)[1]).strip()
            if not uniform.isdigit() or len(uniform) != 8:
                return _response(400, {"status": "error", "error": "統編必須是 8 碼數字。"})
            return _response(200, _company(uniform))
        return _response(404, {"status": "error", "error": "Not found"})
    except urllib.error.HTTPError as exc:
        return _response(502, {"status": "error", "error": f"上游資料來源 HTTP {exc.code}"})
    except urllib.error.URLError as exc:
        return _response(502, {"status": "error", "error": f"上游資料來源無法連線：{exc.reason}"})
    except Exception as exc:
        return _response(502, {"status": "error", "error": f"Vercel API 執行失敗：{type(exc).__name__}: {exc}"})
