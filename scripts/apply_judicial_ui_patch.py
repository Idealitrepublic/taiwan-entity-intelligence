from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = "T.E.I_ONE_TIME_JUDICIAL_UI_PATCH_V1"

# 1) Force graph labels to white regardless of the inline SVG renderer.
p = ROOT / "web" / "tei-enhancements.js"
s = p.read_text(encoding="utf-8")
if MARKER not in s:
    block = r'''
// T.E.I_ONE_TIME_JUDICIAL_UI_PATCH_V1
// Keep graph labels readable even when the base inline SVG renderer uses browser defaults.
const teiGraphStyle = document.createElement('style');
teiGraphStyle.textContent = '.graph svg .node text,.graph svg text.node-label{fill:#ffffff!important;color:#ffffff!important;stroke:#070a0f!important;stroke-width:4px!important;paint-order:stroke!important;}';
document.head.appendChild(teiGraphStyle);

function teiJudicialPanel() {
  const pane = document.getElementById('overviewPane');
  if (!pane || document.getElementById('tei-judicial-api')) return;
  const box = document.createElement('div');
  box.id = 'tei-judicial-api';
  box.className = 'card';
  box.innerHTML = '<h4>司法院裁判書 API</h4><p>官方 Open API 需要司法院資料開放平台帳號密碼。T.E.I. 會在伺服器端保存憑證，不會送到瀏覽器。</p><div style="display:flex;gap:6px;margin-top:8px"><input id="tei-jid" placeholder="貼上 JID，例如 CHDM,105,交訴,51,20161216,1" style="flex:1;min-width:0;background:#111821;border:1px solid #334151;border-radius:6px;color:#edf2f7;padding:7px;font-size:9px"><button id="tei-jdoc" class="secondary" style="height:32px">取得裁判書</button></div><div id="tei-jdoc-result" style="margin-top:8px;font-size:9px;color:#8b99a8"></div>';
  pane.appendChild(box);
  document.getElementById('tei-jdoc').addEventListener('click', async () => {
    const jid = document.getElementById('tei-jid').value.trim();
    const out = document.getElementById('tei-jdoc-result');
    if (!jid) { out.textContent = '請輸入 JID。'; return; }
    out.textContent = '查詢司法院 API 中…';
    try {
      const r = await fetch('/api/judicial?jid=' + encodeURIComponent(jid) + '&t=' + Date.now(), {cache:'no-store'});
      const x = await r.json();
      if (!r.ok || x.status !== 'ok') throw new Error(x.error || x.detail?.error || x.detail || '司法院 API 尚未設定或驗證失敗');
      const d = x.data || {};
      const full = d.JFULLX || {};
      out.innerHTML = '<b style="color:#eaf0f6">' + (full.JFULLCONTENT ? '已取得裁判全文' : '已取得裁判資料') + '</b><br>' + esc(d.JTITLE || '') + ' · ' + esc(d.JID || jid) + (full.JFULLCONTENT ? '<div style="margin-top:7px;max-height:280px;overflow:auto;white-space:pre-wrap;color:#c9d2dc">' + esc(full.JFULLCONTENT) + '</div>' : '');
    } catch (e) { out.textContent = '司法院 API：' + e.message; }
  });
}

document.addEventListener('DOMContentLoaded', teiJudicialPanel);
const teiOldEnhance = enhance;
enhance = function(){ teiOldEnhance(); teiJudicialPanel(); };
'''
    s = s.replace('\n})();', '\n' + block + '\n})();', 1)
    p.write_text(s, encoding='utf-8')

# 2) Add a server-side proxy to the existing Supabase judicial-api Edge Function.
p = ROOT / "api" / "index.py"
s = p.read_text(encoding="utf-8")
if "def _judicial_proxy(" not in s:
    s = s.replace("import json\nfrom urllib.parse import parse_qs, urlparse", "import json\nimport urllib.error\nimport urllib.parse\nimport urllib.request\nfrom urllib.parse import parse_qs, urlparse", 1)
    helper = r'''

def _judicial_proxy(jid):
    if not SUPABASE_KEY:
        return 503, {"status": "not_configured", "error": "Supabase key not configured"}
    url = f"https://rztdbdurkjfrirsrrhtu.supabase.co/functions/v1/judicial-api?jid={urllib.parse.quote(jid, safe='')}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "apikey": SUPABASE_KEY,
        "Accept": "application/json",
        "User-Agent": "T.E.I./3.2",
    })
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            body = r.read().decode("utf-8", errors="replace")
            return r.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try: data = json.loads(body)
        except Exception: data = {"status":"error", "error":body[:800]}
        return exc.code, data
    except Exception as exc:
        return 502, {"status":"error", "error":str(exc)}
'''
    s = s.replace("\n\nclass Handler(BaseHandler):", helper + "\n\nclass Handler(BaseHandler):", 1)
    route = "        if path == \"/api/judicial\":\n            jid = query.get(\"jid\", [\"\"])[0].strip()\n            if not jid:\n                return self._send_raw(400, json.dumps({\"status\":\"error\",\"error\":\"缺少 jid\"}, ensure_ascii=False), \"application/json; charset=utf-8\")\n            code, data = _judicial_proxy(jid)\n            return self._send_raw(code, json.dumps(data, ensure_ascii=False), \"application/json; charset=utf-8\")\n"
    s = s.replace("        if path == \"/api/company/", route + "        if path == \"/api/company/", 1)
    p.write_text(s, encoding='utf-8')

print('patched')
