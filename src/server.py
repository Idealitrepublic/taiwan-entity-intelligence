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
DEMO_COMPANY = "82876417"


def _demo_response():
    company = "御首服務事業有限公司"
    people = [("person:林宇澤","林宇澤","主要聯絡／業務運作人物"),("person:吳虹葳","吳虹葳","判決記載之人頭負責人及股東"),("person:王凱迪","王凱迪","判決記載之出資人"),("person:周金川","周金川","判決記載之相關人物"),("person:賴乙誠","賴乙誠","判決記載之相關人物"),("person:朱家禾","朱家禾","判決記載之相關人物")]
    nodes=[{"id":"company:82876417","type":"company","label":company,"properties":{"uniform_number":"82876417","demo":True,"source_note":"官方裁判書案例測試資料"}}]
    edges=[]
    for pid,name,role in people:
        nodes.append({"id":pid,"type":"person","label":name,"properties":{"position":role,"source":"official_judgment"}}); edges.append({"source":"company:82876417","target":pid,"relationship":role})
    evidence=[
      {"evidence_id":"judgment:KLDM-111訴328","schema_version":"1.0","source":{"type":"judicial_public","name":"司法院裁判書－111年度訴字第328號","record_id":"KLDM,111,訴,328,20230428,1","url":"https://judgment.judicial.gov.tw/FJUD/printData.aspx?id=KLDM%2C111%2C%E8%A8%B4%2C328%2C20230428%2C1"},"fact":{"type":"judgment","title":"臺灣基隆地方法院 111年度訴字第328號","summary":"判決記載吳虹葳以人頭負責人及股東身分設立御首公司，並記載詐欺集團以御首公司名義對21人實施詐欺。此為裁判書觀測事實，不代表公司法人本身當然成立刑事責任。"},"confidence":1.0,"status":"active","entity_id":"company:82876417","entity_type":"company"},
      {"evidence_id":"judgment:KLDM-110原訴9","schema_version":"1.0","source":{"type":"judicial_public","name":"司法院裁判書－110年度原訴字第9號","record_id":"KLDM,110,原訴,9,20220128,11","url":"https://data.judicial.gov.tw/opendl/JDocFile/KLDM/110%2C%E5%8E%9F%E8%A8%B4%2C9%2C20220128%2C11.pdf"},"fact":{"type":"judgment","title":"臺灣基隆地方法院 110年度原訴字第9號","summary":"判決內容多處直接提及御首公司、林宇澤及相關人員的角色與案件事實；應以裁判全文核對各人的最終罪責與判決主文。"},"confidence":1.0,"status":"active","entity_id":"company:82876417","entity_type":"company"}
    ]
    return {"uniform_number":DEMO_COMPANY,"company":{"Company_Name":company,"Responsible_Name":"吳虹葳","Company_Status":"解散","Company_Setup_Date":"108/05/17","Capital_Stock_Amount":"200,000"},"company_name":company,"people":[{"person_name":n,"position":r} for _,n,r in people],"graph":{"nodes":nodes,"edges":edges},"data_mode":"demo_judicial_case","evidence":evidence,"evidence_count":len(evidence),"evidence_sources":{"司法院裁判書－111年度訴字第328號":1,"司法院裁判書－110年度原訴字第9號":1},"evidence_status":{"標案":"not_run","裁罰":"not_run","165":"not_run","裁判書":"demo_fixture"},"judicial_search_url":JUDICIAL_SEARCH.format(quote_plus(company)),"evidence_note":"這是官方裁判書案例的測試 fixture，用來驗證圖譜與 Evidence UI；不是即時全量裁判書查詢。"}


def _tender_evidence(tenders):
    rows=[]
    for tender in tenders:
        tender_id=tender.get("tender_id") or tender.get("案號") or tender.get("標案編號") or tender.get("id")
        if not tender_id: continue
        title=tender.get("tender_name") or tender.get("標案名稱") or tender.get("案名") or str(tender_id)
        rows.append({"evidence_id":"procurement:{}".format(tender_id),"schema_version":"1.0","source":{"type":"government_open_data","name":"政府採購／本機標案資料","record_id":str(tender_id)},"fact":{"type":"government_tender","title":title,"summary":"本機資料庫含有政府採購紀錄；請回看原始標案確認得標、履約及時間脈絡。"},"confidence":1.0,"status":"active","raw":tender})
    return rows


def _judicial_link(company_name): return JUDICIAL_SEARCH.format(quote_plus(company_name))


def _decorate_evidence(evidence,company_name,people,uniform_number):
    company_norm=str(company_name or "").replace(" ","").casefold(); person_norm=[(str(p or "").replace(" ","").casefold(),p) for p in people if p]
    for item in evidence:
        hay=json.dumps(item.get("raw") or item,ensure_ascii=False).replace(" ","").casefold()
        if company_norm and company_norm in hay: item["entity_id"]="company:{}".format(uniform_number); item["entity_type"]="company"
        else:
            for norm,name in person_norm:
                if len(norm)>=2 and norm in hay: item["entity_id"]="person:{}".format(name); item["entity_type"]="person"; break
        item.setdefault("entity_id","company:{}".format(uniform_number)); item.setdefault("entity_type","company")
    return evidence


def _response(uniform_number,basic,company_name,people,graph,evidence,statuses,mode):
    source_counts={}
    for item in evidence:
        name=item.get("source",{}).get("name","其他"); source_counts[name]=source_counts.get(name,0)+1
    return {"uniform_number":uniform_number,"company":basic,"company_name":company_name,"people":people,"graph":graph,"data_mode":mode,"evidence":evidence,"evidence_count":len(evidence),"evidence_sources":source_counts,"evidence_status":statuses,"judicial_search_url":_judicial_link(company_name),"evidence_note":"公開紀錄命中僅表示來源資料存在名稱／觀測值相符，不代表該實體已被認定違法或涉詐；同名人物仍需人工核對。"}


class Handler(BaseHTTPRequestHandler):
    def _json(self,status,payload):
        body=json.dumps(payload,ensure_ascii=False).encode("utf-8"); self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        parsed=urlparse(self.path)
        if parsed.path=="/":
            with open(os.path.join(WEB,"index.html"),"rb") as f: body=f.read()
            self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body); return
        prefix="/api/company/"
        if not parsed.path.startswith(prefix): self.send_response(404); self.end_headers(); return
        uniform_number=unquote(parsed.path[len(prefix):])
        if not uniform_number.isdigit() or len(uniform_number)!=8: self._json(400,{"error":"統編必須是 8 碼數字。"}); return
        try:
            if uniform_number==DEMO_COMPANY:
                self._json(200,_demo_response()); return
            basic=get_company(uniform_number)
            try: conn=connect()
            except FileNotFoundError:
                graph=live_company_graph(uniform_number); people=[{"uniform_number":uniform_number,"company_name":(basic or {}).get("Company_Name") or uniform_number,"position":n.get("properties",{}).get("position"),"person_name":n.get("label"),"shares":n.get("properties",{}).get("shares")} for n in graph.get("nodes",[]) if n.get("type")=="person"]; company_name=(basic or {}).get("Company_Name") or uniform_number; public=collect_public_evidence(company_name,[p.get("person_name") for p in people]); evidence=_decorate_evidence(public["evidence"],company_name,[p.get("person_name") for p in people],uniform_number); statuses={"標案":"not_available_in_public_runtime",**public["statuses"]}
                if not basic and not graph.get("nodes"): self._json(404,{"error":"找不到此統編。"}); return
                self._json(200,_response(uniform_number,basic,company_name,people,graph,evidence,statuses,"live_government_open_data")); return
            people=company_people(conn,uniform_number)
            if not basic and not people: conn.close(); self._json(404,{"error":"找不到此統編。"}); return
            company_name=(basic or {}).get("Company_Name") or (people[0]["company_name"] if people else uniform_number); graph=company_graph(conn,uniform_number); tenders=company_tenders(conn,company_name); conn.close(); public=collect_public_evidence(company_name,[p.get("person_name") for p in people]); evidence=_decorate_evidence(_tender_evidence(tenders)+public["evidence"],company_name,[p.get("person_name") for p in people],uniform_number); statuses={"標案":"checked",**public["statuses"]}; self._json(200,_response(uniform_number,basic,company_name,people,graph,evidence,statuses,"local_database"))
        except Exception as exc: self._json(500,{"error":str(exc)})


def main():
    host=os.environ.get("HOST","127.0.0.1"); port=int(os.environ.get("PORT","8000")); ThreadingHTTPServer((host,port),Handler).serve_forever()

if __name__=="__main__": main()
