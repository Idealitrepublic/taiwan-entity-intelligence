#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lean ingestion for T.E.I. v2.

Reads already-downloaded CSV/JSON files from data/raw and sends only fields
needed for search, linking, and risk analysis. It intentionally does NOT send
raw payloads to Postgres; originals stay in Supabase Storage.
"""
from __future__ import annotations
import argparse, csv, getpass, hashlib, json, re, urllib.error, urllib.parse, urllib.request
from pathlib import Path

SUPABASE_URL = "https://anntdcxttvffekslbrkj.supabase.co"
ROOT = Path("data/raw")
BATCH = 500


def norm(v): return re.sub(r"[\\s　]+", "", str(v or "")).strip()
def rid(*parts): return hashlib.sha256("|".join(norm(x) for x in parts).encode()).hexdigest()

def headers(key):
    h = {"apikey": key, "Content-Type": "application/json", "Accept": "application/json"}
    if key.startswith("eyJ"):
        h["Authorization"] = "Bearer " + key
    return h

def post(table, rows, key, conflict=None):
    if not rows: return
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if conflict: url += "?on_conflict=" + urllib.parse.quote(conflict, safe=",")
    for i in range(0, len(rows), BATCH):
        data = json.dumps(rows[i:i+BATCH], ensure_ascii=False).encode()
        req = urllib.request.Request(url, data=data, method="POST", headers={**headers(key), "Prefer":"resolution=merge-duplicates,return=minimal"})
        with urllib.request.urlopen(req, timeout=180) as r: r.read()

def first(row, names):
    m = {norm(k).lower(): v for k,v in row.items()}
    for n in names:
        v = m.get(norm(n).lower())
        if v not in (None, ""): return str(v).strip()
    return ""

def rows_from(path):
    if path.suffix.lower() == ".json":
        data=json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data,list): return data
        for k in ("data","records","items","result"):
            if isinstance(data.get(k),list): return data[k]
        return [data]
    encs=("utf-8-sig","cp950","big5","utf-8")
    for enc in encs:
        try:
            with path.open("r",encoding=enc,newline="") as f:
                sample=f.read(8192); f.seek(0)
                try: dialect=csv.Sniffer().sniff(sample,delimiters=",\\t;")
                except csv.Error: dialect=csv.excel
                return list(csv.DictReader(f,dialect=dialect))
        except UnicodeDecodeError: pass
    raise RuntimeError(f"無法讀取：{path}")

def classify(path):
    s=str(path).lower()
    if any(k in s for k in ("董監事","董事","監察人","director")): return "directors"
    if any(k in s for k in ("165","反詐","詐騙","假投資","twnic")): return "fraud"
    if any(k in s for k in ("裁罰","勞動法","環境部","金管會","證券期貨","penalt")): return "penalties"
    return "unknown"

def files_for(root, source):
    out=[]
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".csv",".json") and "company" not in p.parts and "pcc" not in p.parts:
            if classify(p)==source: out.append(p)
    return sorted(out)

def ingest_directors(paths,key):
    people={}; companies={}; rels={}; total=0
    for path in paths:
        source="director:"+path.name
        for idx,row in enumerate(rows_from(path),1):
            total+=1
            uniform=first(row,["統一編號","統編","公司統編"])
            company=first(row,["公司名稱","公司名","公司"])
            person=first(row,["姓名","董事姓名","監察人姓名"])
            title=first(row,["職稱","職務","職位"])
            if not person: continue
            pid=rid("person",person)
            people[pid]={"name":person,"normalized_name":norm(person),"source_name":"董監事資料集","source_record_id":pid}
            if uniform and company:
                companies[uniform]={"uniform_number":uniform,"company_name":company,"source_name":"董監事資料集","source_record_id":rid("company",uniform)}
                keyrel=(uniform,pid,title or "董監事")
                rels[keyrel]={"source_entity_type":"company","source_entity_id":uniform,"relationship_type":title or "董監事","target_entity_type":"person","target_entity_id":pid,"confidence":1,"evidence_ids":[],"source_name":source,"source_record_id":str(idx)}
    post("people",list(people.values()),key,"source_name,source_record_id")
    post("companies",list(companies.values()),key,"uniform_number")
    post("relationships",list(rels.values()),key,None)
    return total,len(people),len(companies),len(rels)

def ingest_fraud(paths,key):
    out={}; total=0
    for path in paths:
        source="fraud165:"+path.name
        for idx,row in enumerate(rows_from(path),1):
            total+=1
            domain=first(row,["網址","網域","詐騙網址","domain","URL"])
            name=first(row,["公司名稱","公司名","名稱","entity_name"])
            uniform=first(row,["統一編號","統編","公司統編"])
            if not (domain or name or uniform): continue
            x=rid(source,idx,domain,name,uniform)
            out[x]={"record_id":x,"dataset_id":"165","record_type":"fraud_warning","entity_name":name,"uniform_number":uniform,"domain":domain,"source_url":first(row,["來源網址","source_url"]),"source_record_id":str(idx)}
    post("fraud_records",list(out.values()),key,"record_id")
    return total,len(out)

def ingest_penalties(paths,key):
    out={}; total=0
    for path in paths:
        source="penalty:"+path.name
        for idx,row in enumerate(rows_from(path),1):
            total+=1
            party=first(row,["公司名稱","事業單位名稱","廠商名稱","機構名稱","名稱"])
            uniform=first(row,["統一編號","統編","公司統編","證券代號"])
            agency=first(row,["機關","主管機關","裁處機關"])
            date=first(row,["裁罰日期","處分日期","公告日期","裁處日期"])
            violation=first(row,["違反法令","違反法規","違規事實","違規內容","違反事項"])
            basis=first(row,["法規依據","法令依據"])
            fine=first(row,["罰鍰","罰鍰金額","處罰金額"])
            n=re.sub(r"[^0-9.-]","",fine)
            x=rid(source,idx,party,uniform,violation)
            out[x]={"case_id":x,"agency_name":agency,"party_name":party,"uniform_number":uniform,"penalty_date":date or None,"legal_basis":basis,"violation":violation,"fine_amount":float(n) if n else None,"source_url":first(row,["來源網址","source_url","URL"]),"source_record_id":str(idx)}
    post("penalties",list(out.values()),key,"case_id")
    return total,len(out)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",choices=["directors","fraud","penalties","all"],required=True)
    args=ap.parse_args()
    root=ROOT.resolve()
    key=getpass.getpass("T.E.I. v2 Supabase key（sb_secret_... 或 legacy service_role）：").strip()
    if not key: raise SystemExit("沒有輸入 key")
    total=0
    for source in ([args.source] if args.source!="all" else ["directors","fraud","penalties"]):
        fs=files_for(root,source); print(f"[{source}] {len(fs)} 個檔案")
        if source=="directors":
            r,p,c,rel=ingest_directors(fs,key); print(f"  董監事：讀取 {r:,}；人物 {p:,}；公司 {c:,}；關係 {rel:,}")
            total+=r
        elif source=="fraud":
            r,w=ingest_fraud(fs,key); print(f"  165：讀取 {r:,}；寫入 {w:,}"); total+=r
        else:
            r,w=ingest_penalties(fs,key); print(f"  裁罰：讀取 {r:,}；寫入 {w:,}"); total+=r
    print(f"完成：共讀取 {total:,} 列")

if __name__=="__main__": main()
