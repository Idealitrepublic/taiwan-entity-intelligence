#!/usr/bin/env python3
"""Download files listed by the PCC OpenData showList page.

This version does not rely only on href discovery. It also clicks likely
Download/OpenData controls and captures Playwright download events, which is
important when PCC generates the file only after a JavaScript/form action.

Usage:
  python3 scripts/pcc_showlist_full_download.py --max-pages 1 --headed
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Set
from urllib.parse import urljoin, urlparse

SHOWLIST = "https://web.pcc.gov.tw/tps/tp/OpenData/showList"
DEFAULT_DIR = Path("data/raw/pcc/all")


def safe_name(value: str, fallback: str = "download.bin") -> str:
    # Accept either a URL or a Playwright suggested filename.
    path = urlparse(value).path if "://" in value else value
    name = os.path.basename(path) or fallback
    name = re.sub(r"[^\w.\-()\u4e00-\u9fff ]+", "_", name).strip() or fallback
    return name[:240]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class Downloader:
    def __init__(self, output: Path, max_pages: int | None, headless: bool):
        self.output = output
        self.max_pages = max_pages
        self.headless = headless
        self.output.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.output / "manifest.json"
        self.manifest: Dict = {"source": SHOWLIST, "files": {}}
        if self.manifest_path.exists():
            try:
                self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        self.urls: List[str] = []
        self.seen: Set[str] = set()
        self.download_count = 0

    def save_manifest(self):
        tmp = self.manifest_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.manifest_path)

    def add_url(self, url: str):
        if not url:
            return
        url = urljoin(SHOWLIST, url)
        if url.startswith("javascript:"):
            return
        low = url.lower()
        if any(x in low for x in (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", "favicon")):
            return
        if "web.pcc.gov.tw" not in low:
            return
        if url not in self.seen:
            self.seen.add(url)
            self.urls.append(url)

    async def scan_page(self, page) -> List[str]:
        found: Set[str] = set()

        hrefs = await page.locator("a[href]").evaluate_all("els => els.map(e => e.href).filter(Boolean)")
        found.update(hrefs)

        values = await page.locator("*[href], *[data-url], *[data-href], *[onclick]").evaluate_all(
            "els => els.flatMap(e => [e.getAttribute('href'), e.getAttribute('data-url'), e.getAttribute('data-href'), e.getAttribute('onclick')]).filter(Boolean)"
        )
        for value in values:
            for match in re.findall(r"https?://[^\"'\\s)]+|(?:/|OpenData/|tps/)[^\"'\\s)]+", value):
                if "web.pcc.gov.tw" in match or match.startswith("/"):
                    found.add(urljoin(SHOWLIST, match))

        # Also keep the actual page for debugging.
        try:
            (self.output / "showlist_last.html").write_text(await page.content(), encoding="utf-8")
        except Exception:
            pass

        for u in sorted(found):
            self.add_url(u)
        return sorted(found)

    async def save_download(self, download, page_url: str):
        try:
            suggested = await download.suggested_filename()
            name = safe_name(suggested)
            dest = self.output / name
            if dest.exists():
                stem, suffix = dest.stem, dest.suffix
                i = 2
                while (self.output / f"{stem}_{i}{suffix}").exists():
                    i += 1
                dest = self.output / f"{stem}_{i}{suffix}"
            await download.save_as(str(dest))
            size = dest.stat().st_size
            key = f"download::{suggested}::{page_url}"
            self.manifest["files"][key] = {
                "url": page_url,
                "status": "downloaded",
                "path": str(dest),
                "bytes": size,
                "sha256": sha256(dest),
                "suggested_filename": suggested,
            }
            self.save_manifest()
            self.download_count += 1
            print(f"  ✓ 瀏覽器下載：{name} ({size:,} bytes)", flush=True)
        except Exception as exc:
            print(f"  ✗ 保存瀏覽器下載失敗：{exc}", flush=True)

    async def click_download_controls(self, page):
        """Click likely download buttons/links and capture download events."""
        selectors = [
            "a",
            "button",
            "input[type='button']",
            "input[type='submit']",
            "[role='button']",
            "[onclick]",
        ]
        candidates = page.locator(",".join(selectors))
        count = await candidates.count()
        for i in range(count):
            el = candidates.nth(i)
            try:
                text = ((await el.inner_text()) or "").strip()
            except Exception:
                text = ""
            try:
                attrs = await el.evaluate("e => ({href:e.getAttribute('href'),onclick:e.getAttribute('onclick'),title:e.getAttribute('title'),value:e.getAttribute('value')})")
            except Exception:
                attrs = {}
            hay = " ".join(str(attrs.get(k) or "") for k in ("href", "onclick", "title", "value")) + " " + text
            if not re.search(r"下載|下載檔案|download|open.?data|檔案", hay, re.I):
                continue

            try:
                async with page.expect_download(timeout=6000) as dl_info:
                    await el.click(timeout=5000, no_wait_after=True)
                download = await dl_info.value
                await self.save_download(download, page.url)
            except Exception:
                # Some controls navigate or open a new tab instead of emitting a download.
                try:
                    await el.click(timeout=2000, no_wait_after=True)
                    await page.wait_for_timeout(800)
                except Exception:
                    pass

    async def click_next(self, page) -> bool:
        patterns = [
            re.compile(r"下一頁", re.I),
            re.compile(r"Next", re.I),
            re.compile(r"^>$"),
            re.compile(r"^›$"),
            re.compile(r"下一頁|下页", re.I),
        ]
        for pattern in patterns:
            loc = page.get_by_text(pattern).first
            try:
                if await loc.count() and await loc.is_visible():
                    await loc.click(timeout=8000)
                    await page.wait_for_timeout(1800)
                    return True
            except Exception:
                continue

        # Fallback: links whose URL looks like pagination.
        loc = page.locator('a[href*="page"], a[href*="Page"], a[href*="pageNo"]').last
        try:
            if await loc.count() and await loc.is_visible():
                await loc.click(timeout=8000)
                await page.wait_for_timeout(1800)
                return True
        except Exception:
            pass
        return False

    async def download_one(self, context, url: str):
        key = url
        rec = self.manifest["files"].get(key)
        if rec and rec.get("status") == "downloaded" and Path(rec.get("path", "")).exists():
            return
        name = safe_name(url)
        dest = self.output / name
        if dest.exists() and (not rec or rec.get("url") != url):
            stem, suffix = dest.stem, dest.suffix
            i = 2
            while (self.output / f"{stem}_{i}{suffix}").exists():
                i += 1
            dest = self.output / f"{stem}_{i}{suffix}"
        try:
            response = await context.request.get(url, timeout=120000)
            body = await response.body()
            if not body:
                self.manifest["files"][key] = {"url": url, "status": "empty", "status_code": response.status}
                self.save_manifest()
                return
            dest.write_bytes(body)
            self.manifest["files"][key] = {
                "url": url,
                "status": "downloaded",
                "status_code": response.status,
                "path": str(dest),
                "bytes": len(body),
                "sha256": sha256(dest),
            }
            self.save_manifest()
            self.download_count += 1
            print(f"  ✓ URL 下載：{name} ({len(body):,} bytes)", flush=True)
        except Exception as exc:
            self.manifest["files"][key] = {"url": url, "status": "error", "error": str(exc)}
            self.save_manifest()
            print(f"  ✗ {url} :: {exc}", flush=True)

    async def run(self):
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()

            # Capture any download that occurs independently of an explicit click.
            async def on_download(download):
                await self.save_download(download, page.url)

            page.on("download", on_download)

            await page.goto(SHOWLIST, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(4000)

            page_no = 1
            previous_url = None
            while True:
                before = len(self.urls)
                found = await self.scan_page(page)
                print(f"第 {page_no} 頁：找到 {len(found)} 個候選連結；累計 {len(self.urls)} 個唯一資源", flush=True)

                # First try actual browser downloads from buttons/forms/JS controls.
                await self.click_download_controls(page)

                # Then fetch ordinary direct URLs discovered on the page.
                for url in list(self.urls)[before:]:
                    await self.download_one(context, url)

                if self.max_pages and page_no >= self.max_pages:
                    break

                previous_url = page.url
                if not await self.click_next(page):
                    break
                if page.url == previous_url:
                    break
                page_no += 1

            await context.close()
            await browser.close()

        self.save_manifest()
        ok = sum(1 for v in self.manifest["files"].values() if v.get("status") == "downloaded")
        print(f"完成：發現 {len(self.urls)} 個唯一資源；成功下載 {ok} 個。", flush=True)
        if not self.urls and self.download_count == 0:
            print(f"沒有發現可下載資源。已保存除錯頁：{self.output / 'showlist_last.html'}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--headed", action="store_true", help="顯示瀏覽器視窗")
    ap.add_argument("--output", default=str(DEFAULT_DIR))
    args = ap.parse_args()
    asyncio.run(Downloader(Path(args.output), args.max_pages, not args.headed).run())


if __name__ == "__main__":
    main()
