#!/usr/bin/env python3
"""Build one reviewed award bundle from an existing PCC notice; no DB writes.

The operator must verify the Company UUID against Development's published exact
uniform identifier and registry Evidence before applying the emitted bundle.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.procurement_materialization import API, build_contract_bundle  # noqa: E402
from src.sources.procurement import _json_get, is_award_notice  # noqa: E402


def latest_notice(payload, filename):
    rows = payload.get("records") if isinstance(payload.get("records"), list) else []
    awards = [row for row in rows if isinstance(row, dict) and is_award_notice(row)]
    if not awards:
        raise ValueError("No award notice exists for the case")
    latest_date = max(str(row.get("date") or "") for row in awards)
    latest = [row for row in awards if str(row.get("date") or "") == latest_date]
    if len(latest) != 1 or latest[0].get("filename") != filename:
        raise ValueError("Requested filename is not the latest award notice")
    return latest[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--job-number", required=True)
    parser.add_argument("--notice-filename", required=True)
    parser.add_argument("--company-uniform", required=True)
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--company-entity-id", required=True)
    args = parser.parse_args()
    UUID(args.company_entity_id)
    url = API + "?" + urlencode({"unit_id": args.unit_id, "job_number": args.job_number})
    notice = latest_notice(_json_get(url, timeout=20), args.notice_filename)
    bundle = build_contract_bundle(
        notice, company_entity_id=args.company_entity_id,
        company_uniform=args.company_uniform, company_name=args.company_name,
        retrieved_at=datetime.now(timezone.utc).isoformat())
    print(json.dumps(bundle, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
