#!/usr/bin/env python3
"""PCC OpenData showList downloader.

First-run goal: visibly open the PCC page, inspect it, and report what it found.
It is deliberately conservative and will NOT claim a download succeeded unless
an actual file is saved.
"""
from __future__ import print_function

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

SHOWLIST = "https://web.pcc.gov.tw/tps/tp/OpenData/showList"
DEFAULT_DIR = Path("data/raw/pcc/all")


def safe_name(value):
    path = urlparse(value).path if "://" in value else value
    name = os.path.basename(path) or "download.bin"
    name = re.sub(r"[^\w.\-()\u4e00-\u9fff ]+", "_", name).strip() or "download.bin"
    return name[:240]


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def save_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--headed", action="store_true", help="顯示 Chromium 視窗（預設就是顯示）")
    parser.add_argument("--output", default=str(DEFAULT_DIR))
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "manifest.json"
    manifest = {"source": SHOWLIST, "files": {}, "pages": [], "errors": []}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    print("=" * 72, flush=True)
    print("T.E.I. PCC OpenData 下載器", flush=True)
    print("=" * 72, flush=True)
    print("PCC：", SHOWLIST, flush=True)
    print("輸出：", str(output.resolve()), flush=True)
    print("Python：", sys.version.split()[0], flush=True)
    print("準備啟動瀏覽器...", flush=True)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print("❌ 找不到 Playwright：", repr(exc), flush=True)
        print("請執行：python3 -m pip install playwright", flush=True)
        return 1

    with sync_playwright() as p:
        browser = None
        try:
            print("啟動 Chromium（可見視窗）...", flush=True)
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            print("正在開啟 PCC...", flush=True)
            response = page.goto(SHOWLIST, wait_until="domcontentloaded", timeout=120000)
            print("PCC 已開啟。HTTP：", response.status if response else "unknown", flush=True)
            print("標題：", page.title(), flush=True)
            time.sleep(3)

            debug_dir = output / "debug"
            save_text(debug_dir / "page_1.html", page.content())
            try:
                page.screenshot(path=str(debug_dir / "page_1.png"), full_page=True)
            except Exception:
                pass
            print("除錯檔已保存：", str(debug_dir.resolve()), flush=True)

            # Capture browser download events while clicking only obvious download controls.
            downloads = []
            for selector in [
                "a:has-text('下載')",
                "button:has-text('下載')",
                "input[value*='下載']",
                "a:has-text('Download')",
                "button:has-text('Download')",
            ]:
                loc = page.locator(selector)
                count = min(loc.count(), 30)
                if count:
                    print("找到控制項：", selector, "×", count, flush=True)
                for i in range(count):
                    try:
                        with page.expect_download(timeout=5000) as dl_info:
                            loc.nth(i).click(timeout=3000, no_wait_after=True)
                        dl = dl_info.value
                        downloads.append(dl)
                        print("✓ 捕捉到下載：", dl.suggested_filename, flush=True)
                    except Exception:
                        pass

            for dl in downloads:
                try:
                    target = output / safe_name(dl.suggested_filename)
                    if target.exists():
                        target = output / (target.stem + "_" + str(int(time.time())) + target.suffix)
                    dl.save_as(str(target))
                    size = target.stat().st_size
                    key = "download::" + dl.suggested_filename
                    manifest["files"][key] = {
                        "url": dl.url,
                        "status": "downloaded",
                        "path": str(target),
                        "bytes": size,
                        "sha256": sha256(target),
                    }
                    print("  ✓ 已保存：", str(target), "(", size, "bytes )", flush=True)
                except Exception as exc:
                    print("  ✗ 保存失敗：", repr(exc), flush=True)

            # Discover visible same-origin links for diagnostics, but do not blindly click them.
            anchors = page.locator("a[href]").evaluate_all("els => els.map(e => ({text:(e.innerText||'').trim(), href:e.href})).filter(x=>x.href)")
            same_origin = [a for a in anchors if "web.pcc.gov.tw" in a.get("href", "")]
            print("頁面同源連結：", len(same_origin), flush=True)
            for item in same_origin[:50]:
                txt = item.get("text") or ""
                href = item.get("href") or ""
                if re.search(r"下載|download|檔案|資料", txt + " " + href, re.I):
                    print("  候選：", txt[:60], href[:180], flush=True)

            manifest["pages"].append({"page": 1, "url": page.url, "same_origin_links": len(same_origin), "browser_downloads": len(downloads)})
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            ok = sum(1 for v in manifest["files"].values() if v.get("status") == "downloaded")
            print("=" * 72, flush=True)
            print("完成：實際下載檔案 =", ok, flush=True)
            if ok == 0:
                print("⚠️ 目前沒有任何檔案成功下載。", flush=True)
                print("請把這段終端機輸出貼回來，我會依實際 PCC 頁面結構再修。", flush=True)
            context.close()
            browser.close()
            return 0 if ok > 0 else 2

        except Exception as exc:
            print("❌ 執行失敗：", repr(exc), flush=True)
            manifest["errors"].append({"error": repr(exc)})
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                if browser:
                    browser.close()
            except Exception:
                pass
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
