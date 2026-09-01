#!/usr/bin/env python3
"""Retry failed local uploads only.

Rules:
- Never uploads PCC. PCC is treated as already uploaded and is excluded entirely.
- Ignore macOS .DS_Store files.
- Skip a file when its SHA256 is already registered in source_files.
- Also skip when the canonical SHA256 object already exists in Storage, even if metadata registration is missing.
- Upload large files with TUS and small files with Storage REST.
"""
from __future__ import annotations

import getpass
import hashlib
import mimetypes
import sys
from pathlib import Path

import requests

PROJECT_REF = "rztdbdurkjfrirsrrhtu"
BASE = f"https://{PROJECT_REF}.supabase.co"
TUS_BASE = f"https://{PROJECT_REF}.storage.supabase.co/storage/v1/upload/resumable"
BUCKET = "tei-raw"
ROOT = Path.home() / "taiwan-entity-intelligence" / "data" / "raw"
CHUNK = 6 * 1024 * 1024


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def dataset(rel: Path) -> str:
    s = str(rel).lower()
    if any(x in s for x in ("pcc", "採購", "招標", "決標")):
        return "pcc"
    if any(x in s for x in ("165", "詐", "fraud", "scam")):
        return "anti_fraud"
    if any(x in s for x in ("裁罰", "penalt", "違法")):
        return "penalties"
    if any(x in s for x in ("公司", "company", "登記")):
        return "company"
    return "other"


def headers(key: str) -> dict[str, str]:
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def registered_sha(key: str, digest: str) -> bool:
    r = requests.get(
        f"{BASE}/rest/v1/source_files",
        params={"sha256": f"eq.{digest}", "select": "id,object_path", "limit": "1"},
        headers=headers(key),
        timeout=60,
    )
    r.raise_for_status()
    return bool(r.json())


def storage_object_exists(key: str, obj: str) -> bool:
    r = requests.head(
        f"{BASE}/storage/v1/object/info/{BUCKET}/{obj}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=60,
    )
    if r.status_code == 200:
        return True
    if r.status_code in (400, 404):
        return False
    r.raise_for_status()
    return False


def upload(key: str, obj: str, path: Path) -> None:
    size = path.stat().st_size
    if size <= CHUNK:
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as f:
            r = requests.post(
                f"{BASE}/storage/v1/object/{BUCKET}/{obj}",
                headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": ctype, "x-upsert": "false"},
                data=f,
                timeout=300,
            )
        r.raise_for_status()
        return

    try:
        from tusclient import client as tus_client
    except ImportError as e:
        raise RuntimeError("缺少 tusclient；請先執行 python3 -m pip install tuspy") from e

    c = tus_client.TusClient(
        TUS_BASE,
        headers={
            "Authorization": f"Bearer {key}",
            "x-upsert": "false",
        },
    )
    meta = {
        "bucketName": BUCKET,
        "objectName": obj,
        "contentType": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        "cacheControl": "3600",
    }
    with path.open("rb") as f:
        c.uploader(file_stream=f, chunk_size=CHUNK, metadata=meta).upload()


def register(key: str, rel: Path, obj: str, digest: str) -> None:
    payload = {
        "dataset": dataset(rel),
        "object_path": obj,
        "file_name": rel.name,
        "format": rel.suffix.lstrip(".").lower() or None,
        "size_bytes": rel.stat().st_size,
        "sha256": digest,
        "status": "uploaded",
        "metadata": {"local_relative_path": rel.as_posix()},
    }
    r = requests.post(
        f"{BASE}/rest/v1/source_files",
        headers={**headers(key), "Prefer": "resolution=merge-duplicates,return=minimal"},
        json=payload,
        timeout=60,
    )
    r.raise_for_status()


def main() -> int:
    root = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else ROOT
    files = [
        p for p in sorted(root.rglob("*"))
        if p.is_file()
        and p.name != ".DS_Store"
        and not any(x in p.parts for x in (".git", "__pycache__"))
    ]
    key = getpass.getpass("貼上新 T.E.I. Supabase service_role key（不會顯示）：").strip()
    if not key:
        return 1

    ok = skip = fail = pcc_skip = 0
    candidates = []
    for p in files:
        rel = p.relative_to(root)
        if dataset(rel) == "pcc":
            pcc_skip += 1
            continue
        candidates.append(p)

    print(f"找到 {len(files)} 個檔案；排除 PCC：{pcc_skip} 個；待檢查：{len(candidates)} 個。")

    for i, p in enumerate(candidates, 1):
        rel = p.relative_to(root)
        try:
            digest = sha256(p)
            obj = f"{dataset(rel)}/{digest}{p.suffix.lower()}"
            if registered_sha(key, digest):
                print(f"[{i}/{len(candidates)}] SKIP 已有 metadata：{rel}")
                skip += 1
                continue
            if storage_object_exists(key, obj):
                print(f"[{i}/{len(candidates)}] SKIP Storage 已存在：{rel}")
                # Repair missing metadata without uploading again.
                register(key, rel, obj, digest)
                skip += 1
                continue

            print(f"[{i}/{len(candidates)}] RETRY：{rel}")
            upload(key, obj, p)
            register(key, rel, obj, digest)
            print("  ✅ 成功")
            ok += 1
        except Exception as e:
            print(f"  ❌ 失敗：{e}")
            fail += 1

    print(f"\n完成：新成功 {ok} / 已存在跳過 {skip} / PCC 排除 {pcc_skip} / 失敗 {fail}")
    return 2 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
