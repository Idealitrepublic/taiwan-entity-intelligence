"""Tiny standard-library web server for the MVP."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from .db import connect
from .graph import company_graph
from .repository import company_people

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")


class Handler(BaseHTTPRequestHandler):
    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            path = os.path.join(WEB, "index.html")
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        prefix = "/api/company/"
        if parsed.path.startswith(prefix):
            uniform_number = unquote(parsed.path[len(prefix):])
            if not uniform_number.isdigit():
                self._json(400, {"error": "統編必須是純數字。"})
                return
            try:
                conn = connect()
                people = company_people(conn, uniform_number)
                if not people:
                    conn.close()
                    self._json(404, {"error": "找不到此統編的本機公司資料。"})
                    return
                graph = company_graph(conn, uniform_number)
                conn.close()
                self._json(200, {
                    "uniform_number": uniform_number,
                    "company_name": people[0]["company_name"],
                    "graph": graph,
                })
            except Exception as exc:
                self._json(500, {"error": str(exc)})
            return

        self.send_response(404)
        self.end_headers()


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print("Taiwan Entity Intelligence: http://{}:{}/".format(host, port))
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
