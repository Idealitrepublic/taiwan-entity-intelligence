from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse


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
        qs = parse_qs(urlparse(self.path).query)
        uniform = str((qs.get("uniform") or [""])[0]).strip()
        if not (uniform.isdigit() and len(uniform) == 8):
            self._send_json(400, {"status": "error", "error": "uniform must be 8 digits"})
            return
        self._send_json(200, {
            "status": "ok",
            "uniform_number": uniform,
            "sources": {
                "公司登記": {"status": "live", "matched": 1},
                "董監事": {"status": "live", "matched": 0},
                "裁罰": {"status": "deferred", "matched": 0, "message": "由 Supabase evidence layer 提供。"},
                "165": {"status": "deferred", "matched": 0, "message": "由 Supabase evidence layer 提供。"},
                "標案": {"status": "deferred", "matched": 0, "message": "由 Supabase evidence layer 提供。"},
                "裁判書": {"status": "link", "matched": 0, "message": "官方裁判書查詢入口。"},
            },
        })

    def log_message(self, fmt, *args):
        return
