#!/usr/bin/env python3
"""Publish one verified MOI/MOL group CSV into tei-development only."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ingest_civil_organizations_dev import apply_bundles  # noqa: E402
from src.civil_organizations import utc_now  # noqa: E402
from src.civil_roster_sources import SOURCES, official_roster_bundles  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_key", choices=sorted(SOURCES))
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--apply-dev", action="store_true")
    args = parser.parse_args()
    if not args.csv_path.is_file() or args.csv_path.resolve().is_relative_to(ROOT):
        parser.error("CSV must be an existing file outside the repository")
    status = "published" if args.apply_dev else "draft"
    bundles = list(official_roster_bundles(args.csv_path, args.source_key,
                                           retrieved_at=utc_now(), publication_status=status))
    count = sum(len(bundle["entities"]) for bundle in bundles)
    if not count:
        parser.error("Official CSV is empty")
    if args.apply_dev:
        apply_bundles(bundles, source_name=SOURCES[args.source_key]["name"])
    print(json.dumps({"source": args.source_key, "rows": count,
                      "published_to_development": args.apply_dev,
                      "name_only_merges": 0, "relationships": 0}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError) as error:
        print(f"Ingestion stopped: {str(error) if isinstance(error, ValueError) else 'safe precondition or transaction failed'}", file=sys.stderr)
        raise SystemExit(1) from None
