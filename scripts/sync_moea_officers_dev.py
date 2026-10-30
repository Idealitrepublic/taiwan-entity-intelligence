#!/usr/bin/env python3
"""Archive the official officer CSV, then index its source-scoped observations.

Only tei-development can be written. The raw file is private in tei-raw;
published source_records retain the exact company ID and row provenance.
No person entities or cross-company relationships are created by name.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ops_backup import database_environment  # noqa: E402
from scripts.ingest_civil_organizations_dev import (  # noqa: E402
    DEVELOPMENT_WRITE_STOP_BYTES, capacity_guard_sql,
)

PROJECT = "canqjiokrtcxkwblhmml"
DATASET = "https://data.gov.tw/dataset/96731"
RESOURCE = "https://data.gcis.nat.gov.tw/od/file?oid=7E5201D9-CAD2-494E-8920-5319D66F66A1"
REQUIRED = {"統一編號", "公司名稱", "職稱", "姓名", "所代表法人", "持有股份數"}


def capacity_plan(database_bytes: int, stage_bytes: int, valid_rows: int) -> dict:
    """Conservative planning bound, not an exact PostgreSQL storage prediction."""
    values = (database_bytes, stage_bytes, valid_rows)
    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError("Capacity inputs must be nonnegative integer byte/row counts")
    estimate = stage_bytes * 4 + valid_rows * 2048
    return {"database_bytes": database_bytes, "estimated_growth_bytes": estimate,
            "stop_bytes": DEVELOPMENT_WRITE_STOP_BYTES,
            "allowed": database_bytes + estimate < DEVELOPMENT_WRITE_STOP_BYTES}


def require_index_capacity(stage: Path, valid_rows: int) -> dict:
    # Check before even uploading the raw archive: manual --confirm-capacity
    # cannot bypass the free-project budget. A rejected input stays local.
    env = {**os.environ, **database_environment(os.environ.get("TEI_DEV_DATABASE_URL", "")),
           "PGCONNECT_TIMEOUT": "10"}
    result = subprocess.run(
        ["psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-c",
         "select pg_database_size(current_database())"],
        capture_output=True, text=True, env=env, timeout=25)
    if result.returncode or not result.stdout.strip().isdigit():
        raise RuntimeError("Development capacity probe failed; details suppressed")
    plan = capacity_plan(int(result.stdout.strip()), stage.stat().st_size, valid_rows)
    if not plan["allowed"]:
        raise RuntimeError("Development capacity guard: retain official snapshot locally; no upload/index performed")
    return plan


def download(destination: Path) -> None:
    request = urllib.request.Request(RESOURCE, headers={"User-Agent": "T.E.I. Development snapshot/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response, destination.open("wb") as output:
        if response.status != 200:
            raise RuntimeError("Official officer CSV unavailable")
        shutil.copyfileobj(response, output)


def prepare(source: Path, stage: Path) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    with source.open("rb") as original:
        for block in iter(lambda: original.read(1024 * 1024), b""):
            digest.update(block)
    valid = invalid = 0
    with source.open("r", encoding="utf-8-sig", newline="") as original, stage.open("w", encoding="utf-8", newline="") as output:
        reader = csv.DictReader(original)
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError("Official officer CSV columns changed; no import performed")
        writer = csv.writer(output)
        for source_row, row in enumerate(reader, start=2):
            uniform = str(row.get("統一編號") or "").strip()
            if len(uniform) != 8 or not uniform.isascii() or not uniform.isdigit() or not str(row.get("姓名") or "").strip():
                invalid += 1
                continue
            raw = {**row, "_source_row": source_row}
            writer.writerow((f"moea_officers:{digest.hexdigest()}:{source_row}", uniform, json.dumps(raw, ensure_ascii=False, separators=(",", ":"))))
            valid += 1
    return digest.hexdigest(), valid, invalid


def archive(source: Path, object_path: str, token: str) -> None:
    if not token:
        raise RuntimeError("Local Development Storage write credential is required; never put it in Preview")
    try:
        from tusclient import client as tus_client
    except ImportError as exc:
        raise RuntimeError("Install tuspy locally to upload the official raw CSV") from exc
    base = f"https://{PROJECT}.supabase.co"
    headers = {"apikey": token, "Authorization": f"Bearer {token}"}
    info = urllib.request.Request(f"{base}/storage/v1/object/info/tei-raw/{object_path}", headers=headers)
    try:
        with urllib.request.urlopen(info, timeout=30):
            return  # Content-addressed object already archived.
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise RuntimeError("Development Storage lookup failed") from None
    upload = tus_client.TusClient(
        f"https://{PROJECT}.storage.supabase.co/storage/v1/upload/resumable",
        headers={**headers, "x-upsert": "false"})
    metadata = {"bucketName": "tei-raw", "objectName": object_path,
                "contentType": "text/csv", "cacheControl": "3600"}
    with source.open("rb") as stream:
        upload.uploader(file_stream=stream, chunk_size=6 * 1024 * 1024, metadata=metadata).upload()


def index(stage: Path, source: Path, digest: str, valid: int, invalid: int, retrieved_at: str, object_path: str) -> None:
    env = {**os.environ, **database_environment(os.environ.get("TEI_DEV_DATABASE_URL", "")), "PGCONNECT_TIMEOUT": "10"}
    if not shutil.which("psql"):
        raise RuntimeError("psql is required for Development indexing")
    file_id = uuid.uuid5(uuid.NAMESPACE_URL, DATASET + "#" + digest)
    # The stage path comes from a private TemporaryDirectory, never from CSV content.
    sql = f"""BEGIN;
{capacity_guard_sql()}
SET LOCAL statement_timeout = '20min';
INSERT INTO public.source_files
 (id,dataset,object_path,file_name,format,size_bytes,sha256,source_url,downloaded_at,indexed_at,status,metadata)
VALUES ('{file_id}','moea_officers','{object_path}','moea-officers.csv','csv',{source.stat().st_size},
 '{digest}','{DATASET}','{retrieved_at}',now(),'indexed',
 '{{"valid_rows":{valid},"invalid_rows":{invalid},"resource_url":"{RESOURCE}"}}'::jsonb)
ON CONFLICT (id) DO NOTHING;
CREATE TEMP TABLE tei_officers_stage (id text, uniform_number text, raw jsonb) ON COMMIT DROP;
\\copy tei_officers_stage FROM '{stage}' WITH (FORMAT csv)
INSERT INTO public.source_records
 (id,source_file_id,dataset,uniform_number,company_name,title,summary,source_url,raw,indexed_at)
SELECT id,'{file_id}','moea_officers',uniform_number,raw->>'公司名稱',
 '經濟部公司登記董監事資料','公司統編與來源列可核對；人物身分限本公司來源範圍','{DATASET}',raw,now()
FROM tei_officers_stage ON CONFLICT (id) DO NOTHING;
{capacity_guard_sql()}
COMMIT;
"""
    result = subprocess.run(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1"], input=sql,
                            text=True, capture_output=True, env=env, timeout=1800)
    if result.returncode:
        raise RuntimeError("Development officer index failed; transaction rolled back (details redacted)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, help="Already downloaded official CSV outside this repository")
    parser.add_argument("--apply", action="store_true", help="Archive and index only in tei-development")
    parser.add_argument("--confirm-capacity", action="store_true", help="Confirm Development Storage and Postgres quotas were reviewed")
    args = parser.parse_args()
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix="tei-moea-officers-") as temporary:
        folder = Path(temporary)
        source = args.file.resolve() if args.file else folder / "official.csv"
        if source.is_relative_to(ROOT):
            raise RuntimeError("Keep official raw files outside the Git repository")
        if not args.file:
            download(source)
        stage = folder / "stage.csv"
        digest, valid, invalid = prepare(source, stage)
        if valid < 1000:
            raise RuntimeError("Official bulk file appears incomplete; no import performed")
        print(json.dumps({"valid_rows": valid, "invalid_rows": invalid, "sha256": digest,
                          "target": "tei-development", "applied": False}))
        if not args.apply:
            return 0
        if not args.confirm_capacity:
            raise RuntimeError("Review Free-project Storage and Postgres capacity before --apply --confirm-capacity")
        # Validate the database target before any Storage write.
        database_environment(os.environ.get("TEI_DEV_DATABASE_URL", ""))
        require_index_capacity(stage, valid)
        object_path = f"moea_officers/{digest}.csv"
        archive(source, object_path, os.environ.get("TEI_DEV_STORAGE_TOKEN", ""))
        index(stage, source, digest, valid, invalid, datetime.now(timezone.utc).isoformat(), object_path)
        print(json.dumps({"target": "tei-development", "applied": True, "valid_rows": valid,
                          "private_storage_object": object_path}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
