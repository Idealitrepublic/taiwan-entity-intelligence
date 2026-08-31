#!/usr/bin/env python3
"""Remove duplicate objects in tei-raw when the same SHA256 was uploaded more than once.

Keeps one canonical object per SHA256, preferring <dataset>/<sha256>.<ext> or <dataset>/<sha256>.
Deletes objects through the Storage API, then removes their source_files metadata rows.
"""
from __future__ import annotations
import getpass
import re
import requests

PROJECT_REF = "rztdbdurkjfrirsrrhtu"
BASE = f"https://{PROJECT_REF}.supabase.co"
BUCKET = "tei-raw"

def hdr(key):
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

def canonical(paths, sha):
    plain = [p for p in paths if re.fullmatch(rf"[^/]+/{re.escape(sha)}(?:\.[A-Za-z0-9]+)?", p)]
    return sorted(plain)[0] if plain else sorted(paths)[0]

def main():
    key = getpass.getpass("貼上新 T.E.I. Supabase service_role key（不會顯示）：").strip()
    if not key:
        return 1
    r = requests.get(f"{BASE}/rest/v1/source_files", params={"select":"id,sha256,object_path", "sha256":"not.is.null", "order":"sha256.asc,object_path.asc", "limit":"100000"}, headers=hdr(key), timeout=120)
    r.raise_for_status()
    rows = r.json()
    groups = {}
    for row in rows:
        groups.setdefault(row["sha256"], []).append(row)
    duplicates = [(sha, rs) for sha, rs in groups.items() if len(rs) > 1]
    print(f"發現 {len(duplicates)} 組重複 SHA256。")
    to_delete = []
    db_delete_ids = []
    for sha, rs in duplicates:
        paths = [x["object_path"] for x in rs]
        keep = canonical(paths, sha)
        for row in rs:
            if row["object_path"] != keep:
                to_delete.append(row["object_path"])
                db_delete_ids.append(row["id"])
        print(f"保留 {keep}；刪除 {len(rs)-1} 個重複")
    if not to_delete:
        print("沒有需要刪除的重複檔案。")
        return 0
    print(f"\n即將永久刪除 {len(to_delete)} 個 Storage 物件。")
    confirm = input("輸入 DELETE DUPLICATES 確認：").strip()
    if confirm != "DELETE DUPLICATES":
        print("已取消。")
        return 0
    for start in range(0, len(to_delete), 1000):
        batch = to_delete[start:start+1000]
        rr = requests.delete(f"{BASE}/storage/v1/object/{BUCKET}", headers={**hdr(key), "Content-Type":"application/json"}, json=batch, timeout=120)
        rr.raise_for_status()
        print(f"Storage 已刪除 {start+len(batch)}/{len(to_delete)}")
    # Delete metadata only after Storage deletion succeeds.
    for row_id in db_delete_ids:
        rr = requests.delete(f"{BASE}/rest/v1/source_files", params={"id":f"eq.{row_id}"}, headers=hdr(key), timeout=60)
        rr.raise_for_status()
    print(f"✅ 完成：刪除 {len(to_delete)} 個重複檔案及其 metadata。")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
