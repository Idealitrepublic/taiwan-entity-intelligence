from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote, urlparse

COMPANY_API = "https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6"
DIRECTOR_API = "https://data.gcis.nat.gov.tw/od/data/api/4E5F7653-1B91-4DDC-99D5-468530FAE396"
SUPABASE = os.environ.get("SUPABASE_URL", "https://rztdbdurkjfrirsrrhtu.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("VITE_SUPABASE_ANON_KEY")
JUDICIAL_SEARCH = "https://judgment.judicial.gov.tw/FJUD/qryresult.aspx?kw={}&judtype=JUDBOOK"


def _json_get(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": "T.E.I./7.0", "Accept": "application/json, text/plain, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8-sig", "replace"))


def _rows(payload):
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("data", "records", "items", "result", "rows", "value"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def _moea_rows(api: str, uniform: str, top: int):
    params = urllib.parse.urlencode({"$format": "json", "$filter": f"Business_Accounting_NO eq {uniform}", "$skip": "0", "$top": str(top)})
    return _rows(_json_get(api + "?" + params))


def _supabase_evidence(uniform: str):
    if not SUPABASE_KEY:
        return [], False
    params = urllib.parse.urlencode({"select": "*", "entity_type": "eq.company", "entity_key": f"eq.{uniform}", "limit": "100"})
    req = urllib.request.Request(f"{SUPABASE}/rest/v1/evidence?{params}", headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8-sig", "replace"))
            return (data if isinstance(data, list) else []), True
    except Exception:
        return [], False


def _supabase_company(uniform: str):
    if not SUPABASE_KEY:
        return None
    params = urllib.parse.urlencode({"select": "*", "uniform_number": f"eq.{uniform}", "limit": "1"})
    req = urllib.request.Request(f"{SUPABASE}/rest/v1/companies?{params}", headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8-sig", "replace"))
            return data[0] if isinstance(data, list) and data else None
    except Exception:
        return None


def build_company(uniform: str):
    company_rows = _moea_rows(COMPANY_API, uniform, 1)
    if not company_rows:
        return {"status": "not_found", "uniform_number": uniform, "company_name": uniform, "company": {}, "people": [], "graph": {"nodes": [], "edges": []}, "evidence": [], "evidence_count": 0, "evidence_status": {"公司登記": {"status": "not_found", "matched": 0}}, "data_mode": "live_moea_core"}

    company = company_rows[0]
    name = str(company.get("Company_Name") or company.get("Juristic_Person_Name") or uniform)

    director_rows = []
    director_error = None
    try:
        director_rows = _moea_rows(DIRECTOR_API, uniform, 1000)
    except Exception as exc:
        director_error = f"{type(exc).__name__}: {exc}"

    people, nodes, edges = [], [{"id": f"company:{uniform}", "type": "company", "label": name, "properties": {"uniform_number": uniform, "source": "經濟部商工行政資料開放平台"}}], []
    for idx, row in enumerate(director_rows[:50], 1):
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

    evidence, db_ok = _supabase_evidence(uniform)
    local_company = _supabase_company(uniform) if SUPABASE_KEY else None

    website_url = None
    website_host = None
    for key, value in company.items():
        if value is None:
            continue
        k, v = str(key).lower(), str(value).strip()
        if not v or not any(t in k for t in ("url", "website", "網址", "網站")):
            continue
        try:
            raw = v if "://" in v else "https://" + v
            host = urllib.parse.urlparse(raw).hostname
            if host:
                website_url, website_host = raw, host.removeprefix("www.")
                break
        except Exception:
            pass

    statuses = {
        "公司登記": {"status": "ok", "matched": 1},
        "董監事": {"status": "ok" if director_rows else ("partial" if director_error else "ok"), "matched": len(people), **({"message": f"董監事來源暫時不可用：{director_error}"} if director_error else {})},
        "我的資料": {"status": "ok" if db_ok else ("not_configured" if not SUPABASE_KEY else "partial"), "matched": len(evidence)},
        "裁罰": {"status": "not_available_in_public_runtime", "matched": 0, "message": "即時裁罰來源由 Supabase evidence layer 分流。"},
        "165": {"status": "not_available_in_public_runtime", "matched": 0, "message": "即時反詐來源由 Supabase evidence layer 分流。"},
        "標案": {"status": "not_available_in_public_runtime", "matched": 0, "message": "即時標案來源由 Supabase evidence layer 分流。"},
        "司法院": {"status": "link", "matched": 0, "url": JUDICIAL_SEARCH.format(urllib.parse.quote_plus(name))},
    }

    return {
        "status": "ok", "uniform_number": uniform, "company": company, "company_name": name,
        "website_url": website_url, "website_host": website_host, "people": people,
        "graph": {"nodes": nodes, "edges": edges}, "evidence": evidence, "evidence_count": len(evidence),
        "local_context": {"configured": bool(SUPABASE_KEY), "company": local_company, "evidence": evidence, "evidence_count": len(evidence)},
        "evidence_status": statuses,
        "website_crosscheck": {"status": "not_available_in_public_runtime", "matched": 0, "website_url": website_url, "website_host": website_host, "records": [], "message": "網址×165 交叉比對不在 Vercel 核心路由執行。"},
        "judicial_search_url": JUDICIAL_SEARCH.format(urllib.parse.quote_plus(name)),
        "data_mode": "live_moea_core_plus_supabase",
        "evidence_note": "來源讀取成功與是否命中是兩個不同指標；公開紀錄不直接等於法律結論。",
    }


class handler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type, authorization, apikey")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_json(204, {})

    def do_GET(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/company/"):
            self._send_json(404, {"error": "Not found"})
            return
        uniform = unquote(path.split("/api/company/", 1)[1]).strip()
        if not (uniform.isdigit() and len(uniform) == 8):
            self._send_json(400, {"error": "統編必須是 8 碼數字。"})
            return
        try:
            payload = build_company(uniform)
            self._send_json(404 if payload.get("status") == "not_found" else 200, payload)
        except urllib.error.HTTPError as exc:
            self._send_json(502, {"status": "error", "error": "MOEA HTTPError", "detail": str(exc)})
        except Exception as exc:
            self._send_json(502, {"status": "error", "error": "公司查詢失敗", "detail": f"{type(exc).__name__}: {exc}"})

    def log_message(self, fmt, *args):
        return
