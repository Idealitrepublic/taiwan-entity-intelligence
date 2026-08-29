#!/usr/bin/env python3
"""Upload files under data/raw to the project's private Supabase Storage bucket.

The script intentionally prompts for the Supabase service-role key at runtime so
that the secret is never saved in the repository or shell history.
"""

from __future__ import annotations

import argparse
import getpass
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SUPABASE_URL = "https://ohvrrqbogxyjivcigbpl.supabase.co"
BUCKET = "raw-data"


def upload_file(path: Path, root: Path, service_key: str) -> tuple[bool, str]:
    rel = path.relative_to(root).as_posix()
    object_path = urllib.parse.quote(rel, safe="/")
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{object_path}?upsert=true"
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    try:
        data = path.read_bytes()
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {service_key}",
                "apikey": service_key,
                "Content-Type": content_type,
                "x-upsert": "true",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        return True, body[:200]
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code}: {body[:300]}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload data/raw to Supabase Storage")
    parser.add_argument("--root", default="data/raw", help="Local raw-data folder")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"找不到資料夾：{root}")
        return 1

    files = [p for p in root.rglob("*") if p.is_file() and p.name != ".DS_Store"]
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
    print("")
    for i, p in enumerate(files[:20], 1):
        print(f"  {i:>3}. {p.relative_to(root)} ({p.stat().st_size / 1024:.1f} KB)")
    if len(files) > 20:
        print(f"  ... 其餘 {len(files) - 20} 個檔案")

    if not args.yes:
        answer = input("\n確定開始上傳？[y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("已取消，沒有上傳任何檔案。")
            return 0

    service_key = getpass.getpass("請貼上 Supabase service_role / secret key（輸入時不會顯示）：").strip()
    if not service_key:
        print("沒有輸入 key，已取消。")
        return 1

    ok = 0
    failed = 0
    for i, path in enumerate(files, 1):
        rel = path.relative_to(root)
        print(f"[{i}/{len(files)}] 上傳 {rel} ...", end=" ", flush=True)
        success, detail = upload_file(path, root, service_key)
        if success:
            ok += 1
            print("OK")
        else:
            failed += 1
            print(f"失敗：{detail}")

    print("\n完成。")
    print(f"成功：{ok}")
    print(f"失敗：{failed}")
    print(f"Supabase Bucket：https://ohvrrqbogxyjivcigbpl.supabase.co/storage/v1/object/{BUCKET}/")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
