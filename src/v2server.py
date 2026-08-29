"""T.E.I. v2 API-first server.

Large government datasets are queried live or through small source adapters;
raw archives remain in Supabase Storage instead of being bulk-loaded into Postgres.
"""
import json
import os
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote

COMPANY_API = "https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6"
DIRECTOR_API = "https://data.gcis.nat.gov.tw/od/data/api/4E5F7653-1B91-4DDC-99D5-468530FAE396"
RESPONSIBLE_API = "https://data.gcis.nat.gov.tw/od/data/api/4B61A0F1-458C-43F9-93F3-9FD6DA5E1B08"
SUPABASE = os.environ.get("SUPABASE_URL", "https://anntdcxttvffekslbrkj.supabase.co")
SUPABASE_ANON = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("VITE_SUPABASE_ANON_KEY")
JUDICIAL_SEARCH = "https://judgment.judicial.gov.tw/LAW_Mobile_FJUD/FJUD/qryresult.aspx?judtype=JUDBOOK&kw={}"


def _json_get(url, timeout=12, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "T.E.I./v2"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8-sig", "replace"))


def _company_filter(api, field, value, top=100):
    params = urllib.parse.urlencode({"$format":"json", "$filter":f"{field} eq {value}", "$skip":"0", "$top":str(top)})
    payload = _json_get(api + "?" + params)
    return payload if isinstance(payload, list) else []


def _edge(slug, params):
    if not SUPABASE_ANON:
        return {"status":"not_configured","matched":0,"message":"SUPABASE_ANON_KEY 未設定"}
    q = urllib.parse.urlencode(params)
    url = f"{SUPABASE}/functions/v1/{slug}?{q}"
    req = urllib.request.Request(url, headers={"Authorization":f"Bearer {SUPABASE_ANON}","apikey":SUPABASE_ANON,"User-Agent":"T.E.I./v2"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode("utf-8-sig","replace"))
    except Exception as exc:
        return {"status":"error","matched":0,"message":str(exc)}


def _evidence(source, dataset, rows, title_key, summary):
    out=[]
    for i,row in enumerate(rows[:100]):
        title = next((row.get(k) for k in title_key if row.get(k)), source)
        out.append({"evidence_id":f"{dataset}:{i}","schema_version":"1.0","source":{"type":"government_open_data","name":source,"dataset_id":dataset},"fact":{"type":dataset,"title":title,"summary":summary},"confidence":1.0,"status":"active","raw":row})
    return out


def build_company(uniform):
    basic_rows = _company_filter(COMPANY_API, "Business_Accounting_NO", uniform, 1)
    basic = basic_rows[0] if basic_rows else {"Business_Accounting_NO":uniform}
    name = basic.get("Company_Name") or basic.get("Juristic_Person_Name") or uniform
    drows = _company_filter(DIRECTOR_API, "Business_Accounting_NO", uniform, 1000)
    people=[]; nodes=[{"id":f"company:{uniform}","type":"company","label":name,"properties":{"uniform_number":uniform,"source":"經濟部商工行政資料開放平台"}}]; edges=[]
    for row in drows:
        person=row.get("Person_Name") or row.get("person_name")
        if not person: continue
        p={"uniform_number":uniform,"company_name":name,"person_name":person,"position":row.get("Person_Position_Name") or row.get("position"),"shares":row.get("Person_Shareholding") or row.get("shares"),"representative":row.get("Representative") or row.get("representative")}
        people.append(p)
        pid=f"person:{person}"
        nodes.append({"id":pid,"type":"person","label":person,"properties":{"position":p["position"],"shares":p["shares"],"source":"經濟部公司登記董監事資料"}})
        edges.append({"source":f"company:{uniform}","target":pid,"relationship":p["position"] or "董事／監察人","properties":{"source":"MOEA_DIRECTOR_API","live":True}})
        if len(people)>=30: break

    evidence=[]; statuses={}
    labor=_edge("labor-penalties-api", {"company":name,"limit":"50"});
    if labor.get("data"):
        data=labor["data"]
        if isinstance(data,str):
            try:data=json.loads(data)
            except Exception:data={}
        rows=data.get("result") or data.get("data") or data.get("records") or []
        if isinstance(rows,list): evidence += _evidence("勞動部政府開放資料 API","administrative_penalty",rows,["事業單位名稱或負責人","事業單位名稱"],"勞動部公開資料命中此企業名稱；不等於法律結論")
        statuses["裁罰"]={"status":"ok","matched":len(evidence)}
    else: statuses["裁罰"]={"status":labor.get("status","error"),"matched":0,"message":labor.get("message")}

    fraud=_edge("anti-fraud-api", {"q":name,"limit":"50"}); frows=fraud.get("data") or []
    if isinstance(frows,list): evidence += _evidence("警政署165反詐騙諮詢專線／遭停止解析涉詐網站","anti_fraud_domain",frows,["WEBURL","WEBSITE_NM","網域","網站名稱"],"165 公開資料命中；表示來源紀錄存在相符值，不等於此公司本身已被認定涉詐")
    statuses["165"]={"status":"ok" if fraud.get("status") in (None,"ok") and isinstance(frows,list) else fraud.get("status","error"),"matched":len(frows) if isinstance(frows,list) else 0}

    env=_edge("environment-penalties-api", {"q":name}); erows=env.get("data") or []
    if isinstance(erows,list): evidence += _evidence("環境部裁罰處分","environment_penalty",erows,["name","行為人名稱","case","案件名稱"],"環境部公開裁罰資料命中；請核對原始處分內容與時間")
    statuses["裁罰_環境"]={"status":"ok" if isinstance(erows,list) else env.get("status","error"),"matched":len(erows) if isinstance(erows,list) else 0}

    statuses["標案"]={"status":"partial","message":"PCC 目前使用獨立查詢層；官方政府電子採購網尚未提供可直接依廠商統編查詢的公開 API，因此不冒充官方 API。"}
    statuses["裁判書"]={"status":"not_configured","message":"司法院 API 需要資料開放平台帳號密碼。"}
    graph={"nodes":nodes,"edges":edges}
    return {"uniform_number":uniform,"company":basic,"company_name":name,"people":people,"graph":graph,"data_mode":"v2_api_first","evidence":evidence,"evidence_count":len(evidence),"evidence_status":statuses,"judicial_search_url":JUDICIAL_SEARCH.format(urllib.parse.quote_plus(name)),"evidence_note":"T.E.I. v2：公司／董監事即時查詢；裁罰、165、環境資料走來源適配器；PCC 與司法院顯示實際可用狀態。"}


class Handler(BaseHTTPRequestHandler):
    def _send(self,status,payload,ctype="application/json; charset=utf-8"):
        body=json.dumps(payload,ensure_ascii=False).encode(); self.send_response(status); self.send_header("Content-Type",ctype); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path.startswith('/api/company/'):
            uid=unquote(self.path.split('/api/company/',1)[1].split('?',1)[0])
            if not uid.isdigit() or len(uid)!=8: return self._send(400,{"error":"統編必須是 8 碼數字。"})
            try:
                return self._send(200,build_company(uid))
            except Exception as exc:
                return self._send(502,{"error":"v2 來源查詢失敗","detail":str(exc)})
        if self.path.startswith('/api/health'):
            return self._send(200,{"status":"ok","version":"v2_api_first","supabase":SUPABASE})
        root=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); web=os.path.join(root,'web'); p=self.path.split('?',1)[0]
        if p=='/' or p=='':
            with open(os.path.join(web,'index.html'),'rb') as f: body=f.read()
            self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if p.startswith('/tei-enhancements.js'):
            with open(os.path.join(web,'tei-enhancements.js'),'rb') as f: body=f.read()
            self.send_response(200); self.send_header('Content-Type','application/javascript; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        self.send_response(404); self.end_headers()
