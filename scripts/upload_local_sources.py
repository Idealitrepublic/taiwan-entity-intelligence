#!/usr/bin/env python3
"""Upload local government source files to the clean T.E.I. Supabase project.

The original uploader used the original Chinese/local path as the Storage object
key. Supabase Storage object names should use safe object-key characters, and
TUS metadata is especially sensitive to non-ASCII paths. This version therefore
uses an ASCII-only SHA256-derived object key while retaining the original local
path in `source_files.metadata`.

- Walks ~/taiwan-entity-intelligence/data/raw by default.
- Ignores macOS .DS_Store files and common build/cache directories.
- Uploads to the private `tei-raw` bucket.
- Uses Supabase TUS resumable uploads for files > 6 MB.
- Uses the Storage REST upload endpoint for smaller files.
- Registers each uploaded object in public.source_files.
- On rerun, skips files already registered with the same local path + SHA256.
- Never uploads anything from a browser and never stores a service key in the repo.
"""

from __future__ import annotations

import getpass
import hashlib
import mimetypes
import sys
from pathlib import Path
from typing import Any, Iterable

import requests

PROJECT_REF = "rztdbdurkjfrirsrrhtu"
SUPABASE_URL = f"https://{PROJECT_REF}.supabase.co"
STORAGE_TUS_URL = f"https://{PROJECT_REF}.storage.supabase.co/storage/v1/upload/resumable"
BUCKET = "tei-raw"
DEFAULT_ROOT = Path.home() / "taiwan-entity-intelligence" / "data" / "raw"
TUS_THRESHOLD = 6 * 1024 * 1024
TUS_CHUNK = 6 * 1024 * 1024


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def classify(rel: Path) -> str:
    s = str(rel).lower()
    if "pcc" in s or "採購" in s or "招標" in s or "決標" in s:
        return "pcc"
    if "165" in s or "詐" in s or "fraud" in s or "scam" in s:
        return "anti_fraud"
    if "裁罰" in s or "penalt" in s or "違法" in s or "勞動" in s:
        return "penalties"
    if "公司" in s or "company" in s or "登記" in s:
        return "company"
    return "other"


def object_path(root: Path, path: Path, digest: str) -> str:
    """Create an ASCII-only, collision-resistant Storage object key."""
    rel = path.relative_to(root)
    dataset = classify(rel)
    suffix = path.suffix.lower()
    return f"{dataset}/{digest}{suffix}"


def postgrest_headers(key: str) -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def fetch_registered(key: str) -> dict[str, dict[str, Any]]:
    """Load already registered local files once to avoid re-uploading them."""
    url = f"{SUPABASE_URL}/rest/v1/source_files"
    params = {
        "select": "object_path,file_name,size_bytes,sha256,status,metadata",
        "limit": "5000",
    }
    r = requests.get(url, headers=postgrest_headers(key), params=params, timeout=60)
    r.raise_for_status()
    rows = r.json()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        meta = row.get("metadata") or {}
        local_rel = meta.get("local_relative_path")
        sha = row.get("sha256")
        if local_rel and sha:
            out[f"{local_rel}|{sha}"] = row
    return out


def register_file(key: str, dataset: str, obj_path: str, file_path: Path, digest: str, root: Path) -> None:
    url = f"{SUPABASE_URL}/rest/v1/source_files"
    rel = file_path.relative_to(root).as_posix()
    payload = {
        "dataset": dataset,
        "object_path": obj_path,
        "file_name": file_path.name,
        "format": file_path.suffix.lstrip(".").lower() or None,
        "size_bytes": file_path.stat().st_size,
        "sha256": digest,
        "status": "uploaded",
        "metadata": {"local_relative_path": rel},
    }
    r = requests.post(
        url,
        headers={**postgrest_headers(key), "Prefer": "resolution=merge-duplicates,return=minimal"},
        json=payload,
        timeout=60,
    )
    r.raise_for_status()


def upload_small(key: str, obj_path: str, file_path: Path) -> None:
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{obj_path}"
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    with file_path.open("rb") as f:
        r = requests.post(
            url,
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            data=f,
            timeout=300,
        )
    r.raise_for_status()


def upload_tus(key: str, obj_path: str, file_path: Path) -> None:
    try:
        from tusclient import client as tus_client
    except ImportError as exc:
        raise RuntimeError(
            "缺少 tusclient。請先執行：python3 -m pip install tuspy"
        ) from exc

    client = tus_client.TusClient(
        STORAGE_TUS_URL,
        headers={
            "Authorization": f"Bearer {key}",
            "apikey": key,
            "x-upsert": "true",
        },
    )
    metadata = {
        "bucketName": BUCKET,
        "objectName": obj_path,
        "contentType": mimetypes.guess_type(file_path.name)[0] or "application/octet-stream",
        "cacheControl": "3600",
    }
    with file_path.open("rb") as stream:
        uploader = client.uploader(
            file_stream=stream,
            chunk_size=TUS_CHUNK,
            metadata=metadata,
        )
        uploader.upload()


def upload_one(key: str, root: Path, file_path: Path, registered: dict[str, dict[str, Any]]) -> str:
    rel = file_path.relative_to(root)
    size = file_path.stat().st_size
    digest = sha256_file(file_path)
    registered_key = f"{rel.as_posix()}|{digest}"

    if registered_key in registered and registered[registered_key].get("status") == "uploaded":
        print(f"\n[SKIP] {rel}：已上傳且 SHA256 相同")
        return "skipped"

    dataset = classify(rel)
    obj_path = object_path(root, file_path, digest)
    print(f"\n[{dataset}] {rel} ({size / 1024 / 1024:.2f} MB)")
    print(f"SHA256: {digest}")
    print(f"Storage key: {obj_path}")
    if size > TUS_THRESHOLD:
        print("方式：TUS resumable upload")
        upload_tus(key, obj_path, file_path)
    else:
        print("方式：Storage REST upload")
        upload_small(key, obj_path, file_path)
    register_file(key, dataset, obj_path, file_path, digest, root)
    print("✅ 成功")
    return "uploaded"


def iter_files(root: Path) -> Iterable[Path]:
    ignored_parts = {".git", "__pycache__"}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.name == ".DS_Store":
            continue
        if any(part in ignored_parts for part in p.parts):
            continue
        yield p


def main() -> int:
    root = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_ROOT
    if not root.exists():
        print(f"找不到資料夾：{root}")
        return 1

    files = list(iter_files(root))
    if not files:
        print(f"資料夾沒有檔案：{root}")
        return 1

    total = sum(p.stat().st_size for p in files)
    print("T.E.I. CLEAN LOCAL SOURCE UPLOADER v2")
    print(f"Supabase: {SUPABASE_URL}")
    print(f"Bucket:   {BUCKET} (private)")
    print(f"來源：    {root}")
    print(f"檔案：    {len(files)} 個 / {total / 1024 / 1024:.2f} MB")
    print("\n本版本會：")
    print("1. 忽略 macOS .DS_Store")
    print("2. 使用 ASCII-only SHA256 Storage key，避免中文檔名造成 400")
    print("3. 已成功上傳且 SHA256 相同的檔案自動跳過")
    print("4. 原始中文檔名與本機相對路徑仍保留在 source_files metadata")
    confirm = input("\n開始上傳？輸入 YES：").strip()
    if confirm != "YES":
        print("已取消。")
        return 0

    key = getpass.getpass("貼上 T.E.I. 新專案的 service_role key（不會顯示）：").strip()
    if not key:
        print("沒有輸入 key。")
        return 1

    try:
        registered = fetch_registered(key)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ 無法讀取 source_files：{exc}")
        return 1

    uploaded = skipped = failed = 0
    for idx, path in enumerate(files, 1):
        print(f"\n========== {idx}/{len(files)} ==========")
        try:
            result = upload_one(key, root, path, registered)
            if result == "uploaded":
                uploaded += 1
                rel = path.relative_to(root).as_posix()
                digest = sha256_file(path)
                registered[f"{rel}|{digest}"] = {"status": "uploaded"}
            else:
                skipped += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"❌ 失敗：{exc}")

    print("\n==============================")
    print(f"完成：{uploaded} 新上傳 / {skipped} 跳過 / {failed} 失敗 / 共 {len(files)}")
    if failed:
        print("失敗檔案可直接再次執行本程式；已成功檔案會自動跳過。")
        return 2
    print("✅ 全部需要的檔案都已處理")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
