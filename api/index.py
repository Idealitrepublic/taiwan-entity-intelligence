"""Canonical Vercel entrypoint for T.E.I.

Routes:
- /                UI from web/index.html
- /app.js          browser application from web/app.js
- /tei-enhancements.js optional enhancement script
- /api/status      live system status
- /api/company/{uniform} company + directors + evidence
- /api/company-sources?uniform={uniform} source aggregation

The handler is deliberately defensive: an unavailable optional source must not
turn a valid company/director query into an HTTP 500.
"""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlparse
from http.server import BaseHTTPRequestHandler

from src.v2server import (
    SUPABASE,
    SUPABASE_KEY,
    _supabase_get,
    build_company,
)

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def read_text(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return fallback


def safe_build_company(uniform: str) -> dict:
    """Return a usable response even when an optional evidence adapter fails."""
    try:
        result = build_company(uniform)
        if not isinstance(result, dict):
            raise TypeError(f"build_company returned {type(result).__name__}")
        return result
    except Exception as exc:
        # Retry the core official company/director path only. This isolates the
        # UI from optional external-source failures and preserves traceability.
        from src.v2server import COMPANY_API, DIRECTOR_API, _company_filter, _local_context

        basic_rows = _company_filter(COMPANY_API, "Business_Accounting_NO", uniform, 1)
        basic = basic_rows[0] if basic_rows else {"Business_Accounting_NO": uniform}
        name = basic.get("Company_Name") or basic.get("Juristic_Person_Name") or uniform
        director_rows = _company_filter(DIRECTOR_API, "Business_Accounting_NO", uniform, 1000)

        people = []
        nodes = [{"id": f"company:{uniform}", "type": "company", "label": name, "properties": {"uniform_number": uniform}}]
        edges = []
        for idx, row in enumerate(director_rows[:50], 1):
            person = row.get("Person_Name") or row.get("person_name")
            if not person:
                continue
            position = row.get("Person_Position_Name") or row.get("position") or "董監事"
            pid = f"person:{person}:{idx}"
            people.append({"uniform_number": uniform, "company_name": name, "person_name": person, "position": position})
            nodes.append({"id": pid, "type": "person", "label": person, "properties": {"position": position}})
            edges.append({"source": f"company:{uniform}", "target": pid, "relationship": position})

        try:
            local = _local_context(uniform)
        except Exception as local_exc:
            local = {"configured": False, "company": None, "evidence": [], "evidence_count": 0,
                     "error": str(local_exc)}

        return {
            "uniform_number": uniform,
            "company": basic,
            "company_name": name,
            "website_url": None,
            "website_host": None,
            "people": people,
            "graph": {"nodes": nodes, "edges": edges},
            "evidence": list(local.get("evidence") or []),
            "evidence_count": len(local.get("evidence") or []),
            "local_context": local,
            "evidence_status": {
                "裁罰": {"status": "error", "matched": 0, "message": "選配公開來源暫時失敗；核心公司資料正常。"},
                "165": {"status": "error", "matched": 0, "message": "選配公開來源暫時失敗；核心公司資料正常。"},
                "標案": {"status": "error", "matched": 0, "message": "選配公開來源暫時失敗；核心公司資料正常。"},
                "裁判書": {"status": "link", "matched": 0, "message": "官方裁判書查詢入口"},
                "系統診斷": {"status": "partial", "matched": 0, "message": f"optional evidence exception: {type(exc).__name__}"},
            },
            "source_catalog": {},
            "website_crosscheck": {"status": "no_website", "matched": 0, "records": []},
            "data_mode": "core_moea_api_plus_supabase",
            "evidence_note": "公開來源僅供研究使用；讀取失敗不代表沒有公開紀錄。",
        }


def source_aggregation(uniform: str) -> dict:
    data = safe_build_company(uniform)
    statuses = data.get("evidence_status") or {}
    return {
        "status": "ok",
        "uniform_number": uniform,
        "company_name": data.get("company_name"),
        "website": {
            "url": data.get("website_url"),
            "host": data.get("website_host"),
        },
        "labor": statuses.get("裁罰") or {"status": "error", "matched": 0},
        "anti_fraud": statuses.get("公司網址×165") or data.get("website_crosscheck") or {"status": "no_website", "matched": 0},
        "sources": statuses,
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
            if not html:
                return self._send(500, {"error": "web/index.html not found"})
            return self._send(200, html, "text/html; charset=utf-8")

        if path == "/app.js":
            js = read_text(WEB / "app.js")
            if not js:
                return self._send(404, "app.js not found", "text/plain; charset=utf-8")
            return self._send(200, js, "application/javascript; charset=utf-8")

        if path == "/tei-enhancements.js":
            js = read_text(WEB / "tei-enhancements.js")
            if not js:
                return self._send(404, "", "application/javascript; charset=utf-8")
            return self._send(200, js, "application/javascript; charset=utf-8")

        if path == "/api/status":
            counts = {}
            for table in ("source_files", "companies", "people", "evidence"):
                rows, state = _supabase_get(table, limit=1)
                if state == "ok":
                    # A cheap count endpoint is not guaranteed by all schemas;
                    # expose connectivity separately and avoid inventing totals.
                    counts[table] = "reachable"
                else:
                    counts[table] = "unavailable"
            return self._send(200, {
                "status": "ok",
                "version": "5.0-canonical-router",
                "supabase": {"configured": bool(SUPABASE_KEY), **counts},
                "routes": ["/api/status", "/api/company/{uniform}", "/api/company-sources"],
            })

        if path.startswith("/api/company/"):
            uniform = unquote(path.split("/api/company/", 1)[1]).strip()
            if not (uniform.isdigit() and len(uniform) == 8):
                return self._send(400, {"error": "統編必須是 8 碼數字。"})
            try:
                return self._send(200, safe_build_company(uniform))
            except Exception as exc:
                return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

        if path == "/api/company-sources":
            qs = __import__("urllib.parse", fromlist=["parse_qs"]).parse_qs(parsed.query)
            uniform = str((qs.get("uniform") or [""])[0]).strip()
            if not (uniform.isdigit() and len(uniform) == 8):
                return self._send(400, {"error": "uniform must be 8 digits"})
            return self._send(200, source_aggregation(uniform))

        return self._send(404, {"error": "Not found"})

    def log_message(self, fmt, *args):
        return


handler = Handler
