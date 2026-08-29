#!/usr/bin/env python3
"""Download all files listed by PCC OpenData showList.

Usage:
  python3 scripts/pcc_showlist_full_download.py

The script uses Playwright, follows the actual showList pagination, captures
network responses/downloads, extracts candidate file URLs, and stores files
under data/raw/pcc/all/. It keeps a manifest so reruns skip files already
successfully downloaded.
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


def safe_name(url: str, fallback: str = "download.bin") -> str:
    path = urlparse(url).path
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
        # Keep download-like URLs and PCC same-origin resources; avoid CSS/JS/images.
        if any(x in low for x in (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", "favicon")):
            return
        if url not in self.seen:
            self.seen.add(url)
            self.urls.append(url)

    async def scan_page(self, page) -> List[str]:
        found: Set[str] = set()
        # Anchor hrefs.
        for u in await page.locator("a").evaluate_all("els => els.map(e => e.href).filter(Boolean)"):
            if "web.pcc.gov.tw" in u:
                found.add(u)
        # Buttons/data attributes and common download tokens.
        values = await page.locator("*[href], *[data-url], *[data-href], *[onclick]").evaluate_all(
            "els => els.flatMap(e => [e.getAttribute('href'), e.getAttribute('data-url'), e.getAttribute('data-href'), e.getAttribute('onclick')]).filter(Boolean)"
        )
        for value in values:
            for match in re.findall(r"https?://[^\"'\\s)]+|(?:/|OpenData/|tps/)[^\"'\\s)]+", value):
                if "web.pcc.gov.tw" in match or match.startswith("/"):
                    found.add(urljoin(SHOWLIST, match))
        for u in found:
            self.add_url(u)
        return sorted(found)

    async def run(self):
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()

            async def on_response(response):
                url = response.url
                ct = (response.headers.get("content-type") or "").lower()
                if "web.pcc.gov.tw" in url and ("download" in url.lower() or "attachment" in ct or "octet-stream" in ct or "xml" in ct or "csv" in ct):
                    self.add_url(url)

            page.on("response", on_response)

            await page.goto(SHOWLIST, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(2500)

            page_no = 1
            while True:
                before = len(self.urls)
                found = await self.scan_page(page)
                print(f"第 {page_no} 頁：找到 {len(found)} 個候選連結；累計 {len(self.urls)} 個唯一資源", flush=True)

                # Download URLs discovered on this page first.
                for url in list(self.urls)[before:]:
                    await self.download_one(context, url)

                if self.max_pages and page_no >= self.max_pages:
                    break

                # Try to locate next-page controls by visible labels or href/query.
                next_link = page.locator("a", has_text=re.compile(r"下一頁|Next|>|›", re.I)).first
                if await next_link.count() == 0:
                    next_link = page.locator('a[href*="page"], a[href*="Page"], a[href*="pageNo"]').last
                if await next_link.count() == 0:
                    break

                try:
                    await next_link.click(timeout=8000)
                    await page.wait_for_timeout(1800)
                    page_no += 1
                except Exception:
                    break

            await context.close()
            await browser.close()

        self.save_manifest()
        ok = sum(1 for v in self.manifest["files"].values() if v.get("status") == "downloaded")
        print(f"完成：發現 {len(self.urls)} 個唯一資源；成功下載 {ok} 個。", flush=True)
        if not self.urls:
            debug = self.output / "showlist_debug.html"
            print(f"沒有發現資源。請查看：{debug}")

    async def download_one(self, context, url: str):
        key = url
        rec = self.manifest["files"].get(key)
        if rec and rec.get("status") == "downloaded" and Path(rec.get("path", "")).exists():
            return
        name = safe_name(url)
        dest = self.output / name
        # Avoid collisions.
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
            print(f"  ✓ {name} ({len(body):,} bytes)", flush=True)
        except Exception as exc:
            self.manifest["files"][key] = {"url": url, "status": "error", "error": str(exc)}
            self.save_manifest()
            print(f"  ✗ {url} :: {exc}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--headed", action="store_true", help="顯示瀏覽器視窗")
    ap.add_argument("--output", default=str(DEFAULT_DIR))
    args = ap.parse_args()
    asyncio.run(Downloader(Path(args.output), args.max_pages, not args.headed).run())


if __name__ == "__main__":
    main()
