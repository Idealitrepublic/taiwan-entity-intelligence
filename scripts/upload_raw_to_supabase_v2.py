#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Upload data/raw to T.E.I. v2 Supabase Storage.

Usage:
  python3 scripts/upload_raw_to_supabase_v2.py

This uploader uses the legacy service_role JWT for Storage because the Storage
endpoint requires an Authorization header. The modern sb_secret_* key must not
be sent as Bearer JWT. The key is requested interactively and never stored.
"""
from __future__ import annotations

import getpass
import hashlib
import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SUPABASE_URL = "https://anntdcxttvffekslbrkj.supabase.co"
BUCKET = "raw-data"
ROOT = Path("data/raw")
PART_SIZE = 40 * 1024 * 1024
MAX_RETRIES = 4
EXCLUDE_DIRS = {"pcc", "company"}
MANIFEST = ROOT / "upload_manifest_v2.json"


def safe_path(rel: str) -> str:
    p = Path(rel)
    return f"raw/{hashlib.sha256(rel.encode('utf-8')).hexdigest()}{p.suffix.lower()}"


def load_manifest():
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"files": {}}


def save_manifest(m):
    tmp = MANIFEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, MANIFEST)


def put(url, data, api_key, content_type):
    last = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("apikey", api_key)
            req.add_header("Authorization", "Bearer " + api_key)
            req.add_header("Content-Type", content_type)
            req.add_header("x-upsert", "true")
            with urllib.request.urlopen(req, timeout=180) as r:
                return True, r.read().decode("utf-8", errors="replace")[:200]
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            last = f"HTTP {e.code}: {body[:300]}"
            if e.code not in {408, 429, 500, 502, 503, 504}:
                return False, last
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        if attempt < MAX_RETRIES:
            time.sleep(min(15, 2 ** (attempt - 1)))
    return False, last


def upload_file(path, root, key, manifest):
    rel = path.relative_to(root).as_posix()
    old = manifest["files"].get(rel, {})
    if old.get("status") in {"uploaded", "chunked"}:
        return True, "已完成"
    size = path.stat().st_size
    base = SUPABASE_URL + "/storage/v1/object/" + BUCKET + "/"
    if size <= PART_SIZE:
        obj = safe_path(rel)
        data = path.read_bytes()
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        ok, detail = put(base + urllib.parse.quote(obj, safe="/") + "?upsert=true", data, key, ctype)
        if ok:
            manifest["files"][rel] = {"status":"uploaded","object_path":obj,"bytes":size}
        return ok, detail

    chunk_dir = "__chunks__/" + hashlib.sha256(rel.encode("utf-8")).hexdigest()
    count = (size + PART_SIZE - 1) // PART_SIZE
    with path.open("rb") as f:
        for i in range(1, count + 1):
            chunk = f.read(PART_SIZE)
            if not chunk:
                break
            obj = f"{chunk_dir}/part-{i:05d}"
            ok, detail = put(base + urllib.parse.quote(obj, safe="/") + "?upsert=true", chunk, key, "application/octet-stream")
            if not ok:
                return False, f"part {i}/{count}: {detail}"
            print(f"    ✓ part {i}/{count} ({len(chunk):,} bytes)", flush=True)
    manifest["files"][rel] = {"status":"chunked","object_path":chunk_dir,"bytes":size,"parts":count}
    return True, f"{count} 個分片"


def main():
    root = ROOT.expanduser().resolve()
    files = []
    for p in root.rglob("*"):
        if not p.is_file() or p.name in {MANIFEST.name, ".DS_Store"}:
            continue
        rel_parts = set(p.relative_to(root).parts)
        if rel_parts & EXCLUDE_DIRS:
            continue
        files.append(p)
    files.sort()
    total = sum(p.stat().st_size for p in files)
    print("T.E.I. v2 原始資料 → Supabase Storage")
    print(f"專案：{SUPABASE_URL}")
    print(f"Bucket：{BUCKET}")
    print(f"排除：pcc/、company/")
    print(f"檔案數：{len(files)}")
    print(f"總大小：約 {total/1024/1024:.1f} MB")
    if input("確定開始上傳？[y/N] ").strip().lower() not in {"y","yes"}:
        return 0
    print("請輸入 T.E.I. v2 的 LEGACY service_role key（eyJ...）。不要輸入 sb_secret_...：")
    key = getpass.getpass("service_role key：").strip()
    if not key.startswith("eyJ"):
        print("錯誤：這個欄位需要 Legacy service_role JWT（通常以 eyJ 開頭）。")
        return 2
    manifest = load_manifest()
    ok = skipped = failed = 0
    for i, path in enumerate(files, 1):
        rel = path.relative_to(root).as_posix()
        old = manifest["files"].get(rel, {})
        if old.get("status") in {"uploaded","chunked"}:
            skipped += 1
            print(f"[{i}/{len(files)}] 跳過 {rel}")
            continue
        print(f"[{i}/{len(files)}] 上傳 {rel} ...", flush=True)
        success, detail = upload_file(path, root, key, manifest)
        if success:
            ok += 1
            print(f"  OK：{detail}")
        else:
            failed += 1
            manifest["files"][rel] = {"status":"failed","error":detail}
            print(f"  失敗：{detail}")
        save_manifest(manifest)
    print("\n完成")
    print(f"成功：{ok}")
    print(f"跳過：{skipped}")
    print(f"失敗：{failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
