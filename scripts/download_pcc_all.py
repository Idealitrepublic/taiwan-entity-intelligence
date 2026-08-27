#!/usr/bin/env python3
"""Download all downloadable resources listed by PCC Open Data showList.

This runs on the user's own computer. It uses Playwright because the PCC site
may require JavaScript/session state. It paginates until no next page remains,
deduplicates file URLs, downloads them to data/raw/pcc/files/, and maintains a
manifest so interrupted runs can resume.

Setup:
  python3 -m pip install playwright
  python3 -m playwright install chromium

Run:
  python3 scripts/download_pcc_all.py
  python3 scripts/download_pcc_all.py --max-pages 3   # smoke test
  python3 scripts/download_pcc_all.py --list-only     # discover links only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    print("請先安裝 Playwright：python3 -m pip install playwright && python3 -m playwright install chromium")
    raise SystemExit(2)

START_URL = "https://web.pcc.gov.tw/tps/tp/OpenData/showList"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "pcc"
FILES = OUT / "files"
MANIFEST = OUT / "manifest.json"
FILE_EXTENSIONS = {".csv", ".tsv", ".txt", ".json", ".xml", ".xlsx", ".xls", ".ods", ".zip", ".rar", ".7z", ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".rtf", ".kml", ".kmz", ".shp", ".dbf", ".prj", ".sql"}


def safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "_", name).strip()
    return name[:180] or "download"


def manifest_load() -> dict:
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"source": START_URL, "pages": [], "files": {}}


def manifest_save(m: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(MANIFEST)


def is_file_link(href: str, text: str) -> bool:
    path = urlparse(href).path.lower()
    if any(path.endswith(ext) for ext in FILE_EXTENSIONS):
        return True
    blob = f"{href} {text}".lower()
    return any(x in blob for x in ("download", "下載", "檔案", "資料下載"))


def page_links(page) -> list[dict]:
    out, seen = [], set()
    for a in page.locator("a").all():
        try:
            href = a.get_attribute("href")
            text = (a.inner_text() or "").strip()
        except Exception:
            continue
        if not href or href.startswith("javascript:") or href.startswith("#"):
            continue
        url = urljoin(page.url, href)
        if is_file_link(url, text) and url not in seen:
            seen.add(url)
            out.append({"url": url, "text": text})
    return out


def next_url(page) -> str | None:
    selectors = ['a:has-text("下一頁")', 'a[title*="下一"]', 'a[aria-label*="下一"]']
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() and loc.is_visible():
                href = loc.get_attribute("href")
                if href and not href.startswith("javascript:"):
                    return urljoin(page.url, href)
        except Exception:
            pass
    return None


def filename(url: str, text: str) -> str:
    base = Path(urlparse(url).path).name
    if not base or "." not in base:
        base = text or "download"
    return safe_name(base)


def download(context, url: str, target: Path) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size:
        return {"status": "exists", "bytes": target.stat().st_size}
    page = context.new_page()
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=90000)
        if response is not None:
            body = response.body()
            ctype = (response.headers.get("content-type") or "").lower()
            if "text/html" not in ctype or target.suffix.lower() in {".html", ".htm"}:
                target.write_bytes(body)
                return {"status": "downloaded", "bytes": len(body), "http": response.status,
                        "sha256": hashlib.sha256(body).hexdigest()}
        return {"status": "empty_or_html", "http": response.status if response else None}
    except PlaywrightTimeoutError:
        return {"status": "timeout"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:500]}
    finally:
        page.close()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--max-pages", type=int, default=0)
    p.add_argument("--list-only", action="store_true")
    p.add_argument("--delay", type=float, default=0.5)
    args = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    FILES.mkdir(parents=True, exist_ok=True)
    m = manifest_load()
    files = m.setdefault("files", {})

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True, locale="zh-TW")
        page = context.new_page()
        page.goto(START_URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(1500)
        seen_pages = set()
        count = 0
        while page.url not in seen_pages:
            seen_pages.add(page.url)
            count += 1
            links = page_links(page)
            m.setdefault("pages", []).append({"page": count, "url": page.url, "links": len(links)})
            for row in links:
                files.setdefault(row["url"], {"text": row["text"], "pages": []})
                files[row["url"]].setdefault("pages", []).append(count)
            manifest_save(m)
            print(f"第 {count} 頁：{len(links)} 個檔案連結；累計 {len(files)} 個唯一資源")
            if args.max_pages and count >= args.max_pages:
                break
            nxt = next_url(page)
            if not nxt or nxt in seen_pages:
                break
            page.goto(nxt, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(int(args.delay * 1000))

        if args.list_only:
            browser.close()
            print(f"已建立清單：{MANIFEST}")
            return 0

        total = len(files)
        for i, (url, meta) in enumerate(files.items(), start=1):
            name = filename(url, meta.get("text", ""))
            stamp = hashlib.sha1(url.encode()).hexdigest()[:10]
            target = FILES / name
            if target.exists() and meta.get("url_hash") != stamp:
                target = FILES / f"{Path(name).stem}_{stamp}{Path(name).suffix}"
            meta["url_hash"] = stamp
            meta["local_path"] = str(target.relative_to(ROOT))
            meta["last_result"] = download(context, url, target)
            meta["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            manifest_save(m)
            print(f"[{i}/{total}] {meta['last_result'].get('status')} {name}")
            time.sleep(args.delay)
        browser.close()
    m["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    manifest_save(m)
    print(f"完成。資料：{FILES}")
    print(f"清單：{MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
