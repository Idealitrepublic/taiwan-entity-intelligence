#!/usr/bin/env python3
"""Project Penghu's official category CSV to organization-only source rows."""
import argparse
import csv
from hashlib import sha256
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.civil_roster_sources import SOURCES

FIELDS = ("團體名稱", "團體類別", "官方編號", "csv_row", "csv_sha256")


def convert(source: Path, destination: Path, source_key: str):
    if not source_key.startswith("penghu_1669") or source_key not in SOURCES:
        raise ValueError("Unsupported official Penghu category")
    if source.resolve() == destination.resolve() or source.stat().st_size > 10_000_000:
        raise ValueError("Invalid official CSV input")
    digest = sha256(source.read_bytes()).hexdigest()
    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"編號", "團體名稱", "理事長及主要人員", "會社址", "人數", "電話"}.issubset(reader.fieldnames or []):
            raise ValueError("Unexpected official CSV columns")
        rows = list(reader)
    output, seen = [], set()
    category = SOURCES[source_key]["category"]
    for row_number, row in enumerate(rows, 2):
        name = (row.get("團體名稱") or "").strip()
        official_id = (row.get("編號") or "").strip()
        if not name and not official_id:
            # The source sometimes has an additional contact-only continuation row.
            continue
        if not name or not official_id or len(name) > 500 or official_id in seen:
            raise ValueError(f"Invalid organization at CSV row {row_number}")
        seen.add(official_id)
        output.append((name, category, official_id, row_number, digest))
    if len(output) != SOURCES[source_key]["expected_rows"]:
        raise ValueError("Official category row count changed; review source before publishing")
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(FIELDS)
        writer.writerows(output)
    destination.chmod(0o600)
    return len(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_key")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(f"converted_rows={convert(args.source, args.destination, args.source_key)}")
