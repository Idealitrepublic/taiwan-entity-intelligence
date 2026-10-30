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
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
AGENCY_URL = "https://oid.nat.gov.tw/OIDWeb/GDS.csv"
BILL_URL = "https://data.ly.gov.tw/odw/ID20Action.action?term=11&sessionPeriod=&sessionTimes=&meetingTimes=&billName=&billOrg=&billProposer=&billCosignatory=&fileType=json"


def build_supplementary_sources(connection, folder):
    """Index saved official originals only; never resolve people by their names."""
    from scripts.sync_moea_officers_dev import RESOURCE, REQUIRED
    from scripts.stage_contribution_evidence_dev import SOURCE_URL
    import zipfile

    connection.executescript("""
      create table if not exists source_snapshots(
        sha256 text primary key,source_url text not null,retrieved_at text not null,source_kind text not null);
      create table if not exists officer_observations(
        snapshot_sha256 text references source_snapshots(sha256),source_row integer,
        company_id text,company_name text,person_name text,position text,representative text,shares text,
        identity_scope text not null default 'company_source_observation_not_resolved_person',
        primary key(snapshot_sha256,source_row));
      create index if not exists officer_company_id on officer_observations(company_id);
      create table if not exists contribution_observations(
        snapshot_sha256 text references source_snapshots(sha256),source_row integer,
        donor_uniform text,donor_name text,candidate_name text,election text,date_raw text,amount_raw text,
        return_note text,correction_note text,resolution_status text not null default 'UNRESOLVED',
        primary key(snapshot_sha256,source_row));
      create index if not exists contribution_donor_id on contribution_observations(donor_uniform);
    """)
    allowed_donations = {SOURCE_URL, SOURCE_URL.replace('%E8%87%BA%E5%8C%97%E5%B8%82', '%E6%96%B0%E5%8C%97%E5%B8%82')}
    sources = json.loads((folder / 'full_acquisition.json').read_text())
    result = []
    for source in sources:
        if not source.get('complete_download'):
            continue
        url = source['source_url']
        if url != RESOURCE and url not in allowed_donations:
            raise ValueError('Unreviewed official source URL')
        path = (folder / source['file']).resolve()
        if not path.is_relative_to(folder.resolve()):
            raise ValueError('Source path must stay inside its private directory')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != source['sha256']:
            raise ValueError('Official original hash mismatch')
        if datetime.fromisoformat(source['retrieved_at']).tzinfo is None:
            raise ValueError('Official acquisition time must include timezone')
        accepted = excluded = total = 0

        def rows(reader, officers):
            nonlocal accepted, excluded, total
            required = REQUIRED if officers else {'收支科目', '身分證／統一編號', '捐贈者／支出對象', '擬參選人／政黨', '選舉名稱', '交易日期', '收入金額'}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError('Official snapshot columns changed')
            for line, row in enumerate(reader, 2):
                total += 1
                uniform = (row.get('統一編號' if officers else '身分證／統一編號') or '').strip()
                corporate = officers or row.get('收支科目') == '營利事業捐贈收入'
                if (not corporate or not re.fullmatch('[0-9]{8}', uniform)
                        or officers and not str(row.get('姓名') or '').strip()):
                    excluded += 1
                    continue
                accepted += 1
                if officers:
                    yield (source['sha256'], line, uniform, row['公司名稱'], row['姓名'],
                           row['職稱'], row['所代表法人'], row['持有股份數'])
                else:
                    yield (source['sha256'], line, uniform, row['捐贈者／支出對象'],
                           row['擬參選人／政黨'], row['選舉名稱'], row['交易日期'], row['收入金額'],
                           row.get('返還/繳庫'), row.get('更正註記'))

        with connection:
            connection.execute('insert or ignore into source_snapshots values(?,?,?,?)',
                               (source['sha256'], url, source['retrieved_at'],
                                'officers' if url == RESOURCE else 'corporate_contribution_observations'))
            if url == RESOURCE:
                with path.open(encoding='utf-8-sig', newline='') as stream:
                    connection.executemany('insert or ignore into officer_observations '
                        '(snapshot_sha256,source_row,company_id,company_name,person_name,position,representative,shares) values(?,?,?,?,?,?,?,?)',
                        rows(csv.DictReader(stream), True))
            else:
                with zipfile.ZipFile(path) as archive, archive.open('incomes.csv') as stream:
                    connection.executemany('insert or ignore into contribution_observations '
                        '(snapshot_sha256,source_row,donor_uniform,donor_name,candidate_name,election,date_raw,amount_raw,return_note,correction_note) values(?,?,?,?,?,?,?,?,?,?)',
                        rows(csv.DictReader(io.TextIOWrapper(stream, encoding='utf-8-sig')), False))
            if not total or total != source['source_rows'] or total != accepted + excluded:
                raise ValueError('Official snapshot row counts do not reconcile')
        result.append({'source_url':url, 'source_rows':total, 'indexed_observations':accepted,
                       'excluded_from_index_retained_in_original':excluded})
    if connection.execute('pragma integrity_check').fetchone()[0] != 'ok' or connection.execute('pragma foreign_key_check').fetchall():
        raise ValueError('Supplementary source index integrity failed')
    return {'sources':result, 'canonical_entities_published':0, 'cloud_writes':0}


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
    parser.add_argument("--supplementary-only", action="store_true")
    args = parser.parse_args()
    folder, output = args.snapshot_directory.resolve(), args.output.resolve()
    if (folder.is_relative_to(ROOT) or output.is_relative_to(ROOT) or
            folder.stat().st_mode & 0o077 or output.parent.stat().st_mode & 0o077):
        parser.error("Use private source/output directories outside the repository")
    os.umask(0o077)
    if args.supplementary_only:
        with sqlite3.connect(output) as connection:
            connection.execute('pragma foreign_keys=on')
            result = build_supplementary_sources(connection, folder)
        output.chmod(0o600)
        print(json.dumps({**result, 'database_bytes':output.stat().st_size}))
        return
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
