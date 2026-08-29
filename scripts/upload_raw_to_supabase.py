#!/usr/bin/env python3
from __future__ import annotations
import argparse, getpass, hashlib, json, mimetypes, os, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

SUPABASE_URL = "https://anntdcxttvffekslbrkj.supabase.co"
BUCKET = "raw-data"
MANIFEST_NAME = "upload_manifest_v2.json"
PART_SIZE = 40 * 1024 * 1024
MAX_RETRIES = 4
EXCLUDED_DIRS = {"pcc", "company"}

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def safe_path(rel: str) -> str:
    p = Path(rel)
    return f"raw/{hashlib.sha256(rel.encode('utf-8')).hexdigest()}{p.suffix.lower()}"

def load_manifest(path: Path):
    if not path.exists(): return {"files": {}}
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {"files": {}}

def save_manifest(path: Path, m):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)

def upload(url, data, key, content_type):
    last=''
    for attempt in range(1, MAX_RETRIES+1):
        try:
            req=urllib.request.Request(url,data=data,method='POST',headers={'apikey':key,'Content-Type':content_type,'x-upsert':'true'})
            with urllib.request.urlopen(req,timeout=180) as r: return True, r.read().decode('utf-8','replace')[:200]
        except urllib.error.HTTPError as e:
            last=f'HTTP {e.code}: {e.read().decode("utf-8","replace")[:300]}'
            if e.code not in {408,429,500,502,503,504}: return False,last
        except Exception as e: last=f'{type(e).__name__}: {e}'
        time.sleep(min(15,2**(attempt-1)))
    return False,last

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='data/raw'); ap.add_argument('--yes',action='store_true'); args=ap.parse_args()
    root=Path(args.root).expanduser().resolve()
    if not root.is_dir(): print(f'找不到資料夾：{root}'); return 1
    files=[p for p in root.rglob('*') if p.is_file() and p.name not in {'.DS_Store',MANIFEST_NAME} and not any(part.lower() in EXCLUDED_DIRS for part in p.relative_to(root).parts)]
    files.sort(); total=sum(p.stat().st_size for p in files)
    print('T.E.I. v2 原始資料 → Supabase Storage'); print(f'專案：https://anntdcxttvffekslbrkj.supabase.co'); print(f'Bucket：{BUCKET}（private）'); print(f'排除：pcc/、company/'); print(f'檔案數：{len(files)}'); print(f'總大小：約 {total/1024/1024:.1f} MB')
    if not args.yes and input('確定開始上傳？[y/N] ').strip().lower() not in {'y','yes'}: return 0
    key=getpass.getpass('請貼上 T.E.I. v2 Supabase secret key（sb_secret_...）：').strip()
    if not key: return 1
    m=load_manifest(root/MANIFEST_NAME); ok=failed=skipped=0; base=f'{SUPABASE_URL}/storage/v1/object/{BUCKET}/'
    for i,p in enumerate(files,1):
        rel=p.relative_to(root).as_posix(); old=m['files'].get(rel,{})
        if old.get('status')=='uploaded': skipped+=1; continue
        print(f'[{i}/{len(files)}] {rel}',flush=True); size=p.stat().st_size
        if size<=PART_SIZE:
            data=p.read_bytes(); obj=safe_path(rel); good,detail=upload(base+urllib.parse.quote(obj,safe='/')+'?upsert=true',data,key,mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
            if good: m['files'][rel]={'status':'uploaded','object_path':obj,'bytes':size,'sha256':sha256_bytes(data)}; ok+=1; print('  ✓ 完成')
            else: failed+=1; m['files'][rel]={'status':'failed','error':detail}; print('  ✗ '+detail)
        else:
            chunk_dir='__chunks__/'+hashlib.sha256(rel.encode()).hexdigest(); parts=(size+PART_SIZE-1)//PART_SIZE; good=True
            with p.open('rb') as f:
                for n in range(1,parts+1):
                    c=f.read(PART_SIZE); po=f'{chunk_dir}/part-{n:05d}'; good,detail=upload(base+urllib.parse.quote(po,safe='/')+'?upsert=true',c,key,'application/octet-stream')
                    if not good: print('  ✗ '+detail); break
                    print(f'  ✓ part {n}/{parts}',flush=True)
            if good: m['files'][rel]={'status':'uploaded','object_path':chunk_dir,'bytes':size,'parts':parts}; ok+=1
            else: failed+=1; m['files'][rel]={'status':'failed','error':detail}
        save_manifest(root/MANIFEST_NAME,m)
    print(f'\n完成：成功 {ok}；跳過 {skipped}；失敗 {failed}')
    return 0 if failed==0 else 2
if __name__=='__main__': raise SystemExit(main())