#!/usr/bin/env python3
"""Upload local government source files to the clean T.E.I. Supabase project.

- Walks ~/taiwan-entity-intelligence/data/raw by default.
- Uploads to the private `tei-raw` bucket.
- Uses Supabase TUS resumable uploads for files > 6 MB.
- Uses the Storage REST upload endpoint for smaller files.
- Registers each uploaded object in public.source_files.
- Never uploads anything from a browser and never stores a service key in the repo.
"""

from __future__ import annotations

import csv
import getpass
import hashlib
import mimetypes
import os
import sys
from pathlib import Path
from typing import Iterable

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
    if "裁罰" in s or "penalt" in s or "違法" in s:
        return "penalties"
    if "公司" in s or "company" in s or "登記" in s:
        return "company"
    return "other"


def object_path(root: Path, path: Path) -> str:
    rel = path.relative_to(root)
    dataset = classify(rel)
    # Use POSIX separators because Storage object keys are URL-like paths.
    return f"{dataset}/{rel.as_posix()}"


def postgrest_headers(key: str) -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def register_file(key: str, dataset: str, obj_path: str, file_path: Path, digest: str) -> None:
    url = f"{SUPABASE_URL}/rest/v1/source_files"
    payload = {
        "dataset": dataset,
        "object_path": obj_path,
        "file_name": file_path.name,
        "format": file_path.suffix.lstrip(".").lower() or None,
        "size_bytes": file_path.stat().st_size,
        "sha256": digest,
        "status": "uploaded",
        "metadata": {"local_relative_path": file_path.as_posix()},
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
    # Lazy import so small-file uploads do not require tusclient.
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


def upload_one(key: str, root: Path, file_path: Path) -> None:
    rel = file_path.relative_to(root)
    obj_path = object_path(root, file_path)
    dataset = classify(rel)
    size = file_path.stat().st_size
    print(f"\n[{dataset}] {rel} ({size / 1024 / 1024:.2f} MB)")
    digest = sha256_file(file_path)
    print(f"SHA256: {digest}")
    if size > TUS_THRESHOLD:
        print("方式：TUS resumable upload")
        upload_tus(key, obj_path, file_path)
    else:
        print("方式：Storage REST upload")
        upload_small(key, obj_path, file_path)
    register_file(key, dataset, obj_path, file_path, digest)
    print("✅ 成功")


def iter_files(root: Path) -> Iterable[Path]:
    ignored_parts = {".git", "__pycache__"}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not any(part in ignored_parts for part in p.parts):
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
    print("T.E.I. CLEAN LOCAL SOURCE UPLOADER")
    print(f"Supabase: {SUPABASE_URL}")
    print(f"Bucket:   {BUCKET} (private)")
    print(f"來源：    {root}")
    print(f"檔案：    {len(files)} 個 / {total / 1024 / 1024:.2f} MB")
    print("\n這支程式只會上傳你本機 data/raw 內的檔案；不會把內容灌進 PostgreSQL。")
    confirm = input("\n開始上傳？輸入 YES：").strip()
    if confirm != "YES":
        print("已取消。")
        return 0

    key = getpass.getpass("貼上 T.E.I. 新專案的 service_role key（不會顯示）：").strip()
    if not key:
        print("沒有輸入 key。")
        return 1

    ok = failed = 0
    for idx, path in enumerate(files, 1):
        print(f"\n========== {idx}/{len(files)} ==========")
        try:
            upload_one(key, root, path)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"❌ 失敗：{exc}")

    print("\n==============================")
    print(f"完成：{ok} 成功 / {failed} 失敗 / 共 {len(files)}")
    if failed:
        print("失敗檔案不會影響其他檔案；再次執行可重試（使用 x-upsert）。")
        return 2
    print("✅ 全部成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
