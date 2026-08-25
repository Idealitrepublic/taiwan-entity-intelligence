"""Tiny standard-library web server for the MVP."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from .company import get_company
from .db import connect
from .graph import company_graph
from .live_graph import live_company_graph
from .public_evidence import collect_public_evidence
from .repository import company_people, company_tenders

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")


def _tender_evidence(company_name, tenders):
    rows = []
    for tender in tenders:
        tender_id = tender.get("tender_id") or tender.get("案號") or tender.get("標案編號") or tender.get("id")
        if not tender_id:
            continue
        title = tender.get("tender_name") or tender.get("標案名稱") or tender.get("案名") or str(tender_id)
        rows.append({
            "evidence_id": "procurement:{}".format(tender_id),
            "schema_version": "1.0",
            "source": {"type": "local_government_open_data", "name": "政府採購／本機標案資料", "record_id": str(tender_id)},
            "fact": {"type": "government_tender", "title": title,
                     "summary": "本機資料庫含有與公司名稱相符的政府採購紀錄；請回看原始標案確認得標、履約及時間脈絡。"},
            "confidence": 1.0,
            "status": "active",
            "raw": tender,
        })
    return rows


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
                basic = get_company(uniform_number)

                try:
                    conn = connect()
                except FileNotFoundError:
                    graph = live_company_graph(uniform_number)
                    people = [
                        {
                            "uniform_number": uniform_number,
                            "company_name": basic.get("Company_Name") if basic else uniform_number,
                            "position": node.get("properties", {}).get("position"),
                            "person_name": node.get("label"),
                            "shares": node.get("properties", {}).get("shares"),
                        }
                        for node in graph.get("nodes", [])
                        if node.get("type") == "person"
                    ]
                    company_name = (basic or {}).get("Company_Name") or uniform_number
                    public = collect_public_evidence(company_name, [p.get("person_name") for p in people])
                    if not basic and not graph.get("nodes"):
                        self._json(404, {"error": "找不到此統編。"})
                        return
                    self._json(200, {
                        "uniform_number": uniform_number,
                        "company": basic,
                        "company_name": company_name,
                        "people": people,
                        "graph": graph,
                        "data_mode": "live_government_open_data",
                        "evidence": public["evidence"],
                        "evidence_status": {"標案": "not_available_in_public_runtime", **public["statuses"]},
                        "evidence_note": public["note"],
                    })
                    return

                people = company_people(conn, uniform_number)
                if not basic and not people:
                    conn.close()
                    self._json(404, {"error": "找不到此統編。"})
                    return
                company_name = (basic or {}).get("Company_Name") or (people[0]["company_name"] if people else uniform_number)
                graph = company_graph(conn, uniform_number)
                tenders = company_tenders(conn, company_name)
                conn.close()
                public = collect_public_evidence(company_name, [p.get("person_name") for p in people])
                evidence = _tender_evidence(company_name, tenders) + public["evidence"]
                self._json(200, {
                    "uniform_number": uniform_number,
                    "company": basic,
                    "company_name": company_name,
                    "people": people,
                    "graph": graph,
                    "data_mode": "local_database",
                    "evidence": evidence,
                    "evidence_status": {"標案": "checked", **public["statuses"]},
                    "evidence_note": public["note"],
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
