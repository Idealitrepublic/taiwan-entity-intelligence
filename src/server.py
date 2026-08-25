"""Standard-library web server for the investigation workspace."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote_plus, unquote, urlparse

from .company import get_company
from .db import connect
from .graph import company_graph
from .live_graph import live_company_graph
from .public_evidence import collect_public_evidence
from .repository import company_people, company_tenders

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
JUDICIAL_SEARCH = "https://judgment.judicial.gov.tw/LAW_Mobile_FJUD/FJUD/qryresult.aspx?judtype=JUDBOOK&kw={}"


def _tender_evidence(tenders):
    rows = []
    for tender in tenders:
        tender_id = tender.get("tender_id") or tender.get("案號") or tender.get("標案編號") or tender.get("id")
        if not tender_id:
            continue
        title = tender.get("tender_name") or tender.get("標案名稱") or tender.get("案名") or str(tender_id)
        rows.append({
            "evidence_id": "procurement:{}".format(tender_id),
            "schema_version": "1.0",
            "source": {"type": "government_open_data", "name": "政府採購／本機標案資料", "record_id": str(tender_id)},
            "fact": {"type": "government_tender", "title": title,
                     "summary": "本機資料庫含有政府採購紀錄；請回看原始標案確認得標、履約及時間脈絡。"},
            "confidence": 1.0,
            "status": "active",
            "raw": tender,
        })
    return rows


def _judicial_link(company_name):
    return JUDICIAL_SEARCH.format(quote_plus(company_name))


def _decorate_evidence(evidence, company_name, people, uniform_number):
    company_norm = str(company_name or "").replace(" ", "").casefold()
    person_norm = [(str(p or "").replace(" ", "").casefold(), p) for p in people if p]
    for item in evidence:
        hay = json.dumps(item.get("raw") or item, ensure_ascii=False).replace(" ", "").casefold()
        if company_norm and company_norm in hay:
            item["entity_id"] = "company:{}".format(uniform_number)
            item["entity_type"] = "company"
        else:
            for norm, name in person_norm:
                if len(norm) >= 2 and norm in hay:
                    item["entity_id"] = "person:{}".format(name)
                    item["entity_type"] = "person"
                    break
        item.setdefault("entity_id", "company:{}".format(uniform_number))
        item.setdefault("entity_type", "company")
    return evidence


def _response(uniform_number, basic, company_name, people, graph, evidence, statuses, mode):
    source_counts = {}
    for item in evidence:
        name = item.get("source", {}).get("name", "其他")
        source_counts[name] = source_counts.get(name, 0) + 1
    return {
        "uniform_number": uniform_number,
        "company": basic,
        "company_name": company_name,
        "people": people,
        "graph": graph,
        "data_mode": mode,
        "evidence": evidence,
        "evidence_count": len(evidence),
        "evidence_sources": source_counts,
        "evidence_status": statuses,
        "judicial_search_url": _judicial_link(company_name),
        "evidence_note": "公開紀錄命中僅表示來源資料存在名稱／觀測值相符，不代表該實體已被認定違法或涉詐；同名人物仍需人工核對。",
    }


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
            if not uniform_number.isdigit() or len(uniform_number) != 8:
                self._json(400, {"error": "統編必須是 8 碼數字。"})
                return
            try:
                basic = get_company(uniform_number)
                try:
                    conn = connect()
                except FileNotFoundError:
                    graph = live_company_graph(uniform_number)
                    people = [{
                        "uniform_number": uniform_number,
                        "company_name": (basic or {}).get("Company_Name") or uniform_number,
                        "position": node.get("properties", {}).get("position"),
                        "person_name": node.get("label"),
                        "shares": node.get("properties", {}).get("shares"),
                    } for node in graph.get("nodes", []) if node.get("type") == "person"]
                    company_name = (basic or {}).get("Company_Name") or uniform_number
                    public = collect_public_evidence(company_name, [p.get("person_name") for p in people])
                    evidence = _decorate_evidence(public["evidence"], company_name, [p.get("person_name") for p in people], uniform_number)
                    statuses = {"標案": "not_available_in_public_runtime", **public["statuses"]}
                    if not basic and not graph.get("nodes"):
                        self._json(404, {"error": "找不到此統編。"})
                        return
                    self._json(200, _response(uniform_number, basic, company_name, people, graph, evidence, statuses, "live_government_open_data"))
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
                evidence = _decorate_evidence(_tender_evidence(tenders) + public["evidence"], company_name, [p.get("person_name") for p in people], uniform_number)
                statuses = {"標案": "checked", **public["statuses"]}
                self._json(200, _response(uniform_number, basic, company_name, people, graph, evidence, statuses, "local_database"))
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
