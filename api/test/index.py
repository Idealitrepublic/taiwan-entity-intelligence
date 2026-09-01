"""T.E.I. smoke test endpoint.

Exposes /api/test using a nested Vercel Python function path.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from src.v2server import SUPABASE_KEY, build_company

TEST_UNIFORM = "22099131"


def run_tests():
    out = {"overall": "FAIL", "summary": {"passed": 0, "failed": 0, "warning": 0}, "checks": {}, "company": {}, "supabase_key_configured": bool(SUPABASE_KEY)}
    try:
        data = build_company(TEST_UNIFORM)
        company = data.get("company") or {}
        people = data.get("people") or []
        local = data.get("local_context") or {}
        statuses = data.get("evidence_status") or {}

        checks = [
            ("MOEA 公司 API", bool(data.get("company_name")) and bool(company), "公司基本資料可取得"),
            ("MOEA 董監事 API", isinstance(people, list) and len(people) > 0, f"取得 {len(people)} 位董監事"),
            ("Supabase", bool(local.get("configured")) and local.get("error") is None, "REST 讀取正常"),
        ]
        for name, ok, detail in checks:
            out["checks"][name] = {"status": "PASS" if ok else "FAIL", "detail": detail}
            out["summary"]["passed" if ok else "failed"] += 1

        for name, item in statuses.items():
            st = item.get("status", "unknown") if isinstance(item, dict) else str(item)
            if st == "ok":
                level = "PASS"; out["summary"]["passed"] += 1
            else:
                level = "WARN"; out["summary"]["warning"] += 1
            out["checks"][name] = {
                "status": level,
                "detail": (item.get("message") if isinstance(item, dict) else None) or f"status={st}",
                "matched": (item.get("matched") if isinstance(item, dict) else 0) or 0,
            }

        out["company"] = {
            "name": data.get("company_name"),
            "uniform_number": TEST_UNIFORM,
            "director_count": len(people),
            "local_evidence_count": int(local.get("evidence_count") or 0),
            "evidence_count": len(data.get("evidence") or []),
        }
        out["overall"] = "PASS" if out["summary"]["failed"] == 0 else "FAIL"
    except Exception as exc:
        out["checks"]["Gateway"] = {"status": "FAIL", "detail": f"{type(exc).__name__}: {exc}"}
        out["summary"]["failed"] += 1
        out["overall"] = "FAIL"
    return out


HTML = """<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>T.E.I. Smoke Test</title><style>body{margin:0;background:#080b10;color:#edf2f7;font-family:system-ui,-apple-system,'Noto Sans TC',sans-serif;padding:28px}main{max-width:900px;margin:auto}.box{border:1px solid #26313e;background:#0d131b;border-radius:12px;padding:18px;margin:12px 0}.row{display:flex;justify-content:space-between;gap:18px;padding:10px 0;border-bottom:1px solid #1c2631;font-size:13px}.row:last-child{border-bottom:0}.pass{color:#63d39f}.fail{color:#ef7d8d}.warn{color:#f2c56a}.muted{color:#7f8c9c;font-size:12px}.big{font-size:34px;font-weight:800}</style></head><body><main><div class='box'><h1>T.E.I. Live Smoke Test</h1><div class='muted'>實際呼叫 Production gateway；不是 mock。測試統編 22099131</div><div id='summary'></div></div><div class='box'><h2>連線與資料源</h2><div id='checks'></div></div><div class='box'><h2>測試企業</h2><div id='company'></div></div><script>const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));async function run(){const r=await fetch('/api/test?format=json&t='+Date.now());const x=await r.json();document.getElementById('summary').innerHTML=`<div class='big ${x.overall==='PASS'?'pass':'fail'}'>${esc(x.overall)}</div><div class='muted'>PASS ${x.summary.passed} · FAIL ${x.summary.failed} · WARN ${x.summary.warning}</div>`;document.getElementById('checks').innerHTML=Object.entries(x.checks).map(([k,v])=>`<div class='row'><span>${esc(k)}</span><span class='${v.status==='PASS'?'pass':v.status==='FAIL'?'fail':'warn'}'>${esc(v.status)}${v.detail?' · '+esc(v.detail):''}${v.matched!==undefined?' · '+v.matched+' 筆':''}</span></div>`).join('');const c=x.company||{};document.getElementById('company').innerHTML=`<div class='row'><span>公司</span><span>${esc(c.name||'—')}</span></div><div class='row'><span>統編</span><span>${esc(c.uniform_number||'—')}</span></div><div class='row'><span>董監事</span><span>${esc(c.director_count||0)} 人</span></div><div class='row'><span>Supabase evidence</span><span>${esc(c.local_evidence_count||0)} 筆</span></div><div class='row'><span>總 evidence</span><span>${esc(c.evidence_count||0)} 筆</span></div>`}run().catch(e=>document.body.insertAdjacentHTML('beforeend','<pre>'+esc(e)+'</pre>'));</script></main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, ctype):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if parse_qs(urlparse(self.path).query).get("format") == ["json"]:
            return self._send(200, json.dumps(run_tests(), ensure_ascii=False), "application/json; charset=utf-8")
        return self._send(200, HTML, "text/html; charset=utf-8")

    def log_message(self, fmt, *args):
        return


handler = Handler
