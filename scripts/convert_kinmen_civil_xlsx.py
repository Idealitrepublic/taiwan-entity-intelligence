#!/usr/bin/env python3
"""Project Kinmen's official society XLSX without contact information."""
import argparse
import csv
from hashlib import sha256
from pathlib import Path
import re
from zipfile import ZipFile
import xml.etree.ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
FIELDS = ("團體名稱", "官方編號", "成立日期", "最後更新時間", "xlsx_sheet", "xlsx_row", "xlsx_sha256")


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
        if len(sheets) != 1 or sheets[0].get("name") != "金門縣社會團體":
            raise ValueError("Unexpected official XLSX sheet")
        strings = []
        if "xl/sharedStrings.xml" in members:
            shared = ET.fromstring(package.read("xl/sharedStrings.xml"))
            strings = ["".join(item.itertext()) for item in shared.findall(f"{NS}si")]
        root = ET.fromstring(package.read("xl/worksheets/sheet1.xml"))
    output, seen = [], set()
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
        if row_number == 1:
            if [fields.get(letter) for letter in "ABCDEFG"] != [
                "資源彙整機關", "編號", "社會團體名稱", "會址", "聯絡電話", "成立日期", "最後更新時間"
            ]:
                raise ValueError("Unexpected official XLSX columns")
            continue
        name, official_id = fields.get("C", ""), fields.get("B", "")
        if not name or len(name) > 500 or not official_id or official_id in seen:
            raise ValueError(f"Invalid organization at XLSX row {row_number}")
        seen.add(official_id)
        output.append((name, official_id, fields.get("F", ""), fields.get("G", ""),
                       "金門縣社會團體", row_number, digest))
    if not output:
        raise ValueError("Official XLSX has no organizations")
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
