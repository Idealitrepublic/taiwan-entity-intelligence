"""Bounded live public-record evidence connectors.

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


def _get(url, timeout=25, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent":"TaiwanEntityIntelligence/0.4"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _json(url):
    try:
        return json.loads(_get(url).decode("utf-8-sig","ignore"))
    except Exception:
        return {}


def _dataset_resources(dataset_id):
    urls=[]
    meta=_json("https://data.gov.tw/api/v2/rest/dataset/{}".format(dataset_id))
    distributions=meta.get("distribution") or meta.get("distributions") or []
    if isinstance(distributions,dict): distributions=list(distributions.values())
    for item in distributions:
        if not isinstance(item,dict): continue
        url=item.get("resourceDownloadURL") or item.get("downloadURL") or item.get("url")
        if url: urls.append(url)
    if dataset_id in DIRECT_RESOURCES: urls.append(DIRECT_RESOURCES[dataset_id])
    return list(dict.fromkeys(urls))


def _read_csv_url(url,limit=10000):
    raw=_get(url); text=raw.decode("utf-8-sig","replace")
    try: dialect=csv.Sniffer().sniff(text[:8192])
    except csv.Error: dialect=csv.excel
    rows=csv.DictReader(io.StringIO(text),dialect=dialect)
    return [dict(row) for _,row in zip(range(limit),rows)]


def _norm(value): return re.sub(r"\s+","",str(value or "")).casefold()
def _match_row(row,needles):
    hay=_norm(" ".join(str(v) for v in row.values()))
    return any(n and n in hay for n in needles)


def _evidence(source,record_id,title,summary,url,raw,fact_type):
    now=datetime.now(timezone.utc).isoformat()
    return {"evidence_id":"{}:{}".format(source,record_id),"schema_version":"1.0","observed_at":now,"retrieved_at":now,"source":{"type":"government_open_data","name":source,"record_id":str(record_id),"url":url},"fact":{"type":fact_type,"title":title,"summary":summary},"confidence":1.0,"status":"active","raw":raw}


def _collect_dataset(dataset_key,needles,source_name,fact_type,max_rows=100):
    out=[]; dataset_id=DATASET_IDS[dataset_key]
    for url in _dataset_resources(dataset_id):
        try: rows=_read_csv_url(url)
        except Exception: continue
        for idx,row in enumerate(rows):
            if not _match_row(row,needles): continue
            record_id=row.get("處分字號") or row.get("處分書文號") or row.get("網域") or row.get("網址") or row.get("編號") or idx
            title=row.get("事業單位名稱") or row.get("事業單位名稱或負責人") or row.get("網域") or row.get("網站名稱") or row.get("標題") or source_name
            out.append(_evidence(source_name,record_id,title,"官方公開資料含有與查詢實體名稱相符的紀錄；請開啟來源確認完整脈絡。","https://data.gov.tw/dataset/{}".format(dataset_id),row,fact_type))
            if len(out)>=max_rows:return out
    return out


def _judicial_recent(needles,max_docs=20):
    user=os.getenv("JUDICIAL_API_USER") or os.getenv("JUDICIAL_USER"); password=os.getenv("JUDICIAL_API_PASSWORD") or os.getenv("JUDICIAL_PASSWORD")
    if not user or not password:return [],{"status":"not_configured","message":"司法院 API 尚未設定帳密；已提供官方全文檢索入口。"}
    try:
        def post(path,payload,timeout=20):
            body=json.dumps(payload,ensure_ascii=False).encode("utf-8"); req=urllib.request.Request("https://data.judicial.gov.tw/jdg/api"+path,data=body,headers={"Content-Type":"application/json","User-Agent":"TaiwanEntityIntelligence/0.4"})
            return json.loads(urllib.request.urlopen(req,timeout=timeout).read().decode("utf-8"))
        auth=post("/Auth",{"user":user,"password":password}); token=auth.get("Token") or auth.get("token")
        if not token:return [],{"status":"auth_failed","message":"司法院 API 驗證失敗。"}
        listing=post("/JList",{"token":token}); ids=[]
        for day in listing if isinstance(listing,list) else []:
            if isinstance(day,dict): ids.extend(day.get("list",[]))
        ids=list(dict.fromkeys(ids))[:max_docs]; out=[]
        for jid in ids:
            try:
                doc=post("/JDoc",{"token":token,"j":jid}); content=_norm(json.dumps(doc,ensure_ascii=False))
                if any(n in content for n in needles): out.append(_evidence("司法院裁判書開放 API",jid,doc.get("JTITLE") or jid,"近期裁判書全文包含查詢實體名稱；仍需人工確認當事人與案件關係。","https://data.judicial.gov.tw/",doc,"judgment"))
            except Exception: continue
        return out,{"status":"ok","checked":len(ids)}
    except Exception as exc:return [],{"status":"error","message":str(exc)}


def collect_public_evidence(company_name,people=None):
    needles=[_norm(company_name)]+[_norm(p) for p in (people or []) if p]; needles=[n for n in needles if len(n)>=2]
    evidence=[]; statuses={}
    evidence+=_collect_dataset("labor_penalties",needles,"勞動部／違反勞動法令事業單位","administrative_penalty"); statuses["裁罰"]="checked"
    for key,source,fact in [("scam_domains","165反詐騙諮詢專線_遭停止解析涉詐網站","anti_fraud_domain"),("fake_investment_sites","165反詐騙諮詢專線_假投資(博弈)網站","anti_fraud_site"),("scam_refutations","165反詐騙諮詢專線－詐騙闢謠專區","anti_fraud_refutation")]: evidence+=_collect_dataset(key,needles,source,fact)
    statuses["165"]="checked"; judicial,status=_judicial_recent(needles); evidence+=judicial; statuses["裁判書"]=status
    return {"evidence":evidence,"statuses":statuses,"note":"公開紀錄命中僅表示來源資料存在名稱／觀測值相符，不代表該實體已被認定違法或涉詐。"}
