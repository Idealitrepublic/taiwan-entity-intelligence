"""T.E.I. live smoke-test endpoint.

Serves /api/test as a small diagnostics page and /api/test?format=json as
machine-readable smoke-test results. It calls the same production gateway
functions used by the UI, so this tests real API reachability rather than
mock data. Secrets are never included in the response.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from src.v2server import build_company, SUPABASE_KEY

# Publicly documented 2026 criminal judgment test target. The company was a
# defendant in a first-instance National Security Act case; the test page
# describes it as a known judicial test case, not as a generic "bad company" label.
TEST_UNIFORM = "96972256"  # 東京威力科創股份有限公司
TEST_NAME = "東京威力科創股份有限公司"


def run_tests():
    result = {
        "test_target": TEST_UNIFORM,
        "test_target_name": TEST_NAME,
        "core": {},
        "sources": {},
        "summary": {"passed": 0, "failed": 0, "warning": 0},
    }

    try:
        data = build_company(TEST_UNIFORM)
        company = data.get("company") or {}
        people = data.get("people") or []
        local = data.get("local_context") or {}
        statuses = data.get("evidence_status") or {}

        company_ok = bool(data.get("company_name")) and bool(company)
        directors_ok = isinstance(people, list) and len(people) > 0
        supabase_configured = bool(local.get("configured"))
        supabase_ok = supabase_configured and local.get("error") is None

        checks = [
            ("MOEA 公司 API", company_ok, "已取得公司基本資料" if company_ok else "未取得公司基本資料"),
            ("MOEA 董監事 API", directors_ok, f"取得 {len(people)} 位董監事" if directors_ok else "未取得董監事"),
            ("Supabase 資料庫", supabase_ok, "REST 讀取正常" if supabase_ok else (local.get("error") or "Supabase key 未設定")),
        ]
        for name, ok, detail in checks:
            result["core"][name] = {"status": "pass" if ok else "fail", "detail": detail}
            result["summary"]["passed" if ok else "failed"] += 1

        for name, item in statuses.items():
            if not isinstance(item, dict):
                item = {"status": str(item)}
            status = item.get("status", "unknown")
            matched = int(item.get("matched") or 0)
            if status == "ok":
                level = "pass"
                result["summary"]["passed"] += 1
            elif status in ("partial", "link", "adapter"):
                level = "warning"
                result["summary"]["warning"] += 1
            else:
                level = "warning"
                result["summary"]["warning"] += 1
            result["sources"][name] = {
                "status": level,
                "source_status": status,
                "matched": matched,
                "message": item.get("message"),
                "url": item.get("url"),
            }

        result["company"] = {
            "name": data.get("company_name"),
            "uniform_number": TEST_UNIFORM,
            "director_count": len(people),
            "live_evidence_count": len(data.get("evidence") or []),
            "local_evidence_count": int(local.get("evidence_count") or 0),
        }
        result["judicial_search_url"] = data.get("judicial_search_url")
        result["data_mode"] = data.get("data_mode")

    except Exception as exc:
        result["core"]["Gateway"] = {"status": "fail", "detail": f"{type(exc).__name__}: {exc}"}
        result["summary"]["failed"] += 1

    result["supabase_key_configured"] = bool(SUPABASE_KEY)
    result["overall"] = "PASS" if result["summary"]["failed"] == 0 else "FAIL"
    return result


HTML = """<!doctype html>
<html lang="zh-Hant">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>T.E.I. Smoke Test</title>
<style>
body{margin:0;background:#080b10;color:#edf2f7;font-family:system-ui,-apple-system,"Noto Sans TC",sans-serif;padding:28px}
main{max-width:900px;margin:auto}.box{border:1px solid #26313e;background:#0d131b;border-radius:12px;padding:18px;margin:12px 0}
h1{font-size:22px;margin:0 0 6px}.muted{color:#7f8c9c;font-size:12px}.row{display:flex;justify-content:space-between;gap:16px;padding:11px 0;border-bottom:1px solid #1c2631;font-size:13px}.row:last-child{border-bottom:0}.pass{color:#63d39f}.fail{color:#ef7d8d}.warning{color:#f2c56a}.pill{display:inline-block;padding:5px 8px;border:1px solid #344152;border-radius:999px;font-size:11px}.summary{display:flex;gap:18px;flex-wrap:wrap}.big{font-size:32px;font-weight:800}.btn{border:1px solid #526f96;background:#dfeafb;color:#0d1520;border-radius:7px;padding:8px 12px;font-weight:700;cursor:pointer}.pre{white-space:pre-wrap;word-break:break-word;color:#9eabb9;font-size:11px;line-height:1.6}
</style></head>
<body><main>
<div class="box"><h1>T.E.I. Live Smoke Test</h1><div class="muted">實際呼叫 Production gateway；不是 mock。測試目標：96972256 東京威力科創股份有限公司</div><div id="summary" class="summary" style="margin-top:14px"></div></div>
<div class="box"><h2>核心連線</h2><div id="core"></div></div>
<div class="box"><h2>來源狀態</h2><div id="sources"></div></div>
<div class="box"><h2>測試企業</h2><div id="company"></div></div>
<div class="box"><h2>原始測試 JSON</h2><div id="raw" class="pre"></div></div>
<script>
const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
async function run(){
  const r=await fetch('/api/test?format=json&t='+Date.now());
  const x=await r.json();
  document.title='T.E.I. Smoke Test — '+x.overall;
  document.getElementById('summary').innerHTML=`<div><div class='big ${x.overall==='PASS'?'pass':'fail'}'>${esc(x.overall)}</div><div class='muted'>overall</div></div><div><div class='big'>${x.summary.passed}</div><div class='muted'>passed</div></div><div><div class='big'>${x.summary.failed}</div><div class='muted'>failed</div></div><div><div class='big'>${x.summary.warning}</div><div class='muted'>warnings</div></div>`;
  const render=(obj)=>Object.entries(obj).map(([k,v])=>`<div class='row'><span>${esc(k)}</span><span class='${v.status}'>${esc(v.status.toUpperCase())}${v.detail?' · '+esc(v.detail):v.message?' · '+esc(v.message):''}</span></div>`).join('');
  document.getElementById('core').innerHTML=render(x.core)||'<div class="muted">無資料</div>';
  document.getElementById('sources').innerHTML=render(x.sources)||'<div class="muted">無資料</div>';
  const c=x.company||{}; document.getElementById('company').innerHTML=`<div class='row'><span>公司</span><span>${esc(c.name||'—')}</span></div><div class='row'><span>統編</span><span>${esc(c.uniform_number||'—')}</span></div><div class='row'><span>董監事</span><span>${esc(c.director_count||0)} 人</span></div><div class='row'><span>Evidence</span><span>${esc(c.live_evidence_count||0)} 筆（即時/資料層）</span></div><div class='row'><span>Supabase Evidence</span><span>${esc(c.local_evidence_count||0)} 筆</span></div><div class='row'><span>司法院查詢</span><span><a href='${esc(x.judicial_search_url||'#')}' target='_blank' rel='noreferrer' style='color:#91baff'>官方查詢入口 ↗</a></span></div>`;
  document.getElementById('raw').textContent=JSON.stringify(x,null,2);
}
run().catch(e=>document.getElementById('raw').textContent=String(e));
</script></main></body></html>"""


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
