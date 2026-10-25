#!/usr/bin/env python3
"""Project Hsinchu County's official multi-category XLSX to sourced group rows."""
import argparse
from collections import Counter
import csv
from hashlib import sha256
from pathlib import Path
import re
import sys
from zipfile import ZipFile
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.civil_roster_sources import SOURCES

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
SOURCE_KEY = "hsinchu_county_20261005"
FIELDS = ("團體名稱", "團體類別", "官方編號", "成立日期", "xlsx_sheet", "xlsx_row", "xlsx_sha256")


def convert(source: Path, destination: Path):
    if source.resolve() == destination.resolve() or source.stat().st_size > 10_000_000:
        raise ValueError("Invalid official XLSX input")
    digest = sha256(source.read_bytes()).hexdigest()
    with ZipFile(source) as package:
        members = {entry.filename: entry for entry in package.infolist()}
        if any(entry.file_size > 20_000_000 for entry in members.values()):
            raise ValueError("XLSX member too large")
        workbook = ET.fromstring(package.read("xl/workbook.xml"))
        sheets = workbook.findall(f"{NS}sheets/{NS}sheet")
        if len(sheets) != 1 or sheets[0].get("name") != "完成":
            raise ValueError("Unexpected official XLSX sheet")
        strings = []
        if "xl/sharedStrings.xml" in members:
            shared = ET.fromstring(package.read("xl/sharedStrings.xml"))
            strings = ["".join(item.itertext()) for item in shared.findall(f"{NS}si")]
        root = ET.fromstring(package.read("xl/worksheets/sheet1.xml"))
    output, seen, counts = [], set(), Counter()
    category = None
    for row in root.findall(f"{NS}sheetData/{NS}row"):
        row_number = int(row.get("r", "0"))
        fields = {}
        for cell in row.findall(f"{NS}c"):
            column = re.match(r"[A-Z]+", cell.get("r", ""))
            if column is None:
                raise ValueError("Invalid XLSX cell address")
            value = cell.find(f"{NS}v")
            text = value.text if value is not None else "".join(cell.itertext())
            if cell.get("t") == "s" and text:
                text = strings[int(text)]
            fields[column.group()] = (text or "").strip()
        first, name = fields.get("A", ""), fields.get("B", "")
        if "新竹縣人民團體名冊" in first:
            match = re.fullmatch(r"(?:[一二三四五六七八九十]+、)?新竹縣人民團體名冊（(.+)）", first)
            if not match or match.group(1) not in SOURCES[SOURCE_KEY]["category_counts"]:
                raise ValueError(f"Unexpected official category at XLSX row {row_number}")
            category = match.group(1)
            continue
        if first == "編號" and name == "團體名稱":
            continue
        if first.isdecimal():
            if not category or not name or len(name) > 500 or (category, first) in seen:
                raise ValueError(f"Invalid organization at XLSX row {row_number}")
            seen.add((category, first))
            counts[category] += 1
            output.append((name, category, first, fields.get("F", ""),
                           "完成", row_number, digest))
        elif name:
            raise ValueError(f"Unrecognized official row {row_number}")
    if counts != SOURCES[SOURCE_KEY]["category_counts"] or len(output) != SOURCES[SOURCE_KEY]["expected_rows"]:
        raise ValueError("Official category counts changed; review source before publishing")
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
