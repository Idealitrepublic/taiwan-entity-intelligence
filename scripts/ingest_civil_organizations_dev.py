#!/usr/bin/env python3
"""Validate and optionally ingest an official MOI roster into tei-development only.

The default is a read-only dry run. `--apply-dev --publish-historical` publishes
source-scoped historical observations, never current-registration claims.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ops_backup import database_environment  # noqa: E402
from scripts.run_dev import read_local_env  # noqa: E402
from src.civil_organizations import roster_bundles, utc_now  # noqa: E402


def development_environment():
    ignored = subprocess.run(["git", "check-ignore", "-q", ".env.local"],
                             cwd=ROOT, check=False)
    if ignored.returncode:
        raise RuntimeError(".env.local must be Git-ignored before connecting")
    local = read_local_env(ROOT / ".env.local")
    value = os.environ.get("TEI_DEV_DATABASE_URL") or local.get("TEI_DEV_DATABASE_URL", "")
    env = os.environ.copy()
    env.update(database_environment(value), PGCONNECT_TIMEOUT="10")
    return env


def ensure_same_snapshot(current_hash, known_hashes):
    if any(value != current_hash for value in known_hashes):
        raise ValueError("A different official snapshot already exists; review withdrawal/versioning before import")


def apply_bundles(bundles, *, source_name="MOI nationwide people's associations roster"):
    env = development_environment()
    probe = subprocess.run(
        ["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c",
         "select count(*) from public.entity_types where code='CivilOrganization'"],
        env=env, text=True, capture_output=True, timeout=30)
    if probe.returncode or probe.stdout.strip() != "1":
        raise RuntimeError("Development migration is missing or database is unreachable")
    snapshot_hash = bundles[0]["evidence"][0]["source_locator"]["snapshot_sha256"]
    if not all(evidence["source_name"] == source_name and
               evidence["source_locator"]["snapshot_sha256"] == snapshot_hash
               for bundle in bundles for evidence in bundle["evidence"]):
        raise ValueError("Mixed source or snapshot in ingestion bundles")
    source_literal = source_name.replace("'", "''")
    check = subprocess.run(
        ["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c",
         "select distinct source_locator->>'snapshot_sha256' from public.evidence_records "
         f"where source_name='{source_literal}'"],
        env=env, text=True, capture_output=True, timeout=30)
    if check.returncode:
        raise RuntimeError("Development snapshot check failed")
    ensure_same_snapshot(snapshot_hash, [value for value in check.stdout.splitlines() if value])
    process = subprocess.Popen(
        ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1"], cwd=ROOT,
        env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, text=True)
    try:
        process.stdin.write("BEGIN;\nSET LOCAL standard_conforming_strings = on;\n")
        for bundle in bundles:
            payload = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
            # Standard-conforming SQL string; source content never becomes SQL.
            literal = payload.replace("'", "''")
            process.stdin.write(f"select public.tei_ingest_bundle('{literal}'::jsonb);\n")
        process.stdin.write("COMMIT;\n")
        process.stdin.close()
    except BrokenPipeError:
        process.kill()
    if process.wait(timeout=900):
        raise RuntimeError("Development ingestion transaction failed; no credentials logged")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="MOI CSV downloaded from the official URL")
    parser.add_argument("--apply-dev", action="store_true")
    parser.add_argument("--publish-historical", action="store_true")
    arguments = parser.parse_args()
    if arguments.publish_historical and not arguments.apply_dev:
        parser.error("--publish-historical requires --apply-dev")
    if not arguments.csv_path.is_file() or arguments.csv_path.is_relative_to(ROOT):
        parser.error("source CSV must be an existing file outside the repository")
    status = "published" if arguments.publish_historical else "draft"
    # Materialize first: a malformed last row must not cause a partial import.
    bundles = list(roster_bundles(arguments.csv_path, retrieved_at=utc_now(),
                                  publication_status=status))
    count = sum(len(bundle["entities"]) for bundle in bundles)
    if not count:
        parser.error("source CSV is empty")
    if arguments.apply_dev:
        apply_bundles(bundles)
    print(json.dumps({"mode": "development" if arguments.apply_dev else "dry_run",
                      "requested_historical_status": status, "source_rows": count,
                      "batches": len(bundles), "name_only_merges": 0,
                      "person_records": 0}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(f"Ingestion stopped: {str(error) if isinstance(error, ValueError) else 'safe precondition or transaction failed'}", file=sys.stderr)
        raise SystemExit(1) from None
