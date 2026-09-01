"""T.E.I. live API gateway.

Serves the browser UI and combines:
- Taiwan Ministry of Economic Affairs (GCI) public APIs
- Existing Supabase evidence/source layer (read-only from the app)
- Existing source adapters for labor penalties, anti-fraud and environment penalties

No service-role/secret key is returned to the browser.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote

COMPANY_API = "https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6"
DIRECTOR_API = "https://data.gcis.nat.gov.tw/od/data/api/4E5F7653-1B91-4DDC-99D5-468530FAE396"
SUPABASE = os.environ.get("SUPABASE_URL", "https://rztdbdurkjfrirsrrhtu.supabase.co")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_ANON_KEY")
    or os.environ.get("VITE_SUPABASE_ANON_KEY")
)
JUDICIAL_SEARCH = "https://judgment.judicial.gov.tw/LAW_Mobile_FJUD/FJUD/qryresult.aspx?judtype=JUDBOOK&kw={}"


def _json_get(url: str, timeout: int = 15, headers=None):
    req = urllib.request.Request(
        url,
        headers=headers or {"User-Agent": "T.E.I./3.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8-sig", "replace"))


def _company_filter(api: str, field: str, value: str, top: int = 100):
    params = urllib.parse.urlencode(
        {
            "$format": "json",
            "$filter": f"{field} eq {value}",
            "$skip": "0",
            "$top": str(top),
        }
    )
    payload = _json_get(api + "?" + params)
    return payload if isinstance(payload, list) else []


def _supabase_get(path: str, params: dict[str, str] | None = None, limit: int = 100):
    if not SUPABASE_KEY:
        return None, "not_configured"
    qs = {"select": "*", "limit": str(limit)}
    if params:
        qs.update(params)
    url = f"{SUPABASE}/rest/v1/{path}?{urllib.parse.urlencode(qs, safe=',') }"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
            "User-Agent": "T.E.I./3.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8-sig", "replace")), "ok"
    except urllib.error.HTTPError as exc:
        return {"error": exc.read().decode("utf-8", errors="replace")[:800]}, "error"
    except Exception as exc:
        return {"error": str(exc)}, "error"


def _edge(slug: str, params: dict[str, str]):
    if not SUPABASE_KEY:
        return {"status": "not_configured", "matched": 0, "message": "Supabase key not configured"}
    q = urllib.parse.urlencode(params)
    url = f"{SUPABASE}/functions/v1/{slug}?{q}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "apikey": SUPABASE_KEY,
            "User-Agent": "T.E.I./3.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode("utf-8-sig", "replace"))
    except Exception as exc:
        return {"status": "error", "matched": 0, "message": str(exc)}


def _as_rows(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for k in ("result", "data", "records", "items", "rows"):
            if isinstance(value.get(k), list):
                return value[k]
    return []


def _evidence_card(source: str, dataset: str, row: dict, idx: int, title_keys: tuple[str, ...], note: str):
    title = next((str(row.get(k)) for k in title_keys if row.get(k)), source)
    return {
        "source": {"type": "government_open_data", "name": source, "dataset_id": dataset},
        "fact": {"type": dataset, "title": title, "summary": note},
        "external_id": f"{dataset}:{idx}",
        "source_url": row.get("source_url") or row.get("來源網址") or row.get("URL"),
        "event_date": row.get("date") or row.get("日期") or row.get("裁罰日期"),
        "raw": row,
    }


def _local_context(uniform: str):
    if not SUPABASE_KEY:
        return {
            "configured": False,
            "company": None,
            "evidence": [],
            "evidence_count": 0,
            "source_files": None,
            "error": "SUPABASE_SERVICE_ROLE_KEY / SUPABASE_ANON_KEY 未設定",
        }

    company_rows, c_status = _supabase_get(
        "companies",
        {"uniform_number": f"eq.{uniform}"},
        5,
    )
    evidence_rows, e_status = _supabase_get(
        "evidence",
        {"entity_type": "eq.company", "entity_key": f"eq.{uniform}"},
        100,
    )
    if not isinstance(evidence_rows, list):
        evidence_rows = []

    return {
        "configured": c_status == "ok" or e_status == "ok",
        "company": company_rows[0] if isinstance(company_rows, list) and company_rows else None,
        "evidence": evidence_rows,
        "evidence_count": len(evidence_rows),
        "source_files": None,
        "error": None if c_status == "ok" and e_status == "ok" else "Supabase read partially unavailable",
    }


def source_catalog():
    return {
        "公司登記": {"status": "live", "publisher": "經濟部商業署商工行政資料開放平台"},
        "董監事": {"status": "live", "publisher": "經濟部商業署商工行政資料開放平台"},
        "勞動裁罰": {"status": "adapter", "publisher": "勞動部公開資料"},
        "165反詐": {"status": "adapter", "publisher": "警政署165相關公開資料"},
        "環境裁罰": {"status": "adapter", "publisher": "環境部公開資料"},
        "司法院": {"status": "link", "publisher": "司法院裁判書系統"},
        "政府採購": {"status": "partial", "publisher": "政府電子採購網 / PCC"},
    }


def build_company(uniform: str):
    basic_rows = _company_filter(COMPANY_API, "Business_Accounting_NO", uniform, 1)
    basic = basic_rows[0] if basic_rows else {"Business_Accounting_NO": uniform}
    name = basic.get("Company_Name") or basic.get("Juristic_Person_Name") or uniform

    director_rows = _company_filter(DIRECTOR_API, "Business_Accounting_NO", uniform, 1000)
    people = []
    nodes = [
        {
            "id": f"company:{uniform}",
            "type": "company",
            "label": name,
            "properties": {
                "uniform_number": uniform,
                "source": "經濟部商工行政資料開放平台",
            },
        }
    ]
    edges = []

    for row in director_rows[:40]:
        person = row.get("Person_Name") or row.get("person_name")
        if not person:
            continue
        position = row.get("Person_Position_Name") or row.get("position") or "董監事"
        shares = row.get("Person_Shareholding") or row.get("shares")
        representative = row.get("Representative") or row.get("representative")
        people.append(
            {
                "uniform_number": uniform,
                "company_name": name,
                "person_name": person,
                "position": position,
                "shares": shares,
                "representative": representative,
            }
        )
        pid = f"person:{person}:{len(people)}"
        nodes.append(
            {
                "id": pid,
                "type": "person",
                "label": person,
                "properties": {
                    "position": position,
                    "shares": shares,
                    "representative": representative,
                    "source": "經濟部公司登記董監事資料",
                },
            }
        )
        edges.append(
            {
                "source": f"company:{uniform}",
                "target": pid,
                "relationship": position,
                "properties": {"source": "MOEA_DIRECTOR_API", "live": True},
            }
        )

    local = _local_context(uniform)
    evidence = list(local.get("evidence") or [])
    statuses = {}

    labor = _edge("labor-penalties-api", {"company": name, "limit": "50"})
    lrows = _as_rows(labor)
    evidence.extend(
        _evidence_card(
            "勞動部政府公開資料 API",
            "administrative_penalty",
            row,
            i,
            ("事業單位名稱或負責人", "事業單位名稱", "name"),
            "勞動部公開資料命中；這是來源紀錄，不等於法律結論。",
        )
        for i, row in enumerate(lrows[:50])
    )
    statuses["勞動裁罰"] = {
        "status": "ok" if isinstance(labor, dict) and labor.get("status") not in ("error", "not_configured") else labor.get("status", "error"),
        "matched": len(lrows),
    }

    fraud = _edge("anti-fraud-api", {"q": name, "limit": "50"})
    frows = _as_rows(fraud)
    evidence.extend(
        _evidence_card(
            "165 反詐騙公開資料",
            "anti_fraud_domain",
            row,
            i,
            ("WEBURL", "WEBSITE_NM", "網域", "網站名稱", "name"),
            "165 公開資料命中；表示來源存在相符紀錄，不代表此企業本身已被認定涉詐。",
        )
        for i, row in enumerate(frows[:50])
    )
    statuses["165反詐"] = {"status": "ok" if isinstance(fraud, dict) and fraud.get("status") != "error" else "error", "matched": len(frows)}

    env = _edge("environment-penalties-api", {"q": name, "limit": "50"})
    erows = _as_rows(env)
    evidence.extend(
        _evidence_card(
            "環境部裁罰處分",
            "environment_penalty",
            row,
            i,
            ("name", "行為人名稱", "case", "案件名稱"),
            "環境部公開裁罰資料命中；請以原始處分文件核對時間與內容。",
        )
        for i, row in enumerate(erows[:50])
    )
    statuses["環境裁罰"] = {"status": "ok" if isinstance(env, dict) and env.get("status") != "error" else "error", "matched": len(erows)}

    statuses["政府採購"] = {
        "status": "partial",
        "matched": 0,
        "message": "目前展示來源狀態，不冒充不存在的官方直接統編 API。",
    }
    statuses["司法院"] = {
        "status": "link",
        "matched": 0,
        "message": "可由名稱直接開啟司法院裁判書查詢；API 帳號尚未設定。",
    }

    # Deduplicate cards by external identity while keeping live + local provenance.
    seen = set()
    deduped = []
    for e in evidence:
        k = (e.get("source", {}).get("dataset_id"), e.get("external_id"))
        if k in seen:
            continue
        seen.add(k)
        deduped.append(e)

    return {
        "uniform_number": uniform,
        "company": basic,
        "company_name": name,
        "people": people,
        "graph": {"nodes": nodes, "edges": edges},
        "evidence": deduped[:150],
        "evidence_count": len(deduped[:150]),
        "local_context": local,
        "evidence_status": statuses,
        "source_catalog": source_catalog(),
        "judicial_search_url": JUDICIAL_SEARCH.format(urllib.parse.quote_plus(name)),
        "data_mode": "live_public_api_plus_supabase",
        "evidence_note": "觀測到公開紀錄 ≠ 法律結論。系統刻意把來源證據與推論分開。",
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict, ctype: str = "application/json; charset=utf-8"):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: str, ctype: str):
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/company/"):
            uid = unquote(path.split("/api/company/", 1)[1])
            if not uid.isdigit() or len(uid) != 8:
                return self._send(400, {"error": "統編必須是 8 碼數字。"})
            try:
                return self._send(200, build_company(uid))
            except Exception as exc:
                return self._send(502, {"error": "來源查詢失敗", "detail": str(exc)})

        if path == "/api/status":
            supa = {"configured": bool(SUPABASE_KEY), "source_files": 0, "companies": 0, "people": 0, "evidence": 0}
            if SUPABASE_KEY:
                for table in ("source_files", "companies", "people", "evidence"):
                    rows, status = _supabase_get(table, None, 1000)
                    if isinstance(rows, list):
                        supa[table] = len(rows)
                    else:
                        supa[f"{table}_status"] = status
            return self._send(200, {"status": "ok", "version": "3.0", "supabase": supa, "sources": source_catalog()})

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        web = os.path.join(root, "web")
        if path in ("", "/"):
            return self._send_file(os.path.join(web, "index.html"), "text/html; charset=utf-8")
        if path == "/app.js":
            return self._send_file(os.path.join(web, "app.js"), "application/javascript; charset=utf-8")
        if path == "/tei-enhancements.js":
            return self._send_file(os.path.join(web, "tei-enhancements.js"), "application/javascript; charset=utf-8")
        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt, *args):
        return


handler = Handler
