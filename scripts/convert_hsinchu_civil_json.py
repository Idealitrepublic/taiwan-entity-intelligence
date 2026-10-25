#!/usr/bin/env python3
"""Project checked official Hsinchu City HTML category snapshots to CSV."""
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path

FIELDS = ("團體名稱", "團體類別", "官方序號", "來源更新日期", "來源網址",
          "json_category", "json_row", "json_sha256")
OFFICIAL_PAGE = "https://society.hccg.gov.tw/ch/home.jsp?id=161&parentpath=0,3,34"


def convert(source: Path, destination: Path):
    if source.resolve() == destination.resolve() or source.stat().st_size > 5_000_000:
        raise ValueError("Invalid official HTML snapshot")
    raw = source.read_bytes()
    document = json.loads(raw)
    if document.get("source_page") != OFFICIAL_PAGE or len(document.get("categories", [])) != 12:
        raise ValueError("Unexpected official category set")
    output = []
    for category in document["categories"]:
        name = category["category"]
        url = category["url"]
        rows = category["rows"]
        if not url.startswith(OFFICIAL_PAGE + "&mcustomize=formdata_list1.jsp&mclassno="):
            raise ValueError("Unexpected official category URL")
        if category["expected"] != len(rows) or [int(row["seq"]) for row in rows] != list(range(1, len(rows) + 1)):
            raise ValueError("Incomplete official category")
        for row in rows:
            organization = row["name"].strip()
            if not organization or len(organization) > 500:
                raise ValueError("Invalid official organization")
            output.append((organization, name, row["seq"], category["date"], url,
                           name, row["seq"], sha256(raw).hexdigest()))
    if not output:
        raise ValueError("Official categories are empty")
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
