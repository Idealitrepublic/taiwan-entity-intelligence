#!/usr/bin/env python3
"""Download PCC's official half-month tender/award OpenData files.

The PCC OpenData page is a catalog; the actual national tender/award data are
published as half-month XML files behind the official downloadFile endpoint.
This downloader uses that stable file naming scheme directly instead of
scraping the catalog HTML.

Source catalog:
  https://web.pcc.gov.tw/tps/tp/OpenData/showList

Official file endpoint:
  https://web.pcc.gov.tw/tps/tp/OpenData/downloadFile?fileName=...

File names:
  tender_YYYYMM01.xml
  tender_YYYYMM02.xml
  award_YYYYMM01.xml
  award_YYYYMM02.xml

The script defaults to the full public period beginning 2015-04 and ending
at the current date. It is resumable and stores a manifest with URL, status,
HTTP status, bytes and SHA-256. Missing/unpublished half-month files are
recorded and skipped rather than treated as successful downloads.

Usage:
  python3 scripts/download_pcc_opendata_full.py
  python3 scripts/download_pcc_opendata_full.py --from-month 2025-01
  python3 scripts/download_pcc_opendata_full.py --from-month 2026-08 --to-month 2026-08
  python3 scripts/download_pcc_opendata_full.py --types award

No extra Python package is required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "pcc" / "xml"
MANIFEST = OUT / "manifest.json"
BASE_URL = "https://web.pcc.gov.tw/tps/tp/OpenData/downloadFile"
DEFAULT_FROM = "2015-04"


def parse_month(value: str) -> tuple[int, int]:
    try:
        year, month = (int(x) for x in value.split("-", 1))
        if not 1 <= month <= 12:
            raise ValueError
        return year, month
    except Exception as exc:
        raise argparse.ArgumentTypeError("月份請使用 YYYY-MM，例如 2026-08") from exc


def month_iter(start: tuple[int, int], end: tuple[int, int]):
    y, m = start
    ey, em = end
    while (y, m) <= (ey, em):
        yield y, m
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1


def halfmonth_targets(start: tuple[int, int], end: tuple[int, int], kinds: tuple[str, ...]):
    today = date.today()
    for y, m in month_iter(start, end):
        for half in (1, 2):
            period_start = date(y, m, 1 if half == 1 else 16)
            if period_start > today:
                continue
            for kind in kinds:
                filename = f"{kind}_{y:04d}{m:02d}{half:02d}.xml"
                yield kind, y, m, half, filename


def load_manifest() -> dict:
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"source": "PCC OpenData half-month XML", "files": {}}


def save_manifest(manifest: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(MANIFEST)


def fetch_one(item, manifest: dict, delay: float = 0.0) -> dict:
    kind, year, month, half, filename = item
    url = BASE_URL + "?" + urlencode({"fileName": filename})
    target_dir = OUT / kind
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename

    existing = manifest["files"].get(filename, {})
    if target.exists() and target.stat().st_size > 0 and existing.get("status") == "downloaded":
        return {"filename": filename, "status": "exists", "bytes": target.stat().st_size, "url": url}

    req = Request(
        url,
        headers={
            "User-Agent": "TaiwanEntityIntelligence/1.0",
            "Accept": "application/xml,text/xml,*/*;q=0.8",
        },
    )

    try:
        with urlopen(req, timeout=90) as response:
            status = getattr(response, "status", 200)
            body = response.read()
            content_type = (response.headers.get("content-type") or "").lower()

        # Reject HTML login/error pages even if the upstream returns HTTP 200.
        prefix = body[:256].lstrip().lower()
        if "text/html" in content_type or prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html"):
            return {"filename": filename, "status": "html_response", "http": status, "bytes": len(body), "url": url}

        if not body:
            return {"filename": filename, "status": "empty", "http": status, "bytes": 0, "url": url}

        digest = hashlib.sha256(body).hexdigest()
        tmp = target.with_suffix(target.suffix + ".part")
        tmp.write_bytes(body)
        tmp.replace(target)
        result = {
            "filename": filename,
            "status": "downloaded",
            "http": status,
            "bytes": len(body),
            "sha256": digest,
            "url": url,
            "local_path": str(target.relative_to(ROOT)),
        }
        if delay:
            time.sleep(delay)
        return result

    except HTTPError as exc:
        return {"filename": filename, "status": "http_error", "http": exc.code, "url": url}
    except URLError as exc:
        return {"filename": filename, "status": "network_error", "error": str(exc.reason), "url": url}
    except TimeoutError:
        return {"filename": filename, "status": "timeout", "url": url}
    except Exception as exc:
        return {"filename": filename, "status": "error", "error": str(exc)[:500], "url": url}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-month", default=DEFAULT_FROM, type=parse_month)
    parser.add_argument("--to-month", default=f"{date.today().year:04d}-{date.today().month:02d}", type=parse_month)
    parser.add_argument("--types", choices=["award", "tender", "both"], default="both")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--list-only", action="store_true")
    args = parser.parse_args()

    kinds = ("award", "tender") if args.types == "both" else (args.types,)
    items = list(halfmonth_targets(args.from_month, args.to_month, kinds))
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()

    print("PCC 官方半月 XML 全量下載")
    print(f"期間：{args.from_month[0]:04d}-{args.from_month[1]:02d} → {args.to_month[0]:04d}-{args.to_month[1]:02d}")
    print(f"檔案數：{len(items)}")
    print(f"輸出：{OUT}")

    if args.list_only:
        for item in items:
            print(item[4])
        return 0

    completed = 0
    downloaded = 0
    skipped = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(fetch_one, item, manifest, args.delay) for item in items]
        for future in as_completed(futures):
            result = future.result()
            filename = result["filename"]
            manifest["files"][filename] = result
            completed += 1
            status = result.get("status")
            if status == "downloaded":
                downloaded += 1
            elif status == "exists":
                skipped += 1
            elif status in {"http_error", "empty", "html_response", "network_error", "timeout", "error"}:
                failed += 1
            if completed % 10 == 0 or status not in {"downloaded", "exists"}:
                print(f"[{completed}/{len(items)}] {status}: {filename}")
            save_manifest(manifest)

    manifest["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    manifest["summary"] = {
        "requested": len(items),
        "downloaded": downloaded,
        "already_present": skipped,
        "failed_or_missing": failed,
    }
    save_manifest(manifest)

    print("\n完成。")
    print(f"成功下載：{downloaded}")
    print(f"已存在：{skipped}")
    print(f"失敗/尚未發布：{failed}")
    print(f"資料：{OUT}")
    print(f"清單：{MANIFEST}")
    return 0 if downloaded + skipped > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
