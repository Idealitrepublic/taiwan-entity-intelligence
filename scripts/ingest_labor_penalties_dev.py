#!/usr/bin/env python3
"""Rebuild the existing Development penalty index from official MOL CSVs.

The source_files row marks an external snapshot; no Storage object is implied.
Only the explicitly named tei-development database may be changed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.public_evidence import _dataset_resources, _get  # noqa: E402
from scripts.ops_backup import database_environment  # noqa: E402

DATASETS = ("109896", "109897", "110908")
REQUIRED = {"主管機關", "處分日期", "處分字號", "事業單位名稱或負責人", "違法法規法條"}


def official_rows(dataset_id):
    for url in _dataset_resources(dataset_id):
        try:
            payload = _get(url, timeout=90)
            reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig", "replace")))
            if not REQUIRED.issubset(set(reader.fieldnames or [])):
                continue
            rows = [row for row in reader if row.get("事業單位名稱或負責人", "").strip()]
            if rows:
                return url, payload, rows
        except (OSError, UnicodeError, csv.Error):
            continue
    raise RuntimeError(f"Official labor dataset {dataset_id} has no valid CSV resource")


def indexed_rows(dataset_id, rows):
    source_url = f"https://data.gov.tw/dataset/{dataset_id}"
    result = []
    for raw in rows:
        canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True)
        record_id = hashlib.sha256((dataset_id + "|" + canonical).encode()).hexdigest()
        result.append((
            "mol:" + record_id,
            raw["事業單位名稱或負責人"].strip(),
            raw.get("違法法規法條") or "違反勞動法令事業單位",
            raw.get("違反法規內容") or "",
            source_url,
            canonical,
        ))
    return result


def sql_snapshot(dataset_id, source_url, payload, rows):
    digest = hashlib.sha256(payload).hexdigest()
    file_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{source_url}#{digest}")
    now = datetime.now(timezone.utc).isoformat()
    metadata = json.dumps({"provider": "勞動部", "dataset_id": dataset_id,
                           "external_source_only": True}, ensure_ascii=False)
    file_values = [str(file_id), "penalties", f"external/data.gov.tw/{dataset_id}/{digest}.csv",
                   f"mol-{dataset_id}.csv", "CSV", str(len(payload)), digest, source_url, now,
                   now, "indexed", metadata]
    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    output = io.StringIO()
    output.write("BEGIN;\n")
    output.write("INSERT INTO public.source_files "
                 "(id,dataset,object_path,file_name,format,size_bytes,sha256,source_url,downloaded_at,indexed_at,status,metadata) "
                 f"VALUES ({','.join(map(quote, file_values))}) ON CONFLICT (id) DO NOTHING;\n")
    output.write("CREATE TEMP TABLE tei_penalty_stage "
                 "(id text,company_name text,title text,summary text,source_url text,raw jsonb) ON COMMIT DROP;\n")
    output.write("COPY tei_penalty_stage FROM STDIN WITH (FORMAT csv);\n")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(indexed_rows(dataset_id, rows))
    output.write("\\.\n")
    output.write("INSERT INTO public.source_records "
                 "(id,source_file_id,dataset,company_name,title,summary,source_url,raw) "
                 f"SELECT id,'{file_id}'::uuid,'penalties',company_name,title,summary,source_url,raw "
                 "FROM tei_penalty_stage ON CONFLICT (id) DO NOTHING;\nCOMMIT;\n")
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write only to tei-development")
    parser.add_argument("--materialize", action="store_true", help="publish only explicit, registry-verified identifier matches after indexing")
    args = parser.parse_args()
    if args.materialize and not args.apply:
        parser.error("--materialize requires --apply")
    connection = os.environ.get("TEI_DEV_DATABASE_URL", "")
    database_env = database_environment(connection) if args.apply else {}
    for dataset_id in DATASETS:
        source_url, payload, rows = official_rows(dataset_id)
        print(f"{dataset_id}: {len(rows)} official rows, {len(payload)} bytes")
        if not args.apply:
            continue
        env = os.environ.copy()
        env.update(database_env)
        env["PGCONNECT_TIMEOUT"] = "10"
        process = subprocess.run(
            ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1"],
            input=sql_snapshot(dataset_id, source_url, payload, rows),
            text=True, capture_output=True, env=env, timeout=180,
        )
        if process.returncode:
            raise SystemExit(f"Development import failed for {dataset_id}; transaction rolled back")
        print(f"{dataset_id}: Development import committed")
    if args.materialize:
        subprocess.run([sys.executable, str(ROOT / "scripts/materialize_labor_penalties_dev.py"), "--apply"],
                       check=True, env=os.environ.copy())


if __name__ == "__main__":
    main()
