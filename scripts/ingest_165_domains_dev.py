#!/usr/bin/env python3
"""Index the official 165 blocked-domain CSV in tei-development only.

The records describe domains, not companies or people. This script never
creates Entity or Relationship rows and never writes to Production.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_dev import read_local_env  # noqa: E402
from src.public_evidence import _dataset_resources, _get  # noqa: E402


PROJECT_REF = "canqjiokrtcxkwblhmml"
DATASET_URL = "https://data.gov.tw/dataset/176455"
DOMAIN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def normalize_domain(value):
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw if "://" in raw else "https://" + raw)
        if parsed.scheme not in ("http", "https") or parsed.port not in (None, 80, 443):
            return ""
    except ValueError:
        return ""
    host = (parsed.hostname or "").removeprefix("www.").rstrip(".")
    return host if len(host) <= 253 and DOMAIN.fullmatch(host) else ""


def prepare(payload):
    rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
    if not rows or "網域" not in rows[0]:
        raise ValueError("Official 165 CSV has no domain column")
    result = {}
    for row in rows:
        domain = normalize_domain(row.get("網域"))
        if not domain:
            continue
        raw = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        record_id = "165:" + hashlib.sha256(raw.encode()).hexdigest()
        result[record_id] = (domain, raw)
    if len(result) < 100:
        raise ValueError("Official 165 CSV yielded too few valid domains")
    return len(rows), result


def database_env():
    local = read_local_env(ROOT / ".env.local")
    value = os.environ.get("TEI_DEV_DATABASE_URL") or local.get("TEI_DEV_DATABASE_URL", "")
    parsed = urlsplit(value)
    if parsed.scheme not in ("postgres", "postgresql") or not parsed.hostname:
        raise RuntimeError("Invalid Development database connection")
    if PROJECT_REF not in (parsed.hostname or "") and PROJECT_REF not in (parsed.username or ""):
        raise RuntimeError("Only the named tei-development database is allowed")
    return {**os.environ, "PGHOST": parsed.hostname, "PGPORT": str(parsed.port or 5432),
            "PGUSER": unquote(parsed.username or ""), "PGPASSWORD": unquote(parsed.password or ""),
            "PGDATABASE": parsed.path.lstrip("/") or "postgres", "PGSSLMODE": "require",
            "PGCONNECT_TIMEOUT": "10"}


def publish(payload, resource_url, records):
    psql = shutil.which("psql")
    if not psql:
        raise RuntimeError("psql is required")
    digest = hashlib.sha256(payload).hexdigest()
    file_id = uuid.uuid5(uuid.NAMESPACE_URL, DATASET_URL + ":" + digest)
    # The external:// locator explicitly does not claim a Supabase Storage upload.
    object_path = "external://data.gov.tw/176455/" + digest
    metadata = json.dumps({"dataset_id": "176455", "official_resource_url": resource_url,
                           "row_count": len(records), "external_snapshot": True}, ensure_ascii=False)
    def escaped(value):
        return value.replace("'", "''")
    sql = ["BEGIN; SET LOCAL statement_timeout = '180s';",
           "INSERT INTO public.source_files (id,dataset,object_path,file_name,format,size_bytes,sha256,source_url,downloaded_at,indexed_at,status,metadata) "
           f"VALUES ('{file_id}','anti_fraud','{object_path}','165-blocked-domains.csv','csv',{len(payload)},'{digest}','{DATASET_URL}',now(),now(),'indexed','{escaped(metadata)}'::jsonb) "
           "ON CONFLICT (id) DO UPDATE SET indexed_at=now(),metadata=EXCLUDED.metadata;",
           "CREATE TEMP TABLE tei_165_stage(id text, domain text, raw jsonb) ON COMMIT DROP;",
           "COPY tei_165_stage (id,domain,raw) FROM STDIN WITH (FORMAT csv);"]
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for record_id, (domain, raw) in records.items():
        writer.writerow((record_id, domain, raw))
    sql.append(output.getvalue() + "\\.\n")
    sql.extend([
        "INSERT INTO public.source_records (id,source_file_id,dataset,domain,title,summary,source_url,raw,indexed_at) "
        f"SELECT id,'{file_id}','anti_fraud',domain,'165 涉詐網站停止解析','官方網域資料；不代表公司或個人的犯罪認定','{DATASET_URL}',raw,now() FROM tei_165_stage "
        "ON CONFLICT (id) DO UPDATE SET source_file_id=EXCLUDED.source_file_id,domain=EXCLUDED.domain,raw=EXCLUDED.raw,indexed_at=now();",
        "COMMIT;",
    ])
    completed = subprocess.run([psql, "-X", "-q", "-v", "ON_ERROR_STOP=1"], input="\n".join(sql),
                               text=True, capture_output=True, env=database_env(), timeout=240)
    if completed.returncode:
        raise RuntimeError("Development 165 import failed; database transaction rolled back")
    return len(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish-development", action="store_true")
    args = parser.parse_args()
    # Resolve the current official resource; never use the stale hard-coded URL.
    resources = _dataset_resources("176455")
    if not resources:
        raise RuntimeError("No official 165 CSV resource")
    payload = _get(resources[0])
    raw_count, records = prepare(payload)
    print(f"Official rows: {raw_count}; unique valid records: {len(records)}")
    if args.publish_development:
        print(f"Indexed into tei-development: {publish(payload, resources[0], records)}")
    else:
        print("Dry run only; pass --publish-development after review")


if __name__ == "__main__":
    main()
