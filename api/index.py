"""Vercel entry point with the T.E.I. live gateway and Judicial API proxy."""

import json
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import parse_qs, urlparse

from src.app_js import APP_JS
from src.v2server import Handler as BaseHandler, SUPABASE_KEY, build_company

TEST_UNIFORM = "96972256"
TEST_NAME = "東京威力科創股份有限公司"
TEST_JID = "CHDM,105,交訴,51,20161216,1"
JUDICIAL_EDGE = "https://rztdbdurkjfrirsrrhtu.supabase.co/functions/v1/judicial-api"


def _judicial_request(jid=None):
    if not SUPABASE_KEY:
        return 503, {"status": "not_configured", "error": "Supabase key not configured"}
    params = {}
    if jid:
        params["jid"] = jid
    url = JUDICIAL_EDGE
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "apikey": SUPABASE_KEY,
            "Accept": "application/json",
            "User-Agent": "T.E.I./3.3",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=50) as r:
            body = r.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
            except Exception:
                data = {"status": "error", "error": body[:1200]}
            return r.status, data
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body)
        except Exception:
            data = {"status": "error", "error": body[:1200]}
        return exc.code, data
    except Exception as exc:
        return 502, {"status": "error", "error": str(exc)}


def _judicial_health():
    status, data = _judicial_request()
    if status != 200:
        return status, {"status": data.get("status", "error"), "http_status": status, "detail": data}
    payload = data.get("data", data)
    if isinstance(payload, list):
        count = len(payload)
    elif isinstance(payload, dict):
        count = len(payload.get("data") or payload.get("records") or payload.get("items") or payload.get("result") or [])
    else:
        count = 0
    return 200, {
        "status": "ok",
        "auth_and_jlist": "ok",
        "recent_change_count": count,
        "message": "司法院 Auth/JList 可正常呼叫。",
    }


def smoke_result():
    result = {
        "overall": "FAIL",
        "test_target": TEST_UNIFORM,
        "test_target_name": TEST_NAME,
        "checks": {},
        "summary": {"passed": 0, "failed": 0, "warning": 0},
    }
    try:
        data = build_company(TEST_UNIFORM)
        company = data.get("company") or {}
        people = data.get("people") or []
        local = data.get("local_context") or {}

        checks = [
            ("MOEA 公司 API", bool(data.get("company_name")) and bool(company), "公司基本資料可取得"),
            ("MOEA 董監事 API", isinstance(people, list) and len(people) > 0, f"取得 {len(people)} 位董監事"),
            ("Supabase 資料庫", bool(local.get("configured")) and local.get("error") is None, "REST 讀取正常"),
        ]
        for name, ok, detail in checks:
            result["checks"][name] = {"status": "PASS" if ok else "FAIL", "detail": detail}
            result["summary"]["passed" if ok else "failed"] += 1

        jstatus, jhealth = _judicial_health()
        jok = jstatus == 200 and jhealth.get("status") == "ok"
        result["checks"]["司法院 Auth/JList API"] = {
            "status": "PASS" if jok else "FAIL",
            "detail": jhealth.get("message") or jhealth.get("detail") or "",
            "recent_change_count": jhealth.get("recent_change_count", 0),
        }
        result["summary"]["passed" if jok else "failed"] += 1

        jdstatus, jd = _judicial_request(TEST_JID)
        jdoc_payload = jd.get("data", jd) if isinstance(jd, dict) else jd
        jdoc_ok = jdstatus == 200 and isinstance(jdoc_payload, dict) and bool(jdoc_payload.get("JID") or jdoc_payload.get("JFULLX") or jdoc_payload.get("JTITLE"))
        result["checks"]["司法院 JDoc API"] = {
            "status": "PASS" if jdoc_ok else "WARN",
            "detail": "可取得測試 JID 的裁判書內容。" if jdoc_ok else (jd.get("error") if isinstance(jd, dict) else "JDoc 未取得可驗證內容"),
            "test_jid": TEST_JID,
        }
        result["summary"]["passed" if jdoc_ok else "warning"] += 1

        result["company"] = {
            "name": data.get("company_name"),
            "uniform_number": TEST_UNIFORM,
            "director_count": len(people),
            "supabase_evidence": int(local.get("evidence_count") or 0),
            "evidence_count": len(data.get("evidence") or []),
        }
        result["supabase_key_configured"] = bool(SUPABASE_KEY)
        result["overall"] = "PASS" if result["summary"]["failed"] == 0 else "FAIL"
    except Exception as exc:
        result["checks"]["Gateway"] = {"status": "FAIL", "detail": f"{type(exc).__name__}: {exc}"}
        result["summary"]["failed"] += 1
    return result


HTML = """<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>T.E.I. Live Smoke Test</title><style>body{margin:0;background:#080b10;color:#edf2f7;font-family:system-ui,-apple-system,'Noto Sans TC',sans-serif;padding:28px}main{max-width:900px;margin:auto}.box{border:1px solid #26313e;background:#0d131b;border-radius:12px;padding:18px;margin:12px 0}.row{display:flex;justify-content:space-between;gap:16px;padding:10px 0;border-bottom:1px solid #1c2631;font-size:13px}.pass{color:#63d39f}.fail{color:#ef7d8d}.warn{color:#f2c56a}.muted{color:#7f8c9c;font-size:12px}.big{font-size:34px;font-weight:800}</style></head><body><main><div class='box'><h1>T.E.I. Live Smoke Test</h1><div class='muted'>Production 實測；統編 96972256｜東京威力科創股份有限公司</div><div id='summary'></div></div><div class='box'><h2>連線測試</h2><div id='checks'></div></div><div class='box'><h2>測試企業</h2><div id='company'></div></div><script>const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));async function run(){const r=await fetch('/api?format=json&t='+Date.now());const x=await r.json();document.getElementById('summary').innerHTML=`<div class='big ${x.overall==='PASS'?'pass':'fail'}'>${x.overall}</div><div class='muted'>PASS ${x.summary.passed} · FAIL ${x.summary.failed} · WARN ${x.summary.warning}</div>`;document.getElementById('checks').innerHTML=Object.entries(x.checks).map(([k,v])=>`<div class='row'><span>${esc(k)}</span><span class='${v.status==='PASS'?'pass':v.status==='FAIL'?'fail':'warn'}'>${esc(v.status)}${v.detail?' · '+esc(v.detail):''}</span></div>`).join('');const c=x.company||{};document.getElementById('company').innerHTML=`<div class='row'><span>公司</span><span>${esc(c.name||'—')}</span></div><div class='row'><span>統編</span><span>${esc(c.uniform_number||'—')}</span></div><div class='row'><span>董監事</span><span>${esc(c.director_count||0)} 人</span></div><div class='row'><span>Supabase Evidence</span><span>${esc(c.supabase_evidence||0)} 筆</span></div>`}run().catch(e=>document.body.insertAdjacentHTML('beforeend','<pre>'+esc(e)+'</pre>'));</script></main></body></html>"""


class Handler(BaseHandler):
    def _send_raw(self, status, body, ctype):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        query = parse_qs(urlparse(self.path).query)
        if path == "/app.js":
            return self._send_raw(200, APP_JS, "application/javascript; charset=utf-8")
        if path == "/api" and query.get("format") == ["json"]:
            return self._send_raw(200, json.dumps(smoke_result(), ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/api":
            return self._send_raw(200, HTML, "text/html; charset=utf-8")
        if path == "/api/judicial/health":
            status, payload = _judicial_health()
            return self._send_raw(status, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/api/judicial":
            jid = (query.get("jid") or [None])[0]
            status, payload = _judicial_request(jid)
            return self._send_raw(status, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")
        return super().do_GET()


handler = Handler
