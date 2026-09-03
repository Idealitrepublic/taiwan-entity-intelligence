from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler


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
        configured = bool(
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_ANON_KEY")
            or os.environ.get("VITE_SUPABASE_ANON_KEY")
        )
        self._send_json(
            200,
            {
                "status": "ok",
                "version": "7.0-class-handler",
                "supabase": {"configured": configured},
                "routes": ["/api/status", "/api/company/{uniform}", "/api/company-sources"],
                "source_mode": "MOEA core on Vercel; optional evidence on Supabase",
            },
        )

    def log_message(self, fmt, *args):
        return
