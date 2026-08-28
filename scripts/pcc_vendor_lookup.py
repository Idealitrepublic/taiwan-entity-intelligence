#!/usr/bin/env python3
"""PCC vendor lookup probe for T.E.I.

This uses PCC's public procurement query pages rather than the catalog's
half-month download endpoint. It is intentionally a small, diagnostic-first
adapter: given a uniform number, it records the exact public search URL and
saves the returned HTML for inspection, so parsing rules can be validated
before bulk ingestion.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "pcc" / "vendor_lookup"
BASE = "https://web.pcc.gov.tw/prkms/tender/common/orgName/toAtm"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("uniform_number", help="8 digit Taiwan uniform number")
    args = p.parse_args()
    if not re.fullmatch(r"\d{8}", args.uniform_number):
        raise SystemExit("統編必須是 8 位數字")

    # PCC's vendor-name query page supports a vendor identifier parameter.
    # Keep the URL visible in the saved probe for reproducibility.
    url = BASE + "?orgName=" + quote(args.uniform_number) + "&orgId="
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"{args.uniform_number}.html"
    req = Request(url, headers={"User-Agent": "TaiwanEntityIntelligence/1.0", "Accept": "text/html,application/xhtml+xml"})
    try:
        with urlopen(req, timeout=30) as response:
            body = response.read()
            target.write_bytes(body)
            print(f"HTTP：{getattr(response, 'status', 200)}")
            print(f"URL：{url}")
            print(f"大小：{len(body):,} bytes")
            print(f"保存：{target}")
            # Print a tiny visible clue without attempting to infer data yet.
            text = body.decode("utf-8", errors="replace")
            for token in ("統編", "廠商", "決標", "標案"):
                if token in text:
                    print(f"頁面包含關鍵字：{token}")
            return 0
    except Exception as exc:
        print(f"查詢失敗：{exc}")
        print(f"你也可以直接在瀏覽器開啟：{url}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
