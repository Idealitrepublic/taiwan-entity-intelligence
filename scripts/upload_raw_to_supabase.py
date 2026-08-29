#!/usr/bin/env python3
"""Upload files under data/raw to the project's private Supabase Storage bucket.

Handles Supabase's modern sb_secret_* keys, Storage object-name restrictions,
large files, retries, and resumable reruns. Original local paths are preserved
in manifest.json so sanitized Storage object names can always be mapped back.

For files larger than the configured single-object limit, the uploader stores
numbered parts under __chunks__/ so the original bytes can be reconstructed.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Tuple

SUPABASE_URL = "https://ohvrrqbogxyjivcigbpl.supabase.co"
BUCKET = "raw-data"
MANIFEST_NAME = "upload_manifest.json"
# Keep individual objects comfortably below the Supabase Free-plan 50 MB limit.
PART_SIZE = 40 * 1024 * 1024
MAX_RETRIES = 4


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def storage_safe_object_path(rel: str) -> str:
    """Generate an ASCII-only Storage key while preserving extension.

    Supabase Storage filenames only allow a restricted ASCII character set.
    Hashing avoids failures for Chinese filenames/directories and collisions.
    """
    rel_path = Path(rel)
    suffix = rel_path.suffix.lower()
    digest = hashlib.sha256(rel.encode("utf-8")).hexdigest()
    return f"raw/{digest}{suffix}"


def load_manifest(path: Path) -> Dict:
    if not path.exists():
        return {"source_root": "data/raw", "files": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"source_root": "data/raw", "files": {}}


def save_manifest(path: Path, manifest: Dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def request_upload(url: str, data: bytes, secret_key: str, content_type: str, retries: int = MAX_RETRIES) -> Tuple[bool, str]:
    last = ""
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url,
                data=data,
                method="POST",
                headers={
                    # Modern sb_secret_* keys are valid as apikey credentials.
                    "apikey": secret_key,
                    "Content-Type": content_type,
                    "x-upsert": "true",
                },
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            return True, body[:200]
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last = f"HTTP {exc.code}: {body[:300]}"
            # 4xx generally will not succeed by retrying.
            if exc.code not in {408, 429, 500, 502, 503, 504}:
                return False, last
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"

        if attempt < retries:
            time.sleep(min(15, 2 ** (attempt - 1)))
    return False, last or "unknown upload error"


def upload_one(path: Path, root: Path, secret_key: str, manifest: Dict) -> Tuple[bool, str]:
    rel = path.relative_to(root).as_posix()
    object_path = storage_safe_object_path(rel)
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    size = path.stat().st_size
    digest = sha256_bytes(path.read_bytes()) if size <= PART_SIZE else None

    current = manifest["files"].get(rel, {})
    if current.get("status") == "downloaded" and current.get("object_path"):
        return True, "already uploaded"

    base_url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/"

    if size <= PART_SIZE:
        data = path.read_bytes()
        ok, detail = request_upload(base_url + urllib.parse.quote(object_path, safe="/") + "?upsert=true", data, secret_key, content_type)
        if ok:
            manifest["files"][rel] = {
                "status": "downloaded",
                "object_path": object_path,
                "original_path": rel,
                "bytes": size,
                "sha256": digest or sha256_bytes(data),
            }
            return True, detail
        return False, detail

    # Large files: split into <=40 MB parts so Free-plan limits are respected.
    parts_dir = f"__chunks__/{hashlib.sha256(rel.encode('utf-8')).hexdigest()}"
    total_parts = (size + PART_SIZE - 1) // PART_SIZE
    with path.open("rb") as f:
        for index in range(total_parts):
            chunk = f.read(PART_SIZE)
            if not chunk:
                break
            part_path = f"{parts_dir}/part-{index + 1:05d}"
            ok, detail = request_upload(
                base_url + urllib.parse.quote(part_path, safe="/") + "?upsert=true",
                chunk,
                secret_key,
                "application/octet-stream",
            )
            if not ok:
                return False, f"part {index + 1}/{total_parts}: {detail}"
            print(f"    ✓ part {index + 1}/{total_parts} ({len(chunk):,} bytes)", flush=True)

    manifest["files"][rel] = {
        "status": "chunked",
        "object_path": parts_dir,
        "original_path": rel,
        "bytes": size,
        "parts": total_parts,
    }
    return True, f"stored as {total_parts} parts"


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload data/raw to Supabase Storage")
    parser.add_argument("--root", default="data/raw", help="Local raw-data folder")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    parser.add_argument("--retry-failed", action="store_true", help="Retry files previously marked failed")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"找不到資料夾：{root}")
        return 1

    manifest_path = root / MANIFEST_NAME
    manifest = load_manifest(manifest_path)

    files = [p for p in root.rglob("*") if p.is_file() and p.name not in {".DS_Store", MANIFEST_NAME}]
    files.sort()
    if not files:
        print(f"{root} 裡沒有可上傳的檔案。")
        return 1

    total = sum(p.stat().st_size for p in files)
    print("T.E.I. 原始資料 → Supabase Storage")
    print(f"本機資料夾：{root}")
    print(f"目標 Bucket：{BUCKET}（private）")
    print(f"檔案數：{len(files)}")
    print(f"總大小：約 {total / 1024 / 1024:.1f} MB")
    print("此版本會自動處理中文檔名、重試與大檔分片。")
    print()

    if not args.yes:
        answer = input("確定開始／繼續上傳？[y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("已取消，沒有上傳任何檔案。")
            return 0

    secret_key = getpass.getpass("請貼上 Supabase secret key（sb_secret_...；輸入時不會顯示）：").strip()
    if not secret_key:
        print("沒有輸入 key，已取消。")
        return 1

    ok = 0
    failed = 0
    skipped = 0

    for i, path in enumerate(files, 1):
        rel = path.relative_to(root).as_posix()
        old = manifest["files"].get(rel, {})
        if old.get("status") in {"downloaded", "chunked"} and not args.retry_failed:
            skipped += 1
            print(f"[{i}/{len(files)}] {rel} ... 已完成，跳過")
            continue

        print(f"[{i}/{len(files)}] 上傳 {rel} ...", flush=True)
        success, detail = upload_one(path, root, secret_key, manifest)
        if success:
            ok += 1
            print(f"  OK — {detail}")
        else:
            failed += 1
            manifest["files"][rel] = {"status": "failed", "original_path": rel, "error": detail}
            print(f"  失敗：{detail}")
        save_manifest(manifest_path, manifest)

    print("\n完成。")
    print(f"本次成功：{ok}")
    print(f"已存在／跳過：{skipped}")
    print(f"失敗：{failed}")
    print(f"Supabase Bucket：https://ohvrrqbogxyjivcigbpl.supabase.co/storage/v1/object/{BUCKET}/")
    print(f"上傳紀錄：{manifest_path}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
