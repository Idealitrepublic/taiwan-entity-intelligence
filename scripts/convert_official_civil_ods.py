#!/usr/bin/env python3
"""Convert an official ODS roster to a minimal, source-located CSV outside Git.

Only organization name, source date/category and sheet/row location are kept.
Contact details and personal names never enter the output.
"""
import argparse
import csv
from hashlib import sha256
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
FIELDS = ("團體名稱", "成立日期", "團體分類", "ods_sheet", "ods_row", "ods_sha256")


def cells_for_row(row):
    cells = []
    for cell in row:
        if cell.tag not in (f"{{{TABLE}}}table-cell", f"{{{TABLE}}}covered-table-cell"):
            continue
        value = " ".join("".join(p.itertext()).strip()
                         for p in cell.findall(f"{{{TEXT}}}p")).strip()
        repeat = int(cell.get(f"{{{TABLE}}}number-columns-repeated", "1"))
        if repeat > 64:
            repeat = 64
        cells.extend([value] * repeat)
    return cells


def convert(source: Path, destination: Path):
    if source.resolve() == destination.resolve() or source.stat().st_size > 10_000_000:
        raise ValueError("Invalid official ODS input")
    digest = sha256(source.read_bytes()).hexdigest()
    with zipfile.ZipFile(source) as package:
        root = ET.fromstring(package.read("content.xml"))
    output = []
    for sheet in root.findall(f".//{{{TABLE}}}table"):
        name = sheet.get(f"{{{TABLE}}}name", "")
        header = None
        for row_number, row in enumerate(sheet.findall(f"{{{TABLE}}}table-row"), 1):
            cells = cells_for_row(row)
            if not any(cells):
                continue
            if header is None:
                header = {value: index for index, value in enumerate(cells) if value}
                if "團體名稱" not in header:
                    raise ValueError("Unexpected official ODS columns")
                continue
            def field(column):
                index = header.get(column, -1)
                return cells[index].strip() if 0 <= index < len(cells) else ""
            organization = field("團體名稱")
            if not organization or len(organization) > 500:
                raise ValueError("Invalid official ODS organization row")
            output.append((organization, field("成立日期"), field("團體分類"),
                           name, row_number, digest))
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
