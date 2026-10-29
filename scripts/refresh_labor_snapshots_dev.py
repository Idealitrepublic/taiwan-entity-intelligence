"""Import only genuinely new MOL raw-row versions; never merge by company name."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ingest_civil_organizations_dev import development_environment  # noqa: E402
from scripts.ingest_labor_penalties_dev import DATASETS, REQUIRED, indexed_rows, sql_snapshot  # noqa: E402


def new_rows(dataset_id, payload, known_ids):
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    if not REQUIRED.issubset(set(reader.fieldnames or [])):
        raise ValueError("Official labor CSV schema changed")
    rows = [row for row in reader if row.get("事業單位名稱或負責人", "").strip()]
    if not rows:
        raise ValueError("Empty source snapshot is not a successful refresh")
    by_id = {record[0]: raw for raw, record in zip(rows, indexed_rows(dataset_id, rows), strict=True)}
    return [row for key, row in by_id.items() if key not in known_ids], {
        "source_rows": len(rows), "unique_source_rows": len(by_id),
        "duplicate_source_rows": len(rows) - len(by_id), "new_raw_versions": len(set(by_id) - known_ids)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_directory", type=Path)
    parser.add_argument("--apply-dev", action="store_true")
    args = parser.parse_args()
    folder = args.snapshot_directory.resolve()
    if folder.is_relative_to(ROOT) or folder.stat().st_mode & 0o077:
        parser.error("Use owner-only official snapshots outside the repository")
    env = development_environment()
    result = subprocess.run(["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c",
                             "select coalesce(jsonb_agg(id),'[]') from public.source_records where dataset='penalties'"],
                            text=True, capture_output=True, env=env, timeout=60)
    if result.returncode:
        raise RuntimeError("Development read failed; credentials suppressed")
    known = set(json.loads(result.stdout))
    inventory = {row["dataset"]: row for row in json.loads((folder / "inventory.json").read_text())}
    plans, reports = [], []
    for dataset_id in DATASETS:
        path = folder / (dataset_id + ".csv")
        payload = path.read_bytes()
        source = inventory[dataset_id]
        if source["status"] != "downloaded_not_imported" or hashlib.sha256(payload).hexdigest() != source["sha256"]:
            raise ValueError("Official snapshot hash mismatch")
        if not source["source_url"].startswith("https://apiservice.mol.gov.tw/OdService/download/"):
            raise ValueError("Source must be an official MOL download")
        additions, report = new_rows(dataset_id, payload, known)
        report["dataset"] = dataset_id
        reports.append(report)
        sql = sql_snapshot(dataset_id, source["source_url"], payload, additions,
                           downloaded_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat())
        plans.append(sql.removeprefix("BEGIN;\n").removesuffix("COMMIT;\n").replace(
            "tei_penalty_stage", "tei_penalty_stage_" + dataset_id))
    if sum(report["new_raw_versions"] for report in reports) > 2000:
        raise ValueError("Labor delta exceeds reviewed capacity batch; no import")
    if args.apply_dev:
        sql = ("BEGIN; SET LOCAL standard_conforming_strings=on; SET LOCAL statement_timeout='90s'; "
               "DO $$BEGIN IF pg_database_size(current_database())>480000000 THEN RAISE EXCEPTION 'Development capacity guard'; END IF; END$$;\n"
               + "\n".join(plans) + "\nCOMMIT;\n")
        result = subprocess.run(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1"], input=sql,
                                text=True, capture_output=True, env=env, timeout=180)
        if result.returncode:
            raise RuntimeError("Development labor refresh rolled back; connection details suppressed")
    report = {"applied_to_development": args.apply_dev, "datasets": reports,
              "historical_records_deleted": 0, "name_only_relationships_created": 0}
    output = folder / "refresh_result.json"
    output.write_text(json.dumps(report, ensure_ascii=False))
    output.chmod(0o600)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
