#!/usr/bin/env python3
"""Project Changhua's official roster to source-located organization rows."""
import argparse
import csv
from hashlib import sha256
from pathlib import Path
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.convert_official_civil_ods import TABLE, cells_for_row

FIELDS = ("團體名稱", "團體類別", "官方編號", "ods_sheet", "ods_row", "ods_sha256")


def convert(source: Path, destination: Path):
    if source.resolve() == destination.resolve() or source.stat().st_size > 10_000_000:
        raise ValueError("Invalid official ODS input")
    digest = sha256(source.read_bytes()).hexdigest()
    with zipfile.ZipFile(source) as package:
        root = ET.fromstring(package.read("content.xml"))
    sheets = root.findall(f".//{{{TABLE}}}table")
    if len(sheets) != 1:
        raise ValueError("Unexpected official ODS sheet count")
    sheet = sheets[0]
    rows = sheet.findall(f"{{{TABLE}}}table-row")
    output = []
    seen = set()
    for row_number, row in enumerate(rows, 1):
        fields = cells_for_row(row)
        if not any(fields):
            continue
        if len(fields) < 3 or not all(fields[:3]) or len(fields[2]) > 500:
            raise ValueError(f"Invalid official organization at ODS row {row_number}")
        if fields[0] in seen:
            raise ValueError(f"Duplicate official identifier at ODS row {row_number}")
        seen.add(fields[0])
        output.append((fields[2], fields[1], fields[0], sheet.get(f"{{{TABLE}}}name", ""),
                       row_number, digest))
    if not output:
        raise ValueError("Official ODS has no organization rows")
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(FIELDS)
        writer.writerows(output)
    destination.chmod(0o600)
    return len(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(f"converted_rows={convert(args.source, args.destination)}")
