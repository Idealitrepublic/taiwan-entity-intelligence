"""T.E.I. live API gateway."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote

from .public_evidence import collect_public_evidence

COMPANY_API = "https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6"
DIRECTOR_API = "https://data.gcis.nat.gov.tw/od/data/api/4E5F7653-1B91-4DDC-99D5-468530FAE396"
SUPABASE = os.environ.get("SUPABASE_URL", "https://rztdbdurkjfrirsrrhtu.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("VITE_SUPABASE_ANON_KEY")
JUDICIAL_SEARCH = "https://judgment.judicial.gov.tw/FJUD/qryresult.aspx?kw={}&judtype=JUDBOOK"


def _json_get(url: str, timeout: int = 20, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "T.E.I./4.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8-sig", "replace"))


def _company_filter(api: str, field: str, value: str, top: int):
    params = urllib.parse.urlencode({"$format": "json", "$filter": f"{field} eq {value}", "$skip": "0", "$top": str(top)})
    payload = _json_get(api + "?" + params)
    return payload if isinstance(payload, list) else []


def _supabase_get(path: str, params: dict[str, str] | None = None, limit: int = 100):
    if not SUPABASE_KEY:
        return None, "not_configured"
    qs = {"select": "*", "limit": str(limit)}
    if params:
        qs.update(params)
    url = f"{SUPABASE}/rest/v1/{path}?{urllib.parse.urlencode(qs, safe=',') }"
    req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Accept": "application/json", "User-Agent": "T.E.I./4.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8-sig", "replace")), "ok"
    except urllib.error.HTTPError as exc:
        return {"error": exc.read().decode("utf-8", errors="replace")[:800]}, "error"
    except Exception as exc:
        return {"error": str(exc)}, "error"


def _edge(slug: str, params: dict[str, str]):
    if not SUPABASE_KEY:
        return {"status": "not_configured", "matched": 0, "records": [], "message": "Supabase key not configured"}
    url = f"{SUPABASE}/functions/v1/{slug}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY, "Accept": "application/json", "User-Agent": "T.E.I./4.0"})
    try:
        with urllib.request.urlopen(req, timeout=50) as r:
            return json.loads(r.read().decode("utf-8-sig", "replace"))
    except urllib.error.HTTPError as exc:
        return {"status": "error", "matched": 0, "records": [], "message": exc.read().decode("utf-8", errors="replace")[:800]}
    except Exception as exc:
        return {"status": "error", "matched": 0, "records": [], "message": str(exc)}


def _rows(payload):
    if isinstance(payload, list): return payload
    if isinstance(payload, dict):
        for key in ("records", "data", "result", "items", "rows"):
            if isinstance(payload.get(key), list): return payload[key]
    return []


def _website_from_company(company: dict):
    candidates = []
    for key, value in company.items():
        if value is None: continue
        k = str(key).lower(); v = str(value).strip()
        if not v: continue
        if any(token in k for token in ("website", "web_url", "url", "網址", "網站", "網頁")) and ("." in v or "://" in v): candidates.append(v)
    for value in candidates:
        try:
            raw = value if "://" in value else "https://" + value
            host = urllib.parse.urlparse(raw).hostname or ""
            if host: return raw, host.lower().removeprefix("www.")
        except Exception: pass
    return None, None


def _evidence_card(source: str, dataset: str, row: dict, idx: int, note: str):
    title = next((str(row.get(k)) for k in ("party", "事業單位名稱", "事業單位名稱或負責人", "WEBURL", "網址", "網域名稱", "案件名稱", "標案名稱", "name") if row.get(k)), source)
    return {"source": {"type": "government_open_data", "name": source, "dataset_id": dataset}, "fact": {"type": dataset, "title": title, "summary": note}, "external_id": f"{dataset}:{idx}", "source_url": row.get("source_url") or row.get("來源網址") or row.get("URL"), "event_date": row.get("event_date") or row.get("date") or row.get("公告日期") or row.get("裁罰日期"), "raw": row}


def _local_context(uniform: str):
    if not SUPABASE_KEY: return {"configured": False, "company": None, "evidence": [], "evidence_count": 0, "error": "Supabase key not configured"}
    company_rows, c_status = _supabase_get("companies", {"uniform_number": f"eq.{uniform}"}, 5)
    evidence_rows, e_status = _supabase_get("evidence", {"entity_type": "eq.company", "entity_key": f"eq.{uniform}"}, 100)
    evidence_rows = evidence_rows if isinstance(evidence_rows, list) else []
    return {"configured": c_status == "ok" and e_status == "ok", "company": company_rows[0] if isinstance(company_rows, list) and company_rows else None, "evidence": evidence_rows, "evidence_count": len(evidence_rows), "error": None if c_status == "ok" and e_status == "ok" else "Supabase read partially unavailable"}


def source_catalog():
    return {"公司登記": {"status": "live", "publisher": "經濟部商業署商工行政資料開放平台"}, "董監事": {"status": "live", "publisher": "經濟部商業署商工行政資料開放平台"}, "裁罰": {"status": "live", "publisher": "勞動部政府公開資料"}, "165": {"status": "live", "publisher": "警政署165相關公開資料"}, "標案": {"status": "live", "publisher": "政府公開採購資料集"}, "公司網址×165": {"status": "adapter", "publisher": "公司登記網址 + 165/數位發展部網域清單"}, "司法院": {"status": "link", "publisher": "司法院裁判書系統"}}


def build_company(uniform: str):
    basic_rows = _company_filter(COMPANY_API, "Business_Accounting_NO", uniform, 1)
    basic = basic_rows[0] if basic_rows else {"Business_Accounting_NO": uniform}
    name = basic.get("Company_Name") or basic.get("Juristic_Person_Name") or uniform
    website_url, website_host = _website_from_company(basic)
    director_rows = _company_filter(DIRECTOR_API, "Business_Accounting_NO", uniform, 1000)
    people, nodes, edges = [], [{"id": f"company:{uniform}", "type": "company", "label": name, "properties": {"uniform_number": uniform, "source": "經濟部商工行政資料開放平台"}}], []
    for row in director_rows[:50]:
        person = row.get("Person_Name") or row.get("person_name")
        if not person: continue
        position = row.get("Person_Position_Name") or row.get("position") or "董監事"; shares = row.get("Person_Shareholding") or row.get("shares"); representative = row.get("Representative") or row.get("representative")
        people.append({"uniform_number": uniform, "company_name": name, "person_name": person, "position": position, "shares": shares, "representative": representative})
        pid = f"person:{person}:{len(people)}"; nodes.append({"id": pid, "type": "person", "label": person, "properties": {"position": position, "shares": shares, "representative": representative, "source": "經濟部公司登記董監事資料"}}); edges.append({"source": f"company:{uniform}", "target": pid, "relationship": position, "properties": {"source": "MOEA_DIRECTOR_API", "live": True}})
    local = _local_context(uniform); evidence = list(local.get("evidence") or [])
    public_evidence, public_statuses = collect_public_evidence(name, [p.get("person_name") for p in people]); evidence.extend(public_evidence); statuses = dict(public_statuses)
    if website_host:
        fraud_domain = _edge("anti-fraud-api", {"domain": website_host, "limit": "50"}); fdrows = _rows(fraud_domain); cs = "ok" if fraud_domain.get("status") == "ok" else fraud_domain.get("status", "error"); msg = f"精確比對 {website_host}；命中 {len(fdrows)} 筆。" if cs == "ok" else f"精確比對 {website_host}；來源查詢失敗。"
        for i, row in enumerate(fdrows[:50]): evidence.append(_evidence_card("165/數位發展部反詐騙網域清單", "anti_fraud_domain", row, i, "公司網址與公開涉詐網域清單完成精確網域/子網域比對。"))
        website_crosscheck = {"status": cs, "matched": len(fdrows), "website_url": website_url, "website_host": website_host, "records": fdrows[:50], "message": msg}
    else: website_crosscheck = {"status": "no_website", "matched": 0, "website_url": None, "website_host": None, "records": [], "message": "經濟部公司登記資料未提供可交叉比對的公司網址。"}
    statuses["公司網址×165"] = website_crosscheck; judicial_url = JUDICIAL_SEARCH.format(urllib.parse.quote_plus(name)); statuses["司法院"] = {"status": "link", "matched": 0, "message": "官方裁判書查詢入口", "url": judicial_url}
    seen, deduped = set(), []
    for e in evidence:
        key = (e.get("evidence_id") or e.get("external_id"), e.get("source_url"), e.get("event_date"))
        if key in seen: continue
        seen.add(key); deduped.append(e)
    return {"uniform_number": uniform, "company": basic, "company_name": name, "website_url": website_url, "website_host": website_host, "people": people, "graph": {"nodes": nodes, "edges": edges}, "evidence": deduped[:150], "evidence_count": len(deduped[:150]), "local_context": local, "evidence_status": statuses, "source_catalog": source_catalog(), "website_crosscheck": website_crosscheck, "judicial_search_url": judicial_url, "data_mode": "live_public_api_plus_supabase", "evidence_note": "觀測到公開紀錄 ≠ 法律結論。來源讀取成功與是否命中是兩個不同指標。"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8"); self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/company/"):
            uid = unquote(path.split("/api/company/", 1)[1])
            if not uid.isdigit() or len(uid) != 8: return self._send(400, {"error": "統編必須是 8 碼數字。"})
            try: return self._send(200, build_company(uid))
            except Exception as exc: return self._send(502, {"error": "來源查詢失敗", "detail": str(exc)})
        if path == "/api/status":
            return self._send(200, {"status":"ok", "version":"4.2", "supabase":{"configured":bool(SUPABASE_KEY)}, "source_catalog":source_catalog()})
        self._send(404, {"error":"Not found"})
    def log_message(self, fmt, *args): return


handler = Handler
