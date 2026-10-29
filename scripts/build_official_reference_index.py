"""Build an offline, private source index; never connects to Supabase or Vercel.

These are official source observations, not published canonical entities.
Conflicting bill statuses remain separate observations of the same official ID.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
AGENCY_URL = "https://oid.nat.gov.tw/OIDWeb/GDS.csv"
BILL_URL = "https://data.ly.gov.tw/odw/ID20Action.action?term=11&sessionPeriod=&sessionTimes=&meetingTimes=&billName=&billOrg=&billProposer=&billCosignatory=&fileType=json"


def agency_rows(raw):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not {"OrgName", "OID", "OrgCode"}.issubset(set(reader.fieldnames or [])):
        raise ValueError("Official OID schema changed")
    rows, seen = [], set()
    for index, row in enumerate(reader, 2):
        oid, name = row["OID"].strip(), row["OrgName"].strip()
        if not name or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", oid) or oid in seen:
            raise ValueError("Missing or duplicate official agency identifier")
        seen.add(oid)
        rows.append((index, oid, name, row["OrgCode"].strip() or None))
    if not rows:
        raise ValueError("Empty official OID snapshot")
    return rows


def bill_rows(raw):
    payload = json.loads(raw)
    if not isinstance(payload, dict) or not isinstance(payload.get("dataList"), list) or not payload["dataList"]:
        raise ValueError("Official bill snapshot is empty or invalid")
    allowed = ("term", "sessionPeriod", "sessionTimes", "meetingTimes", "billNo", "billName",
               "billOrg", "billProposer", "billCosignatory", "billStatus", "pdfUrl", "docUrl", "selectTerm")
    rows = []
    for index, row in enumerate(payload["dataList"], 1):
        if not isinstance(row, dict) or str(row.get("term")) != "11" or not str(row.get("billNo") or "").strip() or not row.get("billName"):
            raise ValueError("Official bill row lacks term, ID or title")
        # Preserve repeated IDs: a bill may appear at multiple readings or stages.
        rows.append((index, str(row["billNo"]), row["billName"], json.dumps(
            {key: row.get(key) for key in allowed}, ensure_ascii=False, sort_keys=True)))
    return rows


def build(connection, sources):
    connection.executescript("""
    create table if not exists source_snapshots(
      sha256 text primary key,source_url text not null,retrieved_at text not null,source_kind text not null);
    create table if not exists agency_observations(
      snapshot_sha256 text not null references source_snapshots(sha256),csv_row integer not null,
      oid text not null,agency_name text not null,agency_code text,
      source_status text not null default 'source_does_not_certify_current_active_status',
      primary key(snapshot_sha256,oid));
    create index if not exists agency_official_code on agency_observations(agency_code);
    create table if not exists bill_observations(
      snapshot_sha256 text not null references source_snapshots(sha256),source_row integer not null,
      bill_id text not null,bill_name text not null,source_fields text not null,
      primary key(snapshot_sha256,source_row));
    create index if not exists official_bill_id on bill_observations(bill_id);
    """)
    prepared = []
    for kind, raw, url, retrieved in sources:
        if (kind, url) not in (("agencies", AGENCY_URL), ("bills", BILL_URL)):
            raise ValueError("Only the reviewed official source URLs are accepted")
        if datetime.fromisoformat(retrieved).tzinfo is None:
            raise ValueError("Source retrieval timestamp requires timezone")
        rows = agency_rows(raw) if kind == "agencies" else bill_rows(raw)
        prepared.append((kind, hashlib.sha256(raw).hexdigest(), url, retrieved, rows))
    with connection:
        for kind, digest, url, retrieved, rows in prepared:
            connection.execute("insert or ignore into source_snapshots values(?,?,?,?)", (digest, url, retrieved, kind))
            if kind == "agencies":
                connection.executemany("insert or ignore into agency_observations(snapshot_sha256,csv_row,oid,agency_name,agency_code) values(?,?,?,?,?)",
                                       [(digest, *row) for row in rows])
            else:
                connection.executemany("insert or ignore into bill_observations values(?,?,?,?,?)", [(digest, *row) for row in rows])
    if connection.execute("pragma integrity_check").fetchone()[0] != "ok" or connection.execute("pragma foreign_key_check").fetchall():
        raise ValueError("Offline index integrity check failed")
    return {"local_agency_observations": connection.execute("select count(*) from agency_observations").fetchone()[0],
            "local_bill_observations": connection.execute("select count(*) from bill_observations").fetchone()[0],
            "distinct_official_bill_ids": connection.execute("select count(distinct bill_id) from bill_observations").fetchone()[0],
            "canonical_entities_published": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    folder, output = args.snapshot_directory.resolve(), args.output.resolve()
    if (folder.is_relative_to(ROOT) or output.is_relative_to(ROOT) or
            folder.stat().st_mode & 0o077 or output.parent.stat().st_mode & 0o077):
        parser.error("Use private source/output directories outside the repository")
    os.umask(0o077)
    sources = []
    for kind, name, url in (("agencies", "government-agencies.csv", AGENCY_URL), ("bills", "bills-term11.json", BILL_URL)):
        path = folder / name
        sources.append((kind, path.read_bytes(), url, datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()))
    with sqlite3.connect(output) as connection:
        connection.execute("pragma foreign_keys=on")
        result = build(connection, sources)
    output.chmod(0o600)
    print(json.dumps({**result, "database_bytes": output.stat().st_size, "cloud_writes": 0,
                      "scope": "local source index only; not Preview search or national historical coverage"}))


if __name__ == "__main__":
    main()
