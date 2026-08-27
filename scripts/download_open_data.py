#!/usr/bin/env python3
"""Download selected Taiwan Government Open Data datasets to data/raw.

Uses the official data.gov.tw metadata API to discover each dataset's current
resourceDownloadUrl(s), so URLs do not need to be hard-coded and changed
manually. Files are saved locally for later ingestion into the T.E.I. database.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

DATASET_IDS = [
    176455,  # 165 stopped-resolving suspected fraud websites
    160055,  # 165 fake investment/gambling websites
    38262,   # 165 fraud rumor/refutation
    165027,  # moda/TWNIC fraud-domain list
    109896,  # MOL Labor Standards Act violations
    109897,  # MOL Gender Equality Act violations
    110908,  # MOL Employment Service Act violations
    23838,   # Government procurement award statistics (example official dataset)
]

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw"
META = OUT / "_metadata"
CATALOG = "https://data.gov.tw/api/v2/rest/dataset/{}"


def safe_name(text: str) -> str:
    text = re.sub(r"[^\w\-\u4e00-\u9fff]+", "_", text, flags=re.UNICODE).strip("_")
    return text[:100] or "dataset"


def http_get(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "TaiwanEntityIntelligence/0.1"})
    with urlopen(req, timeout=45) as r:
        return r.read()


def extract_distributions(meta: dict) -> list[dict]:
    """Handle minor schema differences used by data.gov.tw metadata."""
    for key in ("distribution", "distributions", "resources"):
        value = meta.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    for key in ("dataset", "data"):
        obj = meta.get(key)
        if isinstance(obj, dict):
            return extract_distributions(obj)
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Download official Taiwan open-data resources.")
    parser.add_argument("--dataset", action="append", type=int, dest="datasets",
                        help="Dataset ID; repeat for multiple IDs. Defaults to the T.E.I. starter set.")
    args = parser.parse_args()
    dataset_ids = args.datasets or DATASET_IDS

    OUT.mkdir(parents=True, exist_ok=True)
    META.mkdir(parents=True, exist_ok=True)
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest = []

    print(f"T.E.I. open-data download\nOutput: {OUT}")
    for dataset_id in dataset_ids:
        meta_url = CATALOG.format(dataset_id)
        print(f"\n[{dataset_id}] metadata: {meta_url}")
        try:
            raw_meta = http_get(meta_url)
            meta = json.loads(raw_meta.decode("utf-8-sig"))
        except Exception as exc:
            print(f"  metadata ERROR: {exc}", file=sys.stderr)
            manifest.append({"dataset_id": dataset_id, "status": "metadata_error", "error": str(exc)})
            continue

        title = meta.get("title") or meta.get("name") or f"dataset_{dataset_id}"
        meta_path = META / f"{dataset_id}_{safe_name(str(title))}.json"
        meta_path.write_bytes(raw_meta)

        distributions = extract_distributions(meta)
        if not distributions:
            print("  no distribution/resource URL found")
            manifest.append({"dataset_id": dataset_id, "title": title, "status": "no_resource"})
            continue

        downloaded = 0
        for idx, dist in enumerate(distributions, 1):
            url = dist.get("resourceDownloadUrl") or dist.get("resourceDownloadURL") or dist.get("downloadUrl") or dist.get("accessURL")
            if not url:
                continue
            fmt = str(dist.get("format") or "").lower()
            ext = ".json"
            if "csv" in fmt or ".csv" in url.lower():
                ext = ".csv"
            elif "xml" in fmt or ".xml" in url.lower():
                ext = ".xml"
            elif "zip" in fmt or ".zip" in url.lower():
                ext = ".zip"
            name = f"{dataset_id}_{idx}_{safe_name(str(title))}{ext}"
            dest = OUT / name
            print(f"  downloading: {url}")
            try:
                payload = http_get(str(url))
                dest.write_bytes(payload)
                downloaded += 1
                print(f"  saved: {dest.name} ({len(payload):,} bytes)")
                manifest.append({
                    "dataset_id": dataset_id,
                    "title": title,
                    "status": "downloaded",
                    "resource_url": url,
                    "path": str(dest.relative_to(ROOT)),
                    "bytes": len(payload),
                    "downloaded_at_utc": run_ts,
                })
            except Exception as exc:
                print(f"  download ERROR: {exc}", file=sys.stderr)
                manifest.append({
                    "dataset_id": dataset_id,
                    "title": title,
                    "status": "download_error",
                    "resource_url": url,
                    "error": str(exc),
                })

        if downloaded == 0:
            manifest.append({"dataset_id": dataset_id, "title": title, "status": "no_downloaded_resource"})

    manifest_path = OUT / f"download_manifest_{run_ts}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nFinished. Manifest: {manifest_path}")
    return 0 if any(x.get("status") == "downloaded" for x in manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
