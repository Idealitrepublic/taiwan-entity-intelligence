#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lean ingestion for T.E.I. v2.

Streams local CSV/JSON files in bounded batches so large government datasets do
not sit in memory and appear to hang. PostgreSQL stores only normalized fields;
raw originals remain in Supabase Storage.
"""
from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SUPABASE_URL = "https://anntdcxttvffekslbrkj.supabase.co"
ROOT = Path("data/raw")
BATCH = 250
PROGRESS_EVERY = 5000


def norm(v):
    return re.sub(r"[\s　]+", "", str(v or "")).strip()


def rid(*parts):
    return hashlib.sha256("|".join(norm(x) for x in parts).encode("utf-8")).hexdigest()


def headers(key):
    h = {"apikey": key, "Content-Type": "application/json", "Accept": "application/json"}
    if key.startswith("eyJ"):
        h["Authorization"] = "Bearer " + key
    return h


def post(table, rows, key, conflict=None):
    if not rows:
        return
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if conflict:
        url += "?on_conflict=" + urllib.parse.quote(conflict, safe=",")
    for i in range(0, len(rows), BATCH):
        payload = rows[i:i+BATCH]
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={**headers(key), "Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                r.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"Supabase {table} HTTP {exc.code}: {body}") from exc


def first(row, names):
    m = {norm(k).lower(): v for k, v in row.items()}
    for n in names:
        v = m.get(norm(n).lower())
        if v not in (None, ""):
            return str(v).strip()
    return ""


def stream_rows(path):
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        with path.open("r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        yield item
        return

    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, list):
            yield from (x for x in data if isinstance(x, dict))
            return
        if isinstance(data, dict):
            for key in ("data", "records", "items", "result"):
                value = data.get(key)
                if isinstance(value, list):
                    yield from (x for x in value if isinstance(x, dict))
                    return
            yield data
        return

    encodings = ("utf-8-sig", "cp950", "big5", "utf-8")
    for enc in encodings:
        try:
            f = path.open("r", encoding=enc, newline="")
            sample = f.read(8192)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            for row in reader:
                yield {str(k or "").strip(): str(v or "").strip() for k, v in row.items()}
            f.close()
            return
        except UnicodeDecodeError:
            try:
                f.close()
            except Exception:
                pass
            continue
    raise RuntimeError(f"無法讀取：{path}")


def classify(path):
    s = str(path).lower()
    if any(k in s for k in ("董監事", "董事", "監察人", "director")):
        return "directors"
    if any(k in s for k in ("165", "反詐", "詐騙", "假投資", "twnic")):
        return "fraud"
    if any(k in s for k in ("裁罰", "勞動法", "環境部", "金管會", "證券期貨", "penalt")):
        return "penalties"
    return "unknown"


def files_for(root, source):
    out = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in (".csv", ".json", ".jsonl"):
            continue
        rel_parts = p.relative_to(root).parts
        if "company" in rel_parts or "pcc" in rel_parts:
            continue
        if classify(p) == source:
            out.append(p)
    return sorted(out)


def flush_all(people, companies, rels, key):
    post("people", list(people.values()), key, "source_name,source_record_id")
    post("companies", list(companies.values()), key, "uniform_number")
    post("relationships", list(rels.values()), key, None)
    people.clear(); companies.clear(); rels.clear()


def ingest_directors(paths, key):
    total = 0; people = {}; companies = {}; rels = {}
    for path in paths:
        print(f"  → 董監事：{path.relative_to(ROOT)}", flush=True)
        source = "director:" + path.name
        for idx, row in enumerate(stream_rows(path), 1):
            total += 1
            uniform = first(row, ["統一編號", "統編", "公司統編"])
            company = first(row, ["公司名稱", "公司名", "公司"])
            person = first(row, ["姓名", "董事姓名", "監察人姓名"])
            title = first(row, ["職稱", "職務", "職位"])
            if not person:
                continue
            pid = rid("person", person)
            people[pid] = {"name": person, "normalized_name": norm(person), "source_name": "董監事資料集", "source_record_id": pid}
            if uniform and company:
                companies[uniform] = {"uniform_number": uniform, "company_name": company, "source_name": "董監事資料集", "source_record_id": rid("company", uniform)}
                keyrel = (uniform, pid, title or "董監事")
                rels[keyrel] = {"source_entity_type": "company", "source_entity_id": uniform, "relationship_type": title or "董監事", "target_entity_type": "person", "target_entity_id": pid, "confidence": 1, "evidence_ids": [], "source_name": source, "source_record_id": str(idx)}
            if total % PROGRESS_EVERY == 0:
                flush_all(people, companies, rels, key)
                print(f"    進度：已讀取 {total:,} 列", flush=True)
        flush_all(people, companies, rels, key)
    return total


def ingest_fraud(paths, key):
    total = 0; out = {}
    for path in paths:
        print(f"  → 165：{path.relative_to(ROOT)}", flush=True)
        source = "fraud165:" + path.name
        for idx, row in enumerate(stream_rows(path), 1):
            total += 1
            domain = first(row, ["網址", "網域", "詐騙網址", "domain", "URL"])
            name = first(row, ["公司名稱", "公司名", "名稱", "entity_name"])
            uniform = first(row, ["統一編號", "統編", "公司統編"])
            if domain or name or uniform:
                x = rid(source, idx, domain, name, uniform)
                out[x] = {"record_id": x, "dataset_id": "165", "record_type": "fraud_warning", "entity_name": name, "uniform_number": uniform, "domain": domain, "source_url": first(row, ["來源網址", "source_url"]), "source_record_id": str(idx)}
            if len(out) >= BATCH:
                post("fraud_records", list(out.values()), key, "record_id"); out.clear()
            if total % PROGRESS_EVERY == 0:
                print(f"    進度：已讀取 {total:,} 列", flush=True)
        post("fraud_records", list(out.values()), key, "record_id"); out.clear()
    return total


def ingest_penalties(paths, key):
    total = 0; out = {}
    for path in paths:
        print(f"  → 裁罰：{path.relative_to(ROOT)}", flush=True)
        source = "penalty:" + path.name
        for idx, row in enumerate(stream_rows(path), 1):
            total += 1
            party = first(row, ["公司名稱", "事業單位名稱", "廠商名稱", "機構名稱", "名稱"])
            uniform = first(row, ["統一編號", "統編", "公司統編", "證券代號"])
            agency = first(row, ["機關", "主管機關", "裁處機關"])
            date = first(row, ["裁罰日期", "處分日期", "公告日期", "裁處日期"])
            violation = first(row, ["違反法令", "違反法規", "違規事實", "違規內容", "違反事項"])
            basis = first(row, ["法規依據", "法令依據"])
            fine = first(row, ["罰鍰", "罰鍰金額", "處罰金額"])
            n = re.sub(r"[^0-9.-]", "", fine)
            x = rid(source, idx, party, uniform, violation)
            out[x] = {"case_id": x, "agency_name": agency, "party_name": party, "uniform_number": uniform, "penalty_date": date or None, "legal_basis": basis, "violation": violation, "fine_amount": float(n) if n else None, "source_url": first(row, ["來源網址", "source_url", "URL"]), "source_record_id": str(idx)}
            if len(out) >= BATCH:
                post("penalties", list(out.values()), key, "case_id"); out.clear()
            if total % PROGRESS_EVERY == 0:
                print(f"    進度：已讀取 {total:,} 列", flush=True)
        post("penalties", list(out.values()), key, "case_id"); out.clear()
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["directors", "fraud", "penalties", "all"], required=True)
    args = ap.parse_args()
    root = ROOT.resolve()
    key = getpass.getpass("T.E.I. v2 Supabase key：").strip()
    if not key:
        raise SystemExit("沒有輸入 key")
    sources = [args.source] if args.source != "all" else ["directors", "fraud", "penalties"]
    grand = 0
    for source in sources:
        fs = files_for(root, source)
        print(f"\n[{source}] 找到 {len(fs)} 個檔案", flush=True)
        if not fs:
            continue
        try:
            if source == "directors":
                n = ingest_directors(fs, key)
            elif source == "fraud":
                n = ingest_fraud(fs, key)
            else:
                n = ingest_penalties(fs, key)
            print(f"  ✅ 完成：讀取 {n:,} 列", flush=True)
            grand += n
        except Exception as exc:
            print(f"  ❌ {type(exc).__name__}: {exc}", flush=True)
    print(f"\n完成：共讀取 {grand:,} 列", flush=True)


if __name__ == "__main__":
    main()
