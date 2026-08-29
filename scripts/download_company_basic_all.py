#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download the Ministry of Economic Affairs company basic-data API in batches.

Usage:
  python3 scripts/download_company_basic_all.py --end 1000 --fresh
  python3 scripts/download_company_basic_all.py --end 10000

The script writes JSONL incrementally and stores a checkpoint beside the file.
It intentionally stops when the API returns fewer rows than requested, instead
of assuming an exact total count from the dataset page.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request

API_ID = "5F64D864-61CB-4D0D-8AD9-492047CC1EA6"
API_URL = f"https://data.gcis.nat.gov.tw/od/data/api/{API_ID}"
PAGE_SIZE = 1000
DEFAULT_OUTPUT = "data/raw/company/company_basic.jsonl"
UA = "Taiwan-Entity-Intelligence/1.0"


def fetch(url: str, retries: int = 5):
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
            if not raw:
                raise RuntimeError("API 回傳空內容")
            return json.loads(raw.decode("utf-8-sig"))
        except Exception as exc:
            last = exc
            print(f"⚠️ 第 {attempt}/{retries} 次失敗：{exc}")
            if attempt < retries:
                time.sleep(min(20, attempt * 3))
    raise RuntimeError(f"API 重試失敗：{last}")


def rows(payload):
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("records", "data", "result", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        for value in payload.values():
            if isinstance(value, list):
                cand = [x for x in value if isinstance(x, dict)]
                if cand:
                    return cand
    raise RuntimeError("無法辨識 API 回應格式")


def checkpoint_path(out):
    return out + ".checkpoint.json"


def load_checkpoint(out):
    p = checkpoint_path(out)
    if not os.path.exists(p):
        return {"next_skip": 0, "total_downloaded": 0}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_checkpoint(out, next_skip, total):
    p = checkpoint_path(out)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"next_skip": next_skip, "total_downloaded": total, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=1_620_000)
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    cp = checkpoint_path(args.output)
    if args.fresh:
        for p in (args.output, cp):
            if os.path.exists(p):
                os.remove(p)

    state = load_checkpoint(args.output)
    skip = max(args.start, int(state.get("next_skip", args.start)))
    total = int(state.get("total_downloaded", 0))

    print("=" * 70)
    print("經濟部｜公司登記基本資料－應用一")
    print(f"API: {API_URL}")
    print(f"輸出: {args.output}")
    print(f"開始: {skip:,} / 結束上限: {args.end:,}")
    print("=" * 70)

    with open(args.output, "a", encoding="utf-8") as out:
        while skip < args.end:
            top = min(PAGE_SIZE, args.end - skip)
            url = f"{API_URL}?$format=json&$skip={skip}&$top={top}"
            print(f"下載 skip={skip:,}, top={top:,}", flush=True)
            payload = fetch(url)
            batch = rows(payload)
            if not batch:
                print("沒有更多資料，停止。")
                break
            for row in batch:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            count = len(batch)
            skip += count
            total += count
            save_checkpoint(args.output, skip, total)
            print(f"✓ 本批 {count:,} 筆；累計 {total:,} 筆", flush=True)
            if count < top:
                print("本批少於要求數量，視為資料尾端。")
                break
            time.sleep(0.2)

    print("=" * 70)
    print(f"完成。累計寫入：{total:,} 筆")
    print(f"資料：{args.output}")
    print(f"進度：{cp}")
    print("=" * 70)


if __name__ == "__main__":
    main()
