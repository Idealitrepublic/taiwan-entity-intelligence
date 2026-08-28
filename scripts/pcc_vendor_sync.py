#!/usr/bin/env python3
"""Query PCC's public procurement search by supplier uniform number.

This avoids the unreliable OpenData catalog/file-download route. PCC's public
"決標查詢" accepts a supplier identifier (vendorId). The script fetches the
search result pages, extracts procurement rows from HTML tables, and stores a
machine-readable JSONL snapshot under data/raw/pcc/vendor/<uniform_no>/.

Example:
  python3 scripts/pcc_vendor_sync.py 22099131
  python3 scripts/pcc_vendor_sync.py 22099131 --pages 10

No third-party package is required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://web.pcc.gov.tw/prkms/tender/common/tenderList/searchTender"


class TableParser(HTMLParser):
    """Collect table rows/cells while preserving visible text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.current_cell: list[str] = []
        self.current_row: list[str] = []
        self.rows: list[list[str]] = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "table":
            self.in_table = True
            self._depth = 1
        elif self.in_table:
            if tag == "table":
                self._depth += 1
            elif tag == "tr":
                self.in_row = True
                self.current_row = []
            elif tag in {"td", "th"} and self.in_row:
                self.in_cell = True
                self.current_cell = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if not self.in_table:
            return
        if tag in {"td", "th"} and self.in_cell:
            text = re.sub(r"\s+", " ", "".join(self.current_cell)).strip()
            self.current_row.append(text)
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if any(self.current_row):
                self.rows.append(self.current_row)
            self.in_row = False
        elif tag == "table":
            self._depth -= 1
            if self._depth <= 0:
                self.in_table = False

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell.append(data)



def fetch(url: str) -> tuple[int, bytes, dict]:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 Chrome/151 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.6",
        },
    )
    with urlopen(req, timeout=60) as r:
        body = r.read()
        headers = dict(r.headers.items())
        return getattr(r, "status", 200), body, headers



def build_url(uniform_no: str, page_size: int = 100) -> str:
    params = {
        "vendorId": uniform_no,
        "gottenVendorId": uniform_no,
        "gottenVendorName": "",
        "submitVendorId": uniform_no,
        "submitVendorName": "",
        "isQuery": "true",
        "firstSearch": "true",
        "tenderRange": "TENDER_RANGE_ALL",
        "tenderStatus": "TENDER_STATUS_1",
        "tenderWay": "TENDER_WAY_ALL_DECLARATION",
        "pageSize": str(page_size),
    }
    return BASE + "?" + urlencode(params)



def parse_records(url: str, body: bytes) -> list[dict]:
    text = body.decode("utf-8", errors="replace")
    parser = TableParser()
    parser.feed(text)
    records: list[dict] = []
    seen: set[str] = set()
    for row in parser.rows:
        if len(row) < 3:
            continue
        blob = " | ".join(row)
        # Filter out navigation/footer tables. Procurement result rows almost
        # always contain an alphanumeric case number/date/award marker.
        if not any(k in blob for k in ("決標", "招標", "履約", "得標", "案號")):
            continue
        key = hashlib.sha1(blob.encode("utf-8")).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        records.append({"cells": row, "source_url": url})
    return records



def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("uniform_number")
    ap.add_argument("--pages", type=int, default=3, help="number of result pages to inspect")
    ap.add_argument("--delay", type=float, default=0.8)
    args = ap.parse_args()
    if not re.fullmatch(r"\d{8}", args.uniform_number):
        raise SystemExit("統編必須是 8 位數字")

    out_dir = ROOT / "data" / "raw" / "pcc" / "vendor" / args.uniform_number
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"uniform_number": args.uniform_number, "base_url": BASE, "pages": [], "records": 0}
    all_records: list[dict] = []

    # PCC pagination links are discovered from each returned page. Because the
    # site changes pagination parameter names occasionally, follow actual hrefs
    # instead of synthesizing page parameters.
    queue = [build_url(args.uniform_number)]
    seen_urls: set[str] = set()

    for _ in range(max(1, args.pages)):
        if not queue:
            break
        url = queue.pop(0)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        try:
            status, body, headers = fetch(url)
        except Exception as exc:
            manifest["pages"].append({"url": url, "status": "error", "error": str(exc)[:500]})
            break
        parser = TableParser()
        parser.feed(body.decode("utf-8", errors="replace"))
        page_records = parse_records(url, body)
        all_records.extend(page_records)
        page_meta = {"url": url, "http": status, "bytes": len(body), "records": len(page_records)}
        manifest["pages"].append(page_meta)

        # Discover pagination/next links from the raw HTML. Keep only links
        # pointing back into PCC tender search.
        class LinkParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.links: list[str] = []
            def handle_starttag(self, tag, attrs):
                if tag.lower() != "a":
                    return
                href = dict(attrs).get("href")
                if href and "searchTender" in href:
                    self.links.append(urljoin(url, href))
        lp = LinkParser()
        lp.feed(body.decode("utf-8", errors="replace"))
        for href in lp.links:
            if href not in seen_urls and href not in queue:
                # Follow probable pagination links only. Avoid restarting a
                # completely different search.
                q = parse_qs(urlparse(href).query)
                if q.get("vendorId", [""])[0] == args.uniform_number:
                    queue.append(href)
        time.sleep(args.delay)

    # Deduplicate across pages.
    dedup: dict[str, dict] = {}
    for rec in all_records:
        key = hashlib.sha1(json.dumps(rec["cells"], ensure_ascii=False).encode("utf-8")).hexdigest()
        dedup[key] = rec
    all_records = list(dedup.values())
    manifest["records"] = len(all_records)
    manifest["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    (out_dir / "records.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in all_records),
        encoding="utf-8",
    )
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"PCC 廠商查詢：{args.uniform_number}")
    print(f"查詢頁：{len(manifest['pages'])}")
    print(f"擷取結果：{len(all_records)} 筆")
    print(f"資料：{out_dir / 'records.jsonl'}")
    print(f"清單：{out_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
