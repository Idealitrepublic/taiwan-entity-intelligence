"""Live public-record evidence connectors.

A match means only that an official source record contains the searched
observable. It is not a legal or criminal conclusion.
"""
import csv
import io
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

DATASET_IDS = {"labor_penalties":"109896","scam_domains":"176455","fake_investment_sites":"160055","scam_refutations":"38262"}
DIRECT_RESOURCES = {"109896":"https://apiservice.mol.gov.tw/OdService/download/A17000000J-020050-MUA"}

def _get(url, timeout=30, headers=None):
    req=urllib.request.Request(url,headers=headers or {"User-Agent":"TaiwanEntityIntelligence/0.5"})
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.read()

def _json(url):
    try:return json.loads(_get(url).decode("utf-8-sig","ignore"))
    except Exception:return {}

def _dataset_resources(dataset_id):
    urls=[]; meta=_json("https://data.gov.tw/api/v2/rest/dataset/{}".format(dataset_id))
    distributions=meta.get("distribution") or meta.get("distributions") or []
    if isinstance(distributions,dict):distributions=list(distributions.values())
    for item in distributions:
        if isinstance(item,dict):
            url=item.get("resourceDownloadURL") or item.get("downloadURL") or item.get("url")
            if url:urls.append(url)
    if dataset_id in DIRECT_RESOURCES:urls.append(DIRECT_RESOURCES[dataset_id])
    return list(dict.fromkeys(urls))

def _read_rows(url,limit=20000):
    raw=_get(url); text=raw.decode("utf-8-sig","replace"); stripped=text.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            obj=json.loads(text)
            if isinstance(obj,dict):
                for key in ("data","records","result","results"):
                    if isinstance(obj.get(key),list):return [x for x in obj[key] if isinstance(x,dict)][:limit]
            if isinstance(obj,list):return [x for x in obj if isinstance(x,dict)][:limit]
        except Exception:pass
    try:dialect=csv.Sniffer().sniff(text[:8192])
    except csv.Error:dialect=csv.excel
    return [dict(row) for _,row in zip(range(limit),csv.DictReader(io.StringIO(text),dialect=dialect))]

def _norm(value):return re.sub(r"\s+","",str(value or "")).casefold()
def _match_row(row,needles):
    hay=_norm(" ".join(str(v) for v in row.values()));return any(n and n in hay for n in needles)

def _evidence(source,record_id,title,summary,url,raw,fact_type,matched_terms=None):
    now=datetime.now(timezone.utc).isoformat()
    return {"evidence_id":"{}:{}".format(source,record_id),"schema_version":"1.0","observed_at":now,"retrieved_at":now,"source":{"type":"government_open_data","name":source,"record_id":str(record_id),"url":url},"fact":{"type":fact_type,"title":title,"summary":summary,"matched_terms":matched_terms or []},"confidence":1.0,"status":"active","raw":raw}

def _collect_dataset(dataset_key,needles,source_name,fact_type,max_rows=100):
    out=[]; dataset_id=DATASET_IDS[dataset_key]; resources=_dataset_resources(dataset_id)
    if not resources:return out,{"status":"source_unavailable","dataset_id":dataset_id,"matched":0}
    for url in resources:
        try:rows=_read_rows(url)
        except Exception:continue
        for idx,row in enumerate(rows):
            if not _match_row(row,needles):continue
            hay=_norm(" ".join(str(v) for v in row.values())); matched=[n for n in needles if n in hay]
            record_id=row.get("處分字號") or row.get("處分書文號") or row.get("網域") or row.get("網址") or row.get("編號") or row.get("案件編號") or idx
            title=row.get("事業單位名稱") or row.get("事業單位名稱或負責人") or row.get("網域") or row.get("網站名稱") or row.get("標題") or source_name
            out.append(_evidence(source_name,record_id,title,"官方公開資料命中查詢實體；這是來源紀錄，不等於法律上的違法或涉詐認定。","https://data.gov.tw/dataset/{}".format(dataset_id),row,fact_type,matched))
            if len(out)>=max_rows:return out,{"status":"ok","dataset_id":dataset_id,"matched":len(out)}
    return out,{"status":"ok","dataset_id":dataset_id,"matched":len(out)}

def _judicial_recent(needles,max_docs=50):
    user=os.getenv("JUDICIAL_API_USER") or os.getenv("JUDICIAL_USER"); password=os.getenv("JUDICIAL_API_PASSWORD") or os.getenv("JUDICIAL_PASSWORD")
    if not user or not password:return [],{"status":"not_configured","message":"司法院 API 尚未設定帳密。","matched":0}
    try:
        def post(path,payload,timeout=30):
            body=json.dumps(payload,ensure_ascii=False).encode("utf-8"); req=urllib.request.Request("https://data.judicial.gov.tw/jdg/api"+path,data=body,headers={"Content-Type":"application/json","User-Agent":"TaiwanEntityIntelligence/0.5"})
            return json.loads(urllib.request.urlopen(req,timeout=timeout).read().decode("utf-8"))
        auth=post("/Auth",{"user":user,"password":password}); token=auth.get("Token") or auth.get("token")
        if not token:return [],{"status":"auth_failed","message":"司法院 API 驗證失敗。","matched":0}
        listing=post("/JList",{"token":token}); ids=[]
        for day in listing if isinstance(listing,list) else []:
            if isinstance(day,dict):ids.extend(day.get("list",[]))
        ids=list(dict.fromkeys(ids))[:max_docs]; out=[]
        for jid in ids:
            try:
                doc=post("/JDoc",{"token":token,"j":jid}); content=_norm(json.dumps(doc,ensure_ascii=False))
                if any(n in content for n in needles):out.append(_evidence("司法院裁判書開放 API",jid,doc.get("JTITLE") or jid,"近期裁判書全文包含查詢實體名稱；仍需人工確認當事人與案件關係。","https://data.judicial.gov.tw/",doc,"judgment",[n for n in needles if n in content]))
            except Exception:continue
        return out,{"status":"ok","checked":len(ids),"matched":len(out)}
    except Exception as exc:return [],{"status":"error","message":str(exc),"matched":0}

def collect_public_evidence(company_name,people=None):
    needles=[_norm(company_name)]+[_norm(p) for p in (people or []) if p]; needles=[n for n in needles if len(n)>=2]
    evidence=[]; statuses={}
    items=[("labor_penalties","勞動部／違反勞動法令事業單位","administrative_penalty","裁罰"),("scam_domains","165反詐騙諮詢專線／遭停止解析涉詐網站","anti_fraud_domain","165"),("fake_investment_sites","165反詐騙諮詢專線／假投資(博弈)網站","anti_fraud_site","165"),("scam_refutations","165反詐騙諮詢專線／詐騙闢謠專區","anti_fraud_refutation","165")]
    for key,source,fact_type,status_key in items:
        rows,status=_collect_dataset(key,needles,source,fact_type); evidence.extend(rows); statuses[status_key]=status
    judicial,jstatus=_judicial_recent(needles); evidence.extend(judicial); statuses["裁判書"]=jstatus
    return {"evidence":evidence,"statuses":statuses,"summary":{"total":len(evidence),"by_type":{"裁判書":sum(1 for x in evidence if x["fact"]["type"]=="judgment"),"裁罰":sum(1 for x in evidence if x["fact"]["type"]=="administrative_penalty"),"165":sum(1 for x in evidence if x["fact"]["type"].startswith("anti_fraud"))}},"note":"公開紀錄命中只表示來源資料存在名稱／觀測值相符；不代表該實體已被認定違法或涉詐。"}
