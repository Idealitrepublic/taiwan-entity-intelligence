#!/usr/bin/env python3
"""Prepare bounded, official Legislative Yuan bundles for the isolated dev DB.

This script only reads public LY APIs and prints draft bundles. A privileged,
reviewed caller must apply and publish them; it never reads production data.
"""

import argparse
from datetime import datetime, timezone
import json
import subprocess

from src.political_master import build_political_master_batches


MEMBERS = "https://data.ly.gov.tw/odw/ID16Action.action?name=&sex=&party=&partyGroup=&areaName=&term=11&fileType=json"
COMMITTEES = "https://data.ly.gov.tw/odw/ID14Action.action?committee=&name=&fileType=json"


def source_rows(url):
    raw = subprocess.check_output(["curl", "--fail", "--silent", "--show-error", "--location", url], timeout=60)
    return json.loads(raw.decode("utf-8-sig"))["dataList"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int)
    parser.add_argument("--count", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    committee_rows = [row for row in source_rows(COMMITTEES)
                      if str(row.get("term")) == "11"]
    batches, report = build_political_master_batches(
        source_rows(MEMBERS), committee_rows,
        retrieved_at=datetime.now(timezone.utc).isoformat(), max_bytes=50000)
    if args.count:
        print(len(batches))
    elif args.report:
        print(json.dumps({"inputs": report["input_counts"],
                          "batches": len(batches),
                          "quality_issues": report["quality_issues"],
                          "skipped_count": len(report["skipped"])},
                         ensure_ascii=False, separators=(",", ":")))
    elif args.batch is not None and 0 <= args.batch < len(batches):
        print(json.dumps(batches[args.batch], ensure_ascii=False, separators=(",", ":")))
    else:
        parser.error("choose --count, --report, or a valid --batch index")


if __name__ == "__main__":
    main()
