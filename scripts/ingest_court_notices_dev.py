#!/usr/bin/env python3
"""Dry-run or atomically import three reviewed case announcements to Development.

No personal records, identity merges, Relationships, migrations or UI changes.
"""
import argparse
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ingest_civil_organizations_dev import (  # noqa: E402
    capacity_guard_sql, development_environment,
)
from scripts.ops_backup import DEV_REF  # noqa: E402
from src.sources.court_notices import SOURCE, reviewed_bundle  # noqa: E402


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def check_backup(path):
    if path.resolve().is_relative_to(ROOT) or path.stat().st_mode & 0o077:
        raise ValueError("Use an owner-only encrypted backup manifest outside Git")
    data = json.loads(path.read_text())
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(data["created_at"])).total_seconds()
    if (data.get("project_ref") != DEV_REF or data.get("archive_verified") is not True
            or not 0 <= age < 86_400):
        raise ValueError("A verified Development backup from the last 24 hours is required")
    expected = data.get("encrypted_files", {})
    if set(expected) != {"development.dump.age", "sync-evidence.tar.age"}:
        raise ValueError("Incomplete encrypted backup")
    for filename, digest in expected.items():
        encrypted = path.parent / filename
        hasher = sha256()
        with encrypted.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        if hasher.hexdigest() != digest:
            raise ValueError("Encrypted backup checksum mismatch")


def run_sql(sql, env):
    result = subprocess.run(["psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
                            input=sql, env=env, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError("Development SQL failed; credentials and server details suppressed")
    return result.stdout.strip()


def apply(bundle, receipt, backup_manifest):
    check_backup(backup_manifest)
    if (receipt.resolve().is_relative_to(ROOT) or receipt.exists()
            or receipt.parent.stat().st_mode & 0o077):
        raise ValueError("Receipt must be a new file in an owner-only directory outside Git")
    env = development_environment()  # Strict Dev URL parser, ignored 0600 .env.local.
    source = literal(SOURCE)
    baseline = json.loads(run_sql("select jsonb_build_object("
                                 "'entities',(select count(*) from public.entities),"
                                 "'evidence',(select count(*) from public.evidence_records),"
                                 "'relationships',(select count(*) from public.relationships),"
                                 "'source_entities',(select coalesce(jsonb_agg(id),'[]'::jsonb) "
                                 f"from public.entities where source={source}),"
                                 "'source_evidence',(select coalesce(jsonb_agg(id),'[]'::jsonb) "
                                 f"from public.evidence_records where source_name={source}))", env))
    new_entities = [e["id"] for e in bundle["entities"] if e["id"] not in baseline["source_entities"]]
    new_evidence = [e["id"] for e in bundle["evidence"] if e["id"] not in baseline["source_evidence"]]
    if (set(baseline["source_entities"]) - {e["id"] for e in bundle["entities"]}
            or set(baseline["source_evidence"]) - {e["id"] for e in bundle["evidence"]}):
        raise ValueError("Existing source version differs; review before inserting or withdrawing")
    document = {"project_ref": DEV_REF, "state": "prepared", "baseline": baseline,
                "new_entity_ids": new_entities, "new_evidence_ids": new_evidence,
                "expected_case_groups": 3, "personal_records": 0, "new_relationships": 0}
    # Record the planned delta BEFORE the transaction, including disconnect recovery.
    with receipt.open("x", encoding="utf-8") as stream:
        receipt.chmod(0o600)
        json.dump(document, stream, ensure_ascii=False, indent=2)
    checks = f"""
DO $$BEGIN
 IF (SELECT count(*) FROM public.entities) <> {baseline['entities'] + len(new_entities)}
 OR (SELECT count(*) FROM public.evidence_records) <> {baseline['evidence'] + len(new_evidence)}
 OR (SELECT count(*) FROM public.relationships) <> {baseline['relationships']}
 OR (SELECT count(*) FROM public.entities WHERE source={source}
     AND entity_type='Judgment' AND publication_status='published') <> 3
 OR (SELECT count(*) FROM public.evidence_records WHERE source_name={source}
     AND publication_status='published' AND status='active') <> 3
 THEN RAISE EXCEPTION 'Unexpected ingestion delta'; END IF;
END$$;
"""
    sql = ("BEGIN; SET LOCAL standard_conforming_strings=on; SET LOCAL lock_timeout='10s'; "
           "SET LOCAL statement_timeout='45s';\n" + capacity_guard_sql()
           + "SELECT public.tei_ingest_bundle(" + literal(json.dumps(bundle, ensure_ascii=False))
           + "::jsonb);\n" + checks + capacity_guard_sql() + "COMMIT;")
    run_sql(sql, env)
    document["state"] = "committed"
    receipt.write_text(json.dumps(document, ensure_ascii=False, indent=2))
    receipt.chmod(0o600)
    return {"case_groups": 3, "new_entities": len(new_entities),
            "new_evidence": len(new_evidence), "new_relationships": 0, "personal_records": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_directory", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--apply-dev", action="store_true")
    parser.add_argument("--backup-manifest", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.source_directory.resolve().is_relative_to(ROOT):
        parser.error("Official originals must stay outside Git")
    bundle = reviewed_bundle(args.source_directory, as_of=args.as_of,
                             publication_status="published" if args.apply_dev else "draft")
    if args.apply_dev:
        if not args.receipt or not args.backup_manifest:
            parser.error("Applying requires --receipt and --backup-manifest")
        result = apply(bundle, args.receipt, args.backup_manifest)
    else:
        result = {"case_groups": len(bundle["entities"]), "evidence": len(bundle["evidence"]),
                  "personal_records": 0, "relationships": 0}
    print(json.dumps({"mode": "development" if args.apply_dev else "dry_run", **result}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, RuntimeError, subprocess.TimeoutExpired):
        print("Ingestion stopped; source, backup or Development transaction precondition failed. "
              "Inspect receipt before retrying; no credentials logged.", file=sys.stderr)
        raise SystemExit(1) from None
