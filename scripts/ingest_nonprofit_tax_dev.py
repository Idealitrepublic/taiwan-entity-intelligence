#!/usr/bin/env python3
"""Stage the complete MOF tax roster in tei-development; never infer NGO identity."""
import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ingest_civil_organizations_dev import development_environment  # noqa: E402

REQUIRED = {"統一編號", "單位名稱", "機關所在縣市", "最近異動日期", "最近異動原因", "原因說明文字"}


def profile(path: Path):
    digest = sha256(path.read_bytes()).hexdigest()
    seen_ids = set()
    total = invalid = 0
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError("Unexpected MOF tax roster columns")
        for row_number, row in enumerate(reader, 2):
            identifier = (row["統一編號"] or "").strip()
            name = (row["單位名稱"] or "").strip()
            if not name or len(name) > 500 or len(identifier) > 32:
                raise ValueError(f"Invalid MOF row {row_number}")
            if identifier in seen_ids:
                raise ValueError(f"Duplicate tax identifier at row {row_number}")
            seen_ids.add(identifier)
            valid = len(identifier) == 8 and identifier.isascii() and identifier.isdecimal()
            invalid += not valid
            total += 1
    if not total:
        raise ValueError("MOF tax roster is empty")
    return {"snapshot_sha256": digest, "source_rows": total,
            "valid_8_digit_identifiers": total - invalid, "invalid_identifiers": invalid}


def apply(path: Path, summary: dict):
    env = development_environment()
    current = subprocess.run(
        ["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c",
         "select distinct snapshot_sha256 from public.nonprofit_tax_observations"],
        env=env, text=True, capture_output=True, timeout=30)
    if current.returncode:
        raise RuntimeError("Development migration missing or database unreachable")
    if any(value != summary["snapshot_sha256"] for value in current.stdout.splitlines() if value):
        raise ValueError("A different MOF snapshot exists; review versioning before import")
    # The path is only a client-side \copy argument. Reject syntax-bearing paths.
    csv_path = str(path.resolve())
    if "'" in csv_path or "\n" in csv_path or "\\" in csv_path:
        raise ValueError("Unsafe CSV path")
    digest = summary["snapshot_sha256"]
    retrieved = datetime.now(timezone.utc).isoformat()
    script = f"""BEGIN;
create temp table tei_mof_stage (
  csv_line bigint generated always as identity,
  uniform_number text, unit_name text, office_county text,
  last_change_raw text, last_change_reason text, reason_description text
) on commit drop;
\\copy tei_mof_stage (uniform_number,unit_name,office_county,last_change_raw,last_change_reason,reason_description) from '{csv_path}' with (format csv, header true, encoding 'UTF8');
do $$ begin
  if (select count(*) from tei_mof_stage) <> {summary['source_rows']} then
    raise exception 'MOF CSV count changed during import';
  end if;
end $$;
insert into public.nonprofit_tax_observations (
  snapshot_sha256,csv_row,uniform_number_raw,identifier_valid,unit_name,
  office_county,last_change_raw,last_change_reason,reason_description,
  retrieved_at,publication_status
)
select '{digest}', csv_line + 1,
  trim(coalesce(uniform_number,'')),
  trim(coalesce(uniform_number,'')) ~ '^[0-9]{{8}}$', trim(unit_name),
  nullif(trim(office_county),''),nullif(trim(last_change_raw),''),
  nullif(trim(last_change_reason),''),nullif(trim(reason_description),''),
  '{retrieved}'::timestamptz,'published'
from tei_mof_stage
on conflict (snapshot_sha256,csv_row) do nothing;
COMMIT;
"""
    result = subprocess.run(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1",
                             "-v", "VERBOSITY=sqlstate"],
                            input=script, env=env, text=True, capture_output=True,
                            timeout=900)
    if result.returncode:
        codes = re.findall(r"\b(?=[0-9A-Z]*[0-9])[0-9A-Z]{5}\b", result.stderr)
        raise RuntimeError(f"Development tax-roster transaction failed (SQLSTATE {codes[0] if codes else 'unavailable'})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--apply-dev", action="store_true")
    args = parser.parse_args()
    if not args.csv_path.is_file() or args.csv_path.resolve().is_relative_to(ROOT):
        parser.error("Official CSV must be outside the repository")
    summary = profile(args.csv_path)
    if args.apply_dev:
        apply(args.csv_path, summary)
    print(json.dumps({**summary, "published_source_observations": args.apply_dev,
                      "civil_entities_created": 0, "relationships_created": 0},
                     ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        safe = str(error) if isinstance(error, ValueError) or "SQLSTATE" in str(error) else "safe precondition or transaction failed"
        print(f"Ingestion stopped: {safe}", file=sys.stderr)
        raise SystemExit(1) from None
