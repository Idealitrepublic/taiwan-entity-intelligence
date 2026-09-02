"""Canonical Vercel entrypoint for T.E.I.

The Vercel adapter is intentionally fail-open for optional evidence sources.
Core company/director data comes from MOEA; optional live-source collection is
served by the Supabase T.E.I. console so a single upstream parser failure can
never turn /api/company/{uniform} into HTTP 500.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs
from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.error

from src.v2server import (
    COMPANY_API,
    DIRECTOR_API,
    SUPABASE,
    SUPABASE_KEY,
    _company_filter,
    _local_context,
    _website_from_company,
)

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def read_text(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return fallback


def supabase_table_count(table: str) -> int | None:
    """Return an exact row count when the service/anon key permits REST reads."""
    if not SUPABASE_KEY:
        return None
    url = f"{SUPABASE}/rest/v1/{table}?select=id&limit=1"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
            "Prefer": "count=exact",
            "User-Agent": "T.E.I./5.2",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            content_range = r.headers.get("Content-Range", "")
            if "/" not in content_range:
                return 0
            total = content_range.rsplit("/", 1)[1].strip()
            return int(total) if total.isdigit() else 0
    except Exception:
        return None


def supabase_counts() -> dict[str, int] | None:
    if not SUPABASE_KEY:
        return None
    counts: dict[str, int] = {}
    for table in ("source_files", "companies", "people", "evidence"):
        value = supabase_table_count(table)
        if value is None:
            return None
        counts[table] = value
    return counts


def core_company(uniform: str) -> dict:
    basic_rows = _company_filter(COMPANY_API, "Business_Accounting_NO", uniform, 1)
    if not basic_rows:
        return {
            "status": "not_found",
            "uniform_number": uniform,
            "company": {},
            "company_name": uniform,
            "people": [],
            "graph": {"nodes": [], "edges": []},
            "evidence": [],
            "evidence_count": 0,
            "local_context": {"configured": False, "evidence": [], "evidence_count": 0},
            "evidence_status": {},
            "data_mode": "live_moea_core",
        }

    basic = basic_rows[0]
    name = basic.get("Company_Name") or basic.get("Juristic_Person_Name") or uniform
    website_url, website_host = _website_from_company(basic)

    try:
        director_rows = _company_filter(DIRECTOR_API, "Business_Accounting_NO", uniform, 1000)
        director_error = None
    except Exception as exc:
        director_rows = []
        director_error = f"董監事來源暫時不可用：{type(exc).__name__}: {exc}"

    people = []
    nodes = [{
        "id": f"company:{uniform}",
        "type": "company",
        "label": name,
        "properties": {
            "uniform_number": uniform,
            "source": "經濟部商工行政資料開放平台",
        },
    }]
    edges = []
    for idx, row in enumerate(director_rows[:50], 1):
        person = row.get("Person_Name") or row.get("person_name") or row.get("Name")
        if not person:
            continue
        position = row.get("Person_Position_Name") or row.get("position") or row.get("Position") or "董監事"
        shares = row.get("Person_Shareholding") or row.get("shares")
        people.append({
            "uniform_number": uniform,
            "company_name": name,
            "person_name": person,
            "position": position,
            "shares": shares,
        })
        pid = f"person:{person}:{idx}"
        nodes.append({
            "id": pid,
            "type": "person",
            "label": person,
            "properties": {
                "position": position,
                "shares": shares,
                "source": "經濟部公司登記董監事資料",
            },
        })
        edges.append({
            "source": f"company:{uniform}",
            "target": pid,
            "relationship": position,
            "properties": {"source": "MOEA_DIRECTOR_API", "live": True},
        })

    try:
        local = _local_context(uniform)
    except Exception as exc:
        local = {
            "configured": False,
            "company": None,
            "evidence": [],
            "evidence_count": 0,
            "error": f"Supabase evidence unavailable: {type(exc).__name__}: {exc}",
        }

    status = {
        "公司登記": {"status": "ok", "matched": 1},
        "董監事": {
            "status": "ok" if director_rows else ("partial" if director_error else "ok"),
            "matched": len(people),
            **({"message": director_error} if director_error else {}),
        },
        "裁罰": {
            "status": "not_available_in_public_runtime",
            "matched": 0,
            "message": "請使用 Supabase T.E.I. console 取得即時公開裁罰資料。",
        },
        "165": {
            "status": "not_available_in_public_runtime",
            "matched": 0,
            "message": "請使用 Supabase T.E.I. console 取得即時反詐資料。",
        },
        "標案": {
            "status": "not_available_in_public_runtime",
            "matched": 0,
            "message": "請使用 Supabase T.E.I. console 取得即時標案資料。",
        },
        "裁判書": {
            "status": "link",
            "matched": 0,
            "message": "官方裁判書查詢入口",
        },
        "我的資料": {
            "status": "ok" if local.get("configured") else "not_configured",
            "matched": int(local.get("evidence_count") or 0),
        },
    }

    return {
        "status": "ok",
        "uniform_number": uniform,
        "company": basic,
        "company_name": name,
        "website_url": website_url,
        "website_host": website_host,
        "people": people,
        "graph": {"nodes": nodes, "edges": edges},
        "evidence": list(local.get("evidence") or []),
        "evidence_count": int(local.get("evidence_count") or 0),
        "local_context": local,
        "evidence_status": status,
        "website_crosscheck": {
            "status": "not_available_in_public_runtime",
            "matched": 0,
            "website_url": website_url,
            "website_host": website_host,
            "records": [],
            "message": "網址×165 交叉比對由 Supabase T.E.I. console 執行。",
        },
        "judicial_search_url": "https://judgment.judicial.gov.tw/FJUD/qryresult.aspx?kw={}&judtype=JUDBOOK".format(__import__("urllib.parse", fromlist=["quote_plus"]).quote_plus(name)),
        "data_mode": "live_moea_core_plus_supabase",
        "evidence_note": "Vercel 路由只保證核心 MOEA 公司/董監事資料；慢速證據來源由 Supabase console 分流。",
    }


def source_aggregation(uniform: str) -> dict:
    data = core_company(uniform)
    return {
        "status": data.get("status", "ok"),
        "uniform_number": uniform,
        "company_name": data.get("company_name"),
        "website": {
            "url": data.get("website_url"),
            "host": data.get("website_host"),
        },
        "labor": data.get("evidence_status", {}).get("裁罰", {}),
        "anti_fraud": data.get("website_crosscheck", {}),
        "sources": data.get("evidence_status", {}),
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload, content_type: str = "application/json; charset=utf-8"):
        body = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type, authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            html = read_text(WEB / "index.html")
            return self._send(200, html, "text/html; charset=utf-8") if html else self._send(500, {"error": "web/index.html not found"})
        if path == "/app.js":
            js = read_text(WEB / "app.js")
            return self._send(200, js, "application/javascript; charset=utf-8") if js else self._send(404, "app.js not found", "text/plain; charset=utf-8")
        if path == "/tei-enhancements.js":
            js = read_text(WEB / "tei-enhancements.js")
            return self._send(200, js, "application/javascript; charset=utf-8")

        if path == "/api/status":
            counts = supabase_counts()
            payload = {
                "status": "ok",
                "version": "5.2-core-isolated",
                "supabase": {"configured": bool(SUPABASE_KEY)},
                "routes": ["/api/status", "/api/company/{uniform}", "/api/company-sources"],
                "source_mode": "MOEA core on Vercel; optional evidence on Supabase",
            }
            if counts is not None:
                payload["supabase"].update(counts)
            return self._send(200, payload)

        if path.startswith("/api/company/"):
            uniform = unquote(path.split("/api/company/", 1)[1]).strip()
            if not (uniform.isdigit() and len(uniform) == 8):
                return self._send(400, {"error": "統編必須是 8 碼數字。"})
            try:
                return self._send(200, core_company(uniform))
            except Exception as exc:
                return self._send(502, {"status": "error", "error": f"核心公開資料暫時不可用：{type(exc).__name__}: {exc}"})

        if path == "/api/company-sources":
            qs = parse_qs(parsed.query)
            uniform = str((qs.get("uniform") or [""])[0]).strip()
            if not (uniform.isdigit() and len(uniform) == 8):
                return self._send(400, {"error": "uniform must be 8 digits"})
            try:
                return self._send(200, source_aggregation(uniform))
            except Exception as exc:
                return self._send(502, {"status": "error", "error": f"來源聚合暫時不可用：{type(exc).__name__}: {exc}"})

        return self._send(404, {"error": "Not found"})

    def log_message(self, fmt, *args):
        return


handler = Handler
