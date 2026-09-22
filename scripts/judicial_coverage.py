#!/usr/bin/env python3
"""Repeatable, read-only judicial index and official-case coverage benchmark."""
import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.sources.judicial_index import VERIFIED_CASES, load_index, records_for_company  # noqa: E402


def benchmark(verify_official=False):
    index = load_index()
    records = index.get("records", [])
    verified = json.loads(Path(VERIFIED_CASES).read_text(encoding="utf-8"))["records"]
    jids = [row.get("jid") for row in records]
    counts = Counter(jids)
    present = 0
    official_verified = 0
    details = []
    for row in verified:
        company = row["companies"][0]
        hit = any(item["jid"] == row["jid"] for item in records_for_company(company)["records"])
        official_ok = None
        if verify_official:
            response = subprocess.run(
                ["curl", "-fsSL", "--max-time", "20", row["source_url"]],
                capture_output=True, check=False)
            page = response.stdout.decode("utf-8", "replace")
            official_ok = response.returncode == 0 and company in page and all(
                person in page for person in row.get("mentioned_people", []))
            official_verified += bool(official_ok)
        present += bool(hit)
        details.append({"jid": row["jid"], "company": company,
                        "indexed": hit, "official_verified": official_ok,
                        "person_resolution": "unresolved_name_only"})
    return {
        "index_generated_at": index.get("generated_at"),
        "indexed_records": len(records),
        "unique_jids": len(counts),
        "duplicate_jids": sum(count - 1 for count in counts.values()),
        "historical_before_2025": sum(str(row.get("date", ""))[:4] < "2025" for row in records),
        "verified_case_recall": round(present / len(verified), 3) if verified else 0,
        "official_verification_rate": (round(official_verified / len(verified), 3)
                                       if verify_official and verified else None),
        "benchmark_date": date.today().isoformat(),
        "cases": details,
        "coverage_scope": "sampled known cases; not nationwide historical recall",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-official", action="store_true")
    args = parser.parse_args()
    result = benchmark(args.verify_official)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["verified_case_recall"] < 1 or result["duplicate_jids"]:
        raise SystemExit(1)
    if args.verify_official and result["official_verification_rate"] < 1:
        raise SystemExit(2)
