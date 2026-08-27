#!/usr/bin/env python3
"""PCC OpenData bulk downloader with iframe/form/button discovery.

The PCC OpenData list is a browser-oriented page and may not expose files as
ordinary <a href> links. This version inspects the main document and every
iframe, collects href/action/data-* and JavaScript download targets, and can
also capture a diagnostic snapshot when no resources are discovered.

Local setup:
  python3 -m pip install playwright
  python3 -m playwright install chromium

Smoke test:
  python3 scripts/download_pcc_all.py --max-pages 1 --headed

Full run:
  python3 scripts/download_pcc_all.py --headed

Outputs:
  data/raw/pcc/files/
  data/raw/pcc/manifest.json
  data/raw/pcc/debug/  (HTML/screenshot when discovery is empty)
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
    print("請先安裝：python3 -m pip install playwright && python3 -m playwright install chromium")
    raise SystemExit(2)

START_URL = "https://web.pcc.gov.tw/tps/tp/OpenData/showList"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "pcc"
FILES = OUT / "files"
DEBUG = OUT / "debug"
MANIFEST = OUT / "manifest.json"

EXTENSIONS = {
    ".csv", ".tsv", ".txt", ".json", ".xml", ".xlsx", ".xls", ".ods",
    ".zip", ".rar", ".7z", ".pdf", ".doc", ".docx", ".ppt", ".pptx",
    ".rtf", ".kml", ".kmz", ".shp", ".dbf", ".prj", ".sql"
}
DOWNLOAD_WORDS = ("download", "下載", "下載檔案", "資料下載", "取得", "檔案")


def safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "_", name).strip()
    return name[:180] or "download"


def load_manifest() -> dict:
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"source": START_URL, "pages": [], "files": {}}


def save_manifest(m: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(MANIFEST)


def likely_resource(url: str, text: str = "", attrs: str = "") -> bool:
    blob = f"{url} {text} {attrs}".lower()
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in EXTENSIONS) or any(w in blob for w in DOWNLOAD_WORDS)


def extract_frame_resources(frame, page_url: str) -> list[dict]:
    """Collect resource-like URLs from a document/frame, including forms."""
    out: list[dict] = []
    try:
        anchors = frame.locator("a").all()
        for a in anchors:
            try:
                href = a.get_attribute("href") or ""
                text = (a.inner_text() or "").strip()
                raw = (a.get_attribute("onclick") or "") + " " + (a.get_attribute("data-url") or "") + " " + (a.get_attribute("data-href") or "")
            except Exception:
                continue
            candidates = [href]
            for m in re.findall(r"(?:location(?:\.href)?|url|downloadUrl|fileUrl)\\?\s*[=:]\s*['\"]([^'\"]+)", raw, re.I):
                candidates.append(m)
            for candidate in candidates:
                if not candidate or candidate.startswith("javascript:") or candidate.startswith("#"):
                    continue
                absolute = urljoin(page_url, candidate)
                if likely_resource(absolute, text, raw):
                    out.append({"url": absolute, "text": text, "kind": "link"})

        for form in frame.locator("form").all():
            try:
                action = form.get_attribute("action") or ""
                method = (form.get_attribute("method") or "get").lower()
                text = (form.inner_text() or "").strip()
            except Exception:
                continue
            if not action:
                continue
            absolute = urljoin(page_url, action)
            blob = (text + " " + absolute).lower()
            if likely_resource(absolute, text) or any(w in blob for w in DOWNLOAD_WORDS):
                out.append({"url": absolute, "text": text[:200], "kind": "form", "method": method})

        for el in frame.locator("button, input[type=button], input[type=submit], [role=button]").all():
            try:
                text = (el.inner_text() or el.get_attribute("value") or "").strip()
                raw = " ".join(filter(None, [
                    el.get_attribute("onclick") or "",
                    el.get_attribute("data-url") or "",
                    el.get_attribute("data-href") or "",
                    el.get_attribute("data-download") or "",
                ]))
            except Exception:
                continue
            if not text and not raw:
                continue
            if any(w in (text + " " + raw).lower() for w in DOWNLOAD_WORDS):
                urls = re.findall(r"https?://[^'\"\\s]+|['\"]([^'\"]+)['\"]", raw)
                flat = []
                for item in urls:
                    if isinstance(item, tuple):
                        flat.extend(item)
                    else:
                        flat.append(item)
                for candidate in flat:
                    if not candidate:
                        continue
                    absolute = urljoin(page_url, candidate)
                    out.append({"url": absolute, "text": text, "kind": "button"})
    except Exception:
        pass
    return out


def all_frame_resources(page) -> list[dict]:
    resources: list[dict] = []
    seen = set()
    for frame in page.frames:
        for row in extract_frame_resources(frame, frame.url or page.url):
            if row["url"] in seen:
                continue
            seen.add(row["url"])
            resources.append(row)
    return resources


def find_next(page) -> str | None:
    selectors = [
        'a:has-text("下一頁")', 'a:has-text("下一页")',
        'button:has-text("下一頁")', 'button:has-text("下一页")',
        'a[title*="下一"]', 'a[aria-label*="下一"]',
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                href = loc.get_attribute("href")
                if href and not href.startswith("javascript:"):
                    return urljoin(page.url, href)
                # Button pagination: click and return resulting URL.
                before = page.url
                loc.click(timeout=5000)
                page.wait_for_timeout(1000)
                if page.url != before:
                    return page.url
        except Exception:
            pass
    return None


def debug_snapshot(page, page_no: int) -> None:
    DEBUG.mkdir(parents=True, exist_ok=True)
    try:
        (DEBUG / f"page_{page_no}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    try:
        page.screenshot(path=str(DEBUG / f"page_{page_no}.png"), full_page=True)
    except Exception:
        pass
    try:
        frames = [{"url": f.url, "name": f.name} for f in page.frames]
        (DEBUG / f"page_{page_no}_frames.json").write_text(
            json.dumps(frames, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def filename(url: str, text: str) -> str:
    base = Path(urlparse(url).path).name
    if not base or "." not in base:
        base = safe_name(text) or "download"
    return safe_name(base)


def download(context, url: str, target: Path) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size:
        return {"status": "exists", "bytes": target.stat().st_size}
    page = context.new_page()
    try:
        with page.expect_download(timeout=15000) as dl_info:
            page.goto(url, wait_until="commit", timeout=90000)
        dl = dl_info.value
        dl.save_as(str(target))
        return {"status": "downloaded", "bytes": target.stat().st_size}
    except Exception:
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=90000)
            if response is None:
                return {"status": "no_response"}
            body = response.body()
            ctype = (response.headers.get("content-type") or "").lower()
            if "text/html" in ctype and target.suffix.lower() not in {".html", ".htm"}:
                return {"status": "html_response", "http": response.status, "content_type": ctype}
            target.write_bytes(body)
            return {"status": "downloaded", "bytes": len(body), "http": response.status,
                    "sha256": hashlib.sha256(body).hexdigest()}
        except PlaywrightTimeoutError:
            return {"status": "timeout"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)[:500]}
    finally:
        page.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=0, help="0 = all pages")
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--headed", action="store_true", help="Show Chromium window")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--wait", type=int, default=5, help="extra seconds after page load")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    FILES.mkdir(parents=True, exist_ok=True)
    m = load_manifest()
    files = m.setdefault("files", {})

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        context = browser.new_context(accept_downloads=True, locale="zh-TW")
        page = context.new_page()
        print(f"開啟 PCC：{START_URL}")
        page.goto(START_URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(args.wait * 1000)

        seen_pages = set()
        page_no = 0
        while page.url not in seen_pages:
            seen_pages.add(page.url)
            page_no += 1
            resources = all_frame_resources(page)
            if not resources:
                debug_snapshot(page, page_no)
            for row in resources:
                files.setdefault(row["url"], {"text": row.get("text", ""), "kind": row.get("kind"), "pages": []})
                files[row["url"]].setdefault("pages", []).append(page_no)
            manifest_save(m)
            print(f"第 {page_no} 頁：找到 {len(resources)} 個候選資源；累計 {len(files)} 個唯一資源")
            if not resources:
                print("  ⚠️ 沒找到下載資源。已保存除錯檔案到 data/raw/pcc/debug/")
            if args.max_pages and page_no >= args.max_pages:
                break
            nxt = find_next(page)
            if not nxt or nxt in seen_pages:
                break
            if page.url != nxt:
                page.goto(nxt, wait_until="domcontentloaded", timeout=120000)
                page.wait_for_timeout(args.wait * 1000)
            time.sleep(args.delay)

        if args.list_only:
            browser.close()
            print(f"清單：{MANIFEST}")
            return 0

        total = len(files)
        for i, (url, meta) in enumerate(files.items(), 1):
            name = filename(url, meta.get("text", ""))
            stamp = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
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
    save_manifest(m)
    print(f"完成。資料：{FILES}")
    print(f"清單：{MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
