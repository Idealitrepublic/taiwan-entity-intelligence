#!/usr/bin/env python3
"""Convert Tainan's official social-welfare foundation JSON to minimal CSV."""
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path

FIELDS = ("基金會名稱", "設立許可日期", "設立許可文號", "狀態/備註",
          "json_row", "json_sha256")


def convert(source: Path, destination: Path):
    if source.resolve() == destination.resolve() or source.stat().st_size > 5_000_000:
        raise ValueError("Invalid official JSON input")
    raw = source.read_bytes()
    document = json.loads(raw.decode("utf-8-sig"))
    records = document.get("data") if document.get("success") is True else None
    if not isinstance(records, list) or not records:
        raise ValueError("Unexpected official JSON response")
    digest = sha256(raw).hexdigest()
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(FIELDS)
        for index, record in enumerate(records, 1):
            if not isinstance(record, dict):
                raise ValueError("Unexpected official JSON record")
            name = (record.get("基金會名稱") or "").strip()
            if not name or len(name) > 500:
                raise ValueError("Invalid official foundation name")
            writer.writerow([name, record.get("設立許可日期") or "",
                             record.get("設立許可文號") or "",
                             record.get("狀態/備註") or "", index, digest])
    destination.chmod(0o600)
    return len(records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(f"converted_rows={convert(args.source, args.destination)}")
