"""Standard-library web server for the investigation workspace."""
import json
import os
import urllib.request
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
DEMO_COMPANY = "82876417"
PRIMARY_DOMAIN = "taiwan-entity-intelligence.vercel.app"
WORKING_DEPLOYMENT = "https://taiwan-entity-intelligence-etphd32sd-coldlight871029-9944.vercel.app"

def _demo_response():
    company="御首服務事業有限公司"
    people=[("person:林宇澤","林宇澤","主要聯絡／業務運作人物"),("person:吳虹葳","吳虹葳","判決記載之人頭負責人及股東"),("person:王凱迪","王凱迪","判決記載之出資人"),("person:周金川","周金川","判決記載之相關人物"),("person:賴乙誠","賴乙誠","判決記載之相關人物"),("person:朱家禾","朱家禾","判決記載之相關人物")]
    nodes=[{"id":"company:82876417","type":"company","label":company,"properties":{"uniform_number":"82876417","demo":True,"source_note":"官方裁判書案例測試資料"}}]
    edges=[]
    for pid,name,role in people:nodes.append({"id":pid,"type":"person","label":name,"properties":{"position":role,"source":"official_judgment"}});edges.append({"source":"company:82876417","target":pid,"relationship":role})
    evidence=[
      {"evidence_id":"judgment:KLDM-111訴328","schema_version":"1.0","source":{"type":"judicial_public","name":"司法院裁判書－111年度訴字第328號","record_id":"KLDM,111,訴,328,20230428,1","url":"https://judgment.judicial.gov.tw/FJUD/printData.aspx?id=KLDM%2C111%2C%E8%A8%B4%2C328%2C20230428%2C1"},"fact":{"type":"judgment","title":"臺灣基隆地方法院 111年度訴字第328號","summary":"判決記載吳虹葳以人頭負責人及股東身分設立御首公司，並記載詐欺集團以御首公司名義對21人實施詐欺。此為裁判書觀測事實，不代表公司法人本身當然成立刑事責任。"},"confidence":1.0,"status":"active","entity_id":"company:82876417","entity_type":"company"},
      {"evidence_id":"judgment:KLDM-110原訴9","schema_version":"1.0","source":{"type":"judicial_public","name":"司法院裁判書－110年度原訴字第9號","record_id":"KLDM,110,原訴,9,20220128,11","url":"https://data.judicial.gov.tw/opendl/JDocFile/KLDM/110%2C%E5%8E%9F%E8%A8%B4%2C9%2C20220128%2C11.pdf"},"fact":{"type":"judgment","title":"臺灣基隆地方法院 110年度原訴字第9號","summary":"判決內容多處直接提及御首公司、林宇澤及相關人員的角色與案件事實；應以裁判全文核對各人的最終罪責與判決主文。"},"confidence":1.0,"status":"active","entity_id":"company:82876417","entity_type":"company"}]
    return {"uniform_number":DEMO_COMPANY,"company":{"Company_Name":company,"Responsible_Name":"吳虹葳","Company_Status":"解散","Company_Setup_Date":"108/05/17","Capital_Stock_Amount":"200,000"},"company_name":company,"people":[{"person_name":n,"position":r} for _,n,r in people],"graph":{"nodes":nodes,"edges":edges},"data_mode":"demo_judicial_case","evidence":evidence,"evidence_count":2,"evidence_sources":{"司法院裁判書－111年度訴字第328號":1,"司法院裁判書－110年度原訴字第9號":1},"evidence_status":{"標案":"not_run","裁罰":"not_run","165":"not_run","裁判書":"demo_fixture"},"judicial_search_url":JUDICIAL_SEARCH.format(quote_plus(company)),"evidence_note":"官方裁判書案例測試資料；不是即時全量裁判書查詢。"}

def _tender_evidence(tenders):
    rows=[]
    for tender in tenders:
        tid=tender.get("tender_id") or tender.get("案號") or tender.get("標案編號") or tender.get("id")
        if not tid:continue
        title=tender.get("tender_name") or tender.get("標案名稱") or tender.get("案名") or str(tid)
        rows.append({"evidence_id":"procurement:{}".format(tid),"schema_version":"1.0","source":{"type":"government_open_data","name":"政府採購／本機標案資料","record_id":str(tid)},"fact":{"type":"government_tender","title":title,"summary":"本機資料庫含有政府採購紀錄；請回看原始標案確認得標、履約及時間脈絡。"},"confidence":1.0,"status":"active","raw":tender})
    return rows

def _judicial_link(company_name):return JUDICIAL_SEARCH.format(quote_plus(company_name))
def _decorate_evidence(evidence,company_name,people,uniform_number):
    cn=str(company_name or '').replace(' ','').casefold();pn=[(str(x or '').replace(' ','').casefold(),x) for x in people if x]
    for item in evidence:
        hay=json.dumps(item.get('raw') or item,ensure_ascii=False).replace(' ','').casefold()
        if cn and cn in hay:item['entity_id']='company:{}'.format(uniform_number);item['entity_type']='company'
        else:
            for norm,name in pn:
                if len(norm)>=2 and norm in hay:item['entity_id']='person:{}'.format(name);item['entity_type']='person';break
        item.setdefault('entity_id','company:{}'.format(uniform_number));item.setdefault('entity_type','company')
    return evidence

def _response(uniform_number,basic,company_name,people,graph,evidence,statuses,mode):
    counts={}
    for x in evidence:
        n=x.get('source',{}).get('name','其他');counts[n]=counts.get(n,0)+1
    return {"uniform_number":uniform_number,"company":basic,"company_name":company_name,"people":people,"graph":graph,"data_mode":mode,"evidence":evidence,"evidence_count":len(evidence),"evidence_sources":counts,"evidence_status":statuses,"judicial_search_url":_judicial_link(company_name),"evidence_note":"公開紀錄命中僅表示來源資料存在名稱／觀測值相符，不代表該實體已被認定違法或涉詐；同名人物仍需人工核對。"}

class Handler(BaseHTTPRequestHandler):
    def _json(self,status,payload):
        body=json.dumps(payload,ensure_ascii=False).encode('utf-8');self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def _proxy_primary_domain(self):
        host=self.headers.get('Host','').split(':',1)[0].lower()
        if host!=PRIMARY_DOMAIN:return False
        target=WORKING_DEPLOYMENT+self.path
        try:
            req=urllib.request.Request(target,headers={'User-Agent':'TaiwanEntityIntelligence-primary-bridge'})
            with urllib.request.urlopen(req,timeout=55) as response:
                body=response.read();self.send_response(response.status)
                ct=response.headers.get('Content-Type')
                if ct:self.send_header('Content-Type',ct)
                self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return True
        except Exception as exc:self._json(502,{"error":"正式網址與已驗證服務的橋接失敗。","detail":str(exc)});return True
    def do_GET(self):
        if self._proxy_primary_domain():return
        parsed=urlparse(self.path)
        if parsed.path=='/':
            with open(os.path.join(WEB,'index.html'),'rb') as f:body=f.read()
            injection=b'<script src="/tei-enhancements.js?v=2"></script>'
            if b'tei-enhancements.js' not in body:body=body.replace(b'</body>',injection+b'</body>')
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        if parsed.path.startswith('/tei-enhancements.js'):
            with open(os.path.join(WEB,'tei-enhancements.js'),'rb') as f:body=f.read()
            self.send_response(200);self.send_header('Content-Type','application/javascript; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        prefix='/api/company/'
        if not parsed.path.startswith(prefix):self.send_response(404);self.end_headers();return
        uid=unquote(parsed.path[len(prefix):])
        if not uid.isdigit() or len(uid)!=8:self._json(400,{"error":"統編必須是 8 碼數字。"});return
        try:
            if uid==DEMO_COMPANY:self._json(200,_demo_response());return
            basic=get_company(uid)
            try:conn=connect()
            except FileNotFoundError:
                graph=live_company_graph(uid);people=[{"uniform_number":uid,"company_name":(basic or {}).get('Company_Name') or uid,"position":n.get('properties',{}).get('position'),"person_name":n.get('label'),"shares":n.get('properties',{}).get('shares')} for n in graph.get('nodes',[]) if n.get('type')=='person'];name=(basic or {}).get('Company_Name') or uid;public=collect_public_evidence(name,[p.get('person_name') for p in people]);evidence=_decorate_evidence(public['evidence'],name,[p.get('person_name') for p in people],uid);statuses={"標案":"not_available_in_public_runtime",**public['statuses']}
                if not basic and not graph.get('nodes'):self._json(404,{"error":"找不到此統編。"});return
                self._json(200,_response(uid,basic,name,people,graph,evidence,statuses,'live_government_open_data'));return
            people=company_people(conn,uid)
            if not basic and not people:conn.close();self._json(404,{"error":"找不到此統編。"});return
            name=(basic or {}).get('Company_Name') or (people[0]['company_name'] if people else uid);graph=company_graph(conn,uid);tenders=company_tenders(conn,name);conn.close();public=collect_public_evidence(name,[p.get('person_name') for p in people]);evidence=_decorate_evidence(_tender_evidence(tenders)+public['evidence'],name,[p.get('person_name') for p in people],uid);statuses={"標案":"checked",**public['statuses']};self._json(200,_response(uid,basic,name,people,graph,evidence,statuses,'local_database'))
        except Exception as exc:self._json(500,{"error":str(exc)})

def main():
    ThreadingHTTPServer((os.environ.get('HOST','127.0.0.1'),int(os.environ.get('PORT','8000'))),Handler).serve_forever()
if __name__=='__main__':main()
