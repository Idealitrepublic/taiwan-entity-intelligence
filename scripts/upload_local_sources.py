#!/usr/bin/env python3
"""Idempotent uploader for the clean T.E.I. Supabase project.

PCC is intentionally excluded because its already-uploaded files must never be
re-uploaded by the local-source repair job.  Only non-PCC files missing from
both source_files and Storage are candidates for upload.
"""
from __future__ import annotations
import getpass, hashlib, mimetypes, sys
from pathlib import Path
from typing import Iterable, Any
import requests

PROJECT_REF = "rztdbdurkjfrirsrrhtu"
BASE = f"https://{PROJECT_REF}.supabase.co"
TUS_BASE = f"{BASE}/storage/v1/upload/resumable"
BUCKET = "tei-raw"
ROOT = Path.home() / "taiwan-entity-intelligence" / "data" / "raw"
CHUNK = 6 * 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def classify(rel: Path) -> str:
    s = str(rel).lower()
    if any(x in s for x in ("pcc", "採購", "招標", "決標")): return "pcc"
    if any(x in s for x in ("165", "詐", "fraud", "scam")): return "anti_fraud"
    if any(x in s for x in ("裁罰", "penalt", "違法", "勞動")): return "penalties"
    if any(x in s for x in ("公司", "company", "登記")): return "company"
    return "other"


def headers(key: str) -> dict[str, str]:
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def fetch_registered(key: str) -> dict[str, dict[str, Any]]:
    r = requests.get(
        f"{BASE}/rest/v1/source_files",
        params={"select":"object_path,file_name,sha256,status,metadata", "sha256":"not.is.null", "limit":"100000"},
        headers=headers(key), timeout=120,
    )
    r.raise_for_status()
    out = {}
    for row in r.json():
        sha = row.get("sha256")
        if sha: out[sha] = row
    return out


def storage_exists(key: str, obj: str) -> bool:
    r = requests.head(f"{BASE}/storage/v1/object/{BUCKET}/{obj}", headers=headers(key), timeout=60)
    if r.status_code in (200, 206): return True
    if r.status_code == 404: return False
    q = requests.get(f"{BASE}/storage/v1/object/info/{BUCKET}/{obj}", headers=headers(key), timeout=60)
    return q.status_code == 200


def upload_small(key: str, obj: str, path: Path) -> None:
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as f:
        r = requests.post(f"{BASE}/storage/v1/object/{BUCKET}/{obj}", headers={**headers(key), "Content-Type":ctype, "x-upsert":"false"}, data=f, timeout=300)
    r.raise_for_status()


def upload_tus(key: str, obj: str, path: Path) -> None:
    try:
        from tusclient import client as tus_client
    except ImportError as exc:
        raise RuntimeError("缺少 tusclient；請先執行 python3 -m pip install tuspy") from exc
    c = tus_client.TusClient(TUS_BASE, headers={"Authorization":f"Bearer {key}", "apikey":key, "x-upsert":"false"})
    meta = {"bucketName":BUCKET, "objectName":obj, "contentType":mimetypes.guess_type(path.name)[0] or "application/octet-stream", "cacheControl":"3600"}
    with path.open("rb") as f:
        c.uploader(file_stream=f, chunk_size=CHUNK, metadata=meta).upload()


def register(key: str, rel: Path, obj: str, digest: str) -> None:
    payload = {"dataset":classify(rel), "object_path":obj, "file_name":rel.name, "format":rel.suffix.lstrip('.').lower() or None, "size_bytes":rel.stat().st_size, "sha256":digest, "status":"uploaded", "metadata":{"local_relative_path":rel.as_posix()}}
    r = requests.post(f"{BASE}/rest/v1/source_files", headers={**headers(key), "Content-Type":"application/json", "Prefer":"resolution=merge-duplicates,return=minimal"}, json=payload, timeout=60)
    r.raise_for_status()


def iter_files(root: Path) -> Iterable[Path]:
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name in {".DS_Store", "Thumbs.db"}: continue
        if any(x in p.parts for x in (".git", "__pycache__")): continue
        yield p


def main() -> int:
    root = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else ROOT
    if not root.exists(): print(f"找不到資料夾：{root}"); return 1
    files = list(iter_files(root))
    print(f"找到 {len(files)} 個檔案。PCC 全部跳過，只修補其他資料的缺失檔案。")
    key = getpass.getpass("貼上新 T.E.I. Supabase service_role key（不會顯示）：").strip()
    if not key: return 1
    registry = fetch_registered(key)
    seen: set[str] = set()
    uploaded = skipped = failed = 0
    for i, path in enumerate(files, 1):
        rel = path.relative_to(root)
        try:
            ds = classify(rel)
            digest = sha256_file(path)
            if digest in seen:
                print(f"[{i}/{len(files)}] SKIP 本批重複：{rel}"); skipped += 1; continue
            seen.add(digest)
            if ds == "pcc":
                print(f"[{i}/{len(files)}] SKIP PCC（永不重傳）：{rel}"); skipped += 1; continue
            if digest in registry:
                print(f"[{i}/{len(files)}] SKIP 已存在：{rel}"); skipped += 1; continue
            obj = f"{ds}/{digest}{path.suffix.lower()}"
            if storage_exists(key, obj):
                print(f"[{i}/{len(files)}] SKIP Storage 已存在：{rel}")
                register(key, rel, obj, digest); registry[digest] = {"status":"uploaded"}; skipped += 1; continue
            print(f"[{i}/{len(files)}] 修補：{rel}")
            if path.stat().st_size > CHUNK: upload_tus(key, obj, path)
            else: upload_small(key, obj, path)
            register(key, rel, obj, digest); registry[digest] = {"status":"uploaded"}
            print("  ✅ 成功"); uploaded += 1
        except Exception as exc:
            print(f"  ❌ 失敗：{exc}"); failed += 1
    print(f"\n完成：新上傳 {uploaded} / 跳過 {skipped} / 失敗 {failed}")
    return 2 if failed else 0

if __name__ == "__main__": raise SystemExit(main())
