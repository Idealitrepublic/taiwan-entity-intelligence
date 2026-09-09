"""Build a reviewed draft bundle from a legacy export; no name-based merges.

python scripts/backfill_entity_model.py --input snapshot.json --output bundle.json
Add --apply only against an explicitly configured development database.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.entities.backfill import build_legacy_bundle  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    snapshot = json.loads(args.input.read_text())
    if len(snapshot.get("companies", [])) > 10 or len(snapshot.get("company_people", [])) > 150:
        parser.error("Phase 1 backfill is limited to 10 companies / 150 role observations per batch")
    bundle, report = build_legacy_bundle(snapshot)
    args.output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2))
    args.output.chmod(0o600)
    if args.apply:
        url = os.environ.get("TEI_BACKFILL_SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url.startswith("https://") or not key:
            parser.error("Explicit TEI_BACKFILL_SUPABASE_URL and server-only SUPABASE_SERVICE_ROLE_KEY required")
        request = urllib.request.Request(url.rstrip("/") + "/rest/v1/rpc/tei_ingest_bundle",
            data=json.dumps({"bundle": bundle}).encode(), method="POST",
            headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            report["apply"] = json.load(response)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
