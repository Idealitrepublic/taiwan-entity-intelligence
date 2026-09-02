"""Vercel entry point for T.E.I. production UI and diagnostics."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from src.app_js import APP_JS
from src.v2server import SUPABASE_KEY, build_company

TEST_UNIFORM = "96972256"
TEST_NAME = "東京威力科創股份有限公司"
JUDICIAL_EDGE = "https://rztdbdurkjfrirsrrhtu.supabase.co/functions/v1/judicial-api"

HTML = """<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>T.E.I.｜Taiwan Entity Intelligence</title><style>
:root{--bg:#070a0f;--panel:#0d131b;--line:#26313e;--text:#edf2f7;--muted:#7f8c9c;--blue:#7fb0ff;--green:#63d39f;--amber:#f2c56a;--red:#ef7d8d}*{box-sizing:border-box}html,body{margin:0;height:100%;font-family:Inter,system-ui,-apple-system,"Noto Sans TC",sans-serif;background:var(--bg);color:var(--text)}button,input{font:inherit}button{cursor:pointer}.app{min-height:100vh;display:grid;grid-template-rows:64px 86px 1fr}.top{display:flex;align-items:center;justify-content:space-between;padding:0 22px;border-bottom:1px solid var(--line);background:#080c12}.brand{display:flex;align-items:center;gap:12px}.logo{width:32px;height:32px;border:1px solid #456387;border-radius:9px;background:#0f1b29;position:relative}.logo:before{content:"";position:absolute;width:7px;height:7px;border-radius:50%;left:6px;top:12px;background:var(--blue);box-shadow:12px -7px 0 var(--green),14px 8px 0 var(--amber)}.brand h1{font-size:16px;margin:0}.brand p{margin:2px 0 0;color:#708093;font-size:9px;letter-spacing:1.3px}.status{font-size:10px;color:var(--green);border:1px solid #24563f;background:#0a1711;border-radius:999px;padding:7px 11px}.status.off{color:var(--amber);border-color:#5c4b24;background:#171207}.search{display:flex;align-items:center;gap:10px;padding:15px 22px;border-bottom:1px solid var(--line);background:#0a0e14}.searchbox{display:flex;gap:8px;max-width:880px;flex:1}.searchbox input{width:100%;height:46px;border:1px solid #334151;border-radius:8px;background:#111821;color:var(--text);padding:0 14px;outline:none}.primary{height:46px;padding:0 18px;border:1px solid #7597c4;border-radius:8px;background:#dfeafb;color:#0e1620;font-weight:750}.secondary{height:46px;padding:0 12px;border:1px solid #344152;border-radius:7px;background:#101720;color:#bdc8d5}.searchmeta{margin-left:auto;color:#687687;font-size:10px;text-align:right;line-height:1.6}.main{display:grid;grid-template-columns:290px minmax(0,1fr) 360px;min-height:0}.panel{background:var(--panel);overflow:auto}.left{border-right:1px solid var(--line)}.right{border-left:1px solid var(--line)}.section{padding:15px 16px;border-bottom:1px solid var(--line)}.eyebrow{font-size:9px;color:#6f7d8e;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:9px}.title{font-size:19px;font-weight:800;line-height:1.3}.sub{color:#91a0b0;font:11px ui-monospace,monospace;margin-top:5px}.kv{display:grid;gap:7px;margin-top:12px}.kv div{display:flex;justify-content:space-between;gap:12px;font-size:11px}.kv span:first-child{color:#738195}.kv span:last-child{color:#dde5ec;text-align:right;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.kv a{color:#91baff;text-decoration:none}.signal{margin-top:12px;border:1px solid #3c3440;background:#121015;border-radius:8px;padding:10px;color:#b7a9af;font-size:10px;line-height:1.55}.stats{display:grid;grid-template-columns:1fr 1fr;gap:8px}.stat{border:1px solid var(--line);background:#0c1117;border-radius:8px;padding:10px}.stat b{font-size:18px;display:block}.stat span{font-size:9px;color:#718092}.sources{display:grid;gap:7px}.src{display:flex;justify-content:space-between;gap:8px;align-items:center;padding:8px;border:1px solid var(--line);background:#0c1117;border-radius:7px;font-size:10px}.src .name{color:#cbd3dc}.src a{text-decoration:none}.ok{color:var(--green)}.partial{color:var(--amber)}.off{color:#8794a4}.bad{color:var(--red)}.graph{position:relative;overflow:hidden;background:radial-gradient(circle at 50% 45%,#121b26 0,#0a0f15 42%,#070a0f 80%)}.graph:before{content:"";position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.018) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.018) 1px,transparent 1px);background-size:32px 32px}.graphbar{position:absolute;z-index:2;left:18px;right:18px;top:15px;display:flex;justify-content:space-between;align-items:center}.graphbar h2{font-size:12px;margin:0;color:#9daaba}.graphbar small{display:block;color:#647285;margin-top:3px;font-size:9px}.tools{display:flex;gap:7px}.tools button{height:30px;padding:0 9px;border:1px solid #2b3644;border-radius:7px;background:#0d141c;color:#acb8c6;font-size:10px}.graph svg{position:absolute;inset:0;width:100%;height:100%}.edge{stroke:#536173;stroke-width:1.2;opacity:.65}.node text{fill:#fff!important;stroke:#070a0f!important;stroke-width:4px!important;paint-order:stroke!important;user-select:none}.node circle{stroke:#080b10;stroke-width:2}.node:hover circle{stroke:#fff;stroke-width:3}.emptyGraph{position:absolute;inset:0;display:grid;place-items:center;color:#677587;font-size:11px;text-align:center;line-height:1.8;pointer-events:none}.zoom{position:absolute;right:18px;bottom:15px;z-index:2;display:flex}.zoom button{width:32px;height:30px;border:1px solid #2a3542;background:#0d131b;color:#bdc7d2}.zoom button+button{border-left:0}.tabs{display:flex;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--panel);z-index:3}.tab{flex:1;height:45px;border:0;border-bottom:2px solid transparent;background:transparent;color:#758396;font-size:11px}.tab.active{color:#eaf0f6;border-bottom-color:var(--blue)}.pane{padding:15px}.detail h3{font-size:18px;margin:0 0 4px}.tag{display:inline-block;padding:4px 7px;border:1px solid #364453;border-radius:5px;color:#94a4b6;font-size:9px;margin-bottom:12px}.card{border:1px solid var(--line);background:#0c1117;border-radius:8px;padding:10px;margin-bottom:9px}.card h4{margin:0 0 5px;font-size:10px;line-height:1.4}.card p{margin:0;color:#8b99a8;font-size:9px;line-height:1.55}.meta{margin-top:7px;font-size:8px;color:#677688;display:flex;justify-content:space-between;gap:7px}.card a{color:#91baff;text-decoration:none}.notice{padding:10px;border:1px solid #2d3947;background:#0b1118;border-radius:7px;color:#7f8c9a;font-size:9px;line-height:1.6}.empty{color:#677587;font-size:10px;line-height:1.8}.risk-bad{border-color:#5b2730}@media(max-width:1100px){.main{grid-template-columns:250px minmax(0,1fr)}.right{display:none}.searchmeta{display:none}}@media(max-width:760px){.main{grid-template-columns:1fr}.left{display:none}.app{grid-template-rows:60px 96px 1fr}.search{padding:11px 12px}.top{padding:0 12px}}</style></head><body>
<div class="app"><header class="top"><div class="brand"><div class="logo"></div><div><h1>Taiwan Entity Intelligence</h1><p>PUBLIC-RECORD INVESTIGATION WORKSPACE</p></div></div><div id="systemStatus" class="status">● LIVE DATA</div></header>
<div class="search"><div class="searchbox"><input id="q" maxlength="8" inputmode="numeric" placeholder="輸入 8 碼公司統編，例如 23060248"><button id="search" class="primary">開始調查</button></div><button id="sample" class="secondary">載入範例</button><div class="searchmeta">官方公開資料即時查詢<br>＋你的 Supabase source/evidence layer</div></div>
<main class="main"><aside class="panel left"><section class="section"><div class="eyebrow">Target entity</div><div id="company" class="title">尚未選擇企業</div><div id="uniform" class="sub">輸入統編開始調查</div><div id="companyKV"></div><div id="signal" class="signal" style="display:none"></div></section><section class="section"><div class="eyebrow">Network overview</div><div class="stats"><div class="stat"><b id="people">—</b><span>董監事</span></div><div class="stat"><b id="edges">—</b><span>關係邊</span></div><div class="stat"><b id="evcount">—</b><span>公開證據</span></div><div class="stat"><b id="localev">—</b><span>我的資料</span></div></div></section><section class="section"><div class="eyebrow">My data · Supabase</div><div id="dbStatus" class="sources"><div class="src"><span class="name">正在檢查…</span><span class="off">—</span></div></div></section><section class="section"><div class="eyebrow">Open-data sources</div><div id="sourceStatus" class="sources"></div></section><section class="section"><div class="eyebrow">Interpretation</div><div class="notice">命中公開裁罰、反詐或裁判資料只表示存在公開紀錄，不直接代表企業或個人犯罪。</div></section></aside>
<section class="graph"><div class="graphbar"><div><h2 id="graphTitle">企業關係圖譜</h2><small id="graphSub">等待查詢</small></div><div class="tools"><button id="fit">重置</button><button id="clear">清空</button></div></div><svg id="svg" viewBox="0 0 1000 700" preserveAspectRatio="none"></svg><div id="graphEmpty" class="emptyGraph">輸入統編後<br>這裡會顯示企業、董監事與來源證據。</div><div class="zoom"><button id="minus">−</button><button id="one">1:1</button><button id="plus">＋</button></div></section>
<aside class="panel right"><div class="tabs"><button class="tab active" data-tab="overview">企業</button><button class="tab" data-tab="evidence">Evidence</button></div><div id="overviewPane" class="pane"><div class="empty">選擇企業後，這裡會顯示公司資料與調查訊號。</div></div><div id="evidencePane" class="pane" style="display:none"></div></aside></main></div>
<script src="/app.js?v=20260902" defer></script></body></html>"""

def _judicial_request(jid=None):
    if not SUPABASE_KEY:
        return 503, {"status": "not_configured", "error": "Supabase key not configured"}
    url = JUDICIAL_EDGE
    if jid: url += "?" + urllib.parse.urlencode({"jid": jid})
    req = urllib.request.Request(url, headers={"Authorization":f"Bearer {SUPABASE_KEY}","apikey":SUPABASE_KEY,"Accept":"application/json","User-Agent":"T.E.I./4.0"})
    try:
        with urllib.request.urlopen(req, timeout=50) as r:
            body=r.read().decode("utf-8",errors="replace")
            try: data=json.loads(body)
            except Exception: data={"status":"error","error":body[:1200]}
            return r.status,data
    except urllib.error.HTTPError as exc:
        body=exc.read().decode("utf-8",errors="replace")
        try: data=json.loads(body)
        except Exception: data={"status":"error","error":body[:1200]}
        return exc.code,data
    except Exception as exc:
        return 502,{"status":"error","error":str(exc)}

def smoke_result():
    result={"overall":"FAIL","test_target":TEST_UNIFORM,"test_target_name":TEST_NAME,"checks":{},"summary":{"passed":0,"failed":0,"warning":0}}
    try:
        data=build_company(TEST_UNIFORM); company=data.get("company") or {}; people=data.get("people") or []; local=data.get("local_context") or {}; statuses=data.get("evidence_status") or {}
        for label,ok,detail in [("MOEA 公司 API",bool(data.get("company_name")) and bool(company),"公司基本資料可取得"),("MOEA 董監事 API",isinstance(people,list) and len(people)>0,f"取得 {len(people)} 位董監事"),("Supabase 資料庫",bool(local.get("configured")) and local.get("error") is None,"REST 讀取正常")]:
            result["checks"][label]={"status":"PASS" if ok else "FAIL","detail":detail}; result["summary"]["passed" if ok else "failed"]+=1
        for label,item in statuses.items():
            result["checks"][label]={"status":"PASS" if item.get("status")=="ok" else "WARN","matched":int(item.get("matched") or 0),"detail":item.get("message","")}; result["summary"]["passed" if item.get("status")=="ok" else "warning"]+=1
        result["company"]={"name":data.get("company_name"),"uniform_number":TEST_UNIFORM,"director_count":len(people),"live_evidence_count":len(data.get("evidence") or []),"local_evidence_count":int(local.get("evidence_count") or 0),"website_url":data.get("website_url"),"website_crosscheck":data.get("website_crosscheck")}
        result["overall"]="PASS" if result["summary"]["failed"]==0 else "FAIL"
    except Exception as exc:
        result["checks"]["Gateway"]={"status":"FAIL","detail":f"{type(exc).__name__}: {exc}"}; result["summary"]["failed"]+=1
    return result

class Handler(BaseHTTPRequestHandler):
    def _send(self,status,body,ctype):
        data=body.encode("utf-8") if isinstance(body,str) else body; self.send_response(status); self.send_header("Content-Type",ctype); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        path=self.path.split("?",1)[0]; query=parse_qs(urlparse(self.path).query)
        if path=="/app.js": return self._send(200,APP_JS,"application/javascript; charset=utf-8")
        if path=="/api" and query.get("format")==["json"]: return self._send(200,json.dumps(smoke_result(),ensure_ascii=False),"application/json; charset=utf-8")
        if path=="/api": return self._send(200,json.dumps(smoke_result(),ensure_ascii=False),"application/json; charset=utf-8")
        if path=="/api/judicial/health":
            status,payload=_judicial_request(); return self._send(status,json.dumps(payload,ensure_ascii=False),"application/json; charset=utf-8")
        if path=="/api/judicial":
            status,payload=_judicial_request((query.get("jid") or [None])[0]); return self._send(status,json.dumps(payload,ensure_ascii=False),"application/json; charset=utf-8")
        return self._send(200,HTML,"text/html; charset=utf-8")
    def log_message(self,fmt,*args): return
handler=Handler
