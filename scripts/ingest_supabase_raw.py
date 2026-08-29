#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ingest raw files already stored in Supabase Storage into T.E.I. tables.

This script is intentionally run locally so the Supabase secret key never enters
GitHub. It reads objects under raw-data/raw/, identifies common Taiwan government
CSV/JSON datasets by their headers/content, and writes normalized records to
Postgres through the Supabase REST API.

Supported first-pass sources:
- 董監事資料集 -> people / companies / relationships / evidence
- 165反詐資料 -> fraud_records / evidence
- 政府裁罰資料 -> penalties / evidence
- JSON domain/165 feeds -> fraud_records / evidence

Unknown files are reported and skipped rather than guessed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

SUPABASE_URL = "https://ohvrrqbogxyjivcigbpl.supabase.co"
BUCKET = "raw-data"
RAW_PREFIX = "raw/"
PAGE_SIZE = 1000
BATCH_SIZE = 100
TIMEOUT = 180


def http_json(method: str, url: str, key: str, payload: Any = None) -> Any:
    body = None
    headers = {
        "apikey": key,
        "Accept": "application/json",
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = resp.read()
    if not data:
        return None
    return json.loads(data.decode("utf-8-sig"))


def http_bytes(url: str, key: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"apikey": key, "Accept": "*/*"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def safe_get_json(url: str, key: str) -> Any:
    for attempt in range(1, 4):
        try:
            return http_json("GET", url, key)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(attempt)


def list_objects(key: str) -> List[Dict[str, Any]]:
    objects: List[Dict[str, Any]] = []
    offset = 0
    endpoint = f"{SUPABASE_URL}/storage/v1/object/list/{BUCKET}"
    while True:
        rows = http_json(
            "POST",
            endpoint,
            key,
            {"prefix": RAW_PREFIX, "limit": PAGE_SIZE, "offset": offset, "sortBy": {"column": "name", "order": "asc"}},
        )
        if not isinstance(rows, list) or not rows:
            break
        objects.extend([r for r in rows if isinstance(r, dict) and r.get("name")])
        if len(rows) < PAGE_SIZE:
            break
        offset += len(rows)
    return objects


def decode_text(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp950", "big5", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def normalize_col(x: str) -> str:
    return re.sub(r"[\s　_\-()（）/]+", "", (x or "").strip().lower())


def classify_text(path: str, text: str) -> str:
    sample = text[:200_000]
    head = sample.splitlines()[0] if sample.splitlines() else ""
    cols = [normalize_col(x) for x in next(csv.reader([head]), [])]
    joined = "|".join(cols)
    all_text = (head + "\n" + sample[:20_000]).lower()

    # Known director dataset columns from the user's existing data.
    director_hits = sum(k in joined for k in ("統一編號", "公司名稱", "職稱", "姓名", "所代表法人", "持有股份數"))
    if director_hits >= 4:
        return "directors"

    fraud_hits = sum(k in joined for k in ("網址", "網域", "網站", "詐騙", "涉詐", "165"))
    if fraud_hits >= 2 or any(k in all_text for k in ("涉詐網站", "詐騙網站", "假投資", "165反詐")):
        return "fraud165"

    penalty_hits = sum(k in joined for k in ("裁罰", "裁處", "違反法令", "違規", "罰鍰", "處分", "法規"))
    if penalty_hits >= 2 or any(k in all_text for k in ("裁罰", "裁處", "罰鍰", "違反勞動法令", "裁罰處分")):
        return "penalty"

    if path.lower().endswith(".json"):
        try:
            obj = json.loads(sample)
            blob = json.dumps(obj, ensure_ascii=False).lower()
            if any(k in blob for k in ("詐騙", "涉詐", "假投資", "網域", "domain")):
                return "fraud165"
        except Exception:
            pass

    return "unknown"


def parse_csv_rows(raw: bytes) -> Tuple[List[str], Iterable[List[str]]]:
    text = decode_text(raw)
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return [], []
    return header, reader


def row_dict(header: List[str], row: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for i, key in enumerate(header):
        k = key.strip() if key else ""
        out[k] = row[i].strip() if i < len(row) and row[i] is not None else ""
    return out


def getv(row: Dict[str, str], *names: str) -> str:
    norm = {normalize_col(k): v for k, v in row.items()}
    for name in names:
        if normalize_col(name) in norm and norm[normalize_col(name)]:
            return norm[normalize_col(name)]
    return ""


def postgrest_insert(table: str, rows: List[Dict[str, Any]], key: str) -> int:
    if not rows:
        return 0
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    total = 0
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start+BATCH_SIZE]
        last_err = None
        for attempt in range(1, 4):
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(batch, ensure_ascii=False).encode("utf-8"),
                    method="POST",
                    headers={
                        "apikey": key,
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "Prefer": "resolution=ignore-duplicates,return=minimal",
                    },
                )
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    resp.read()
                total += len(batch)
                break
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                last_err = f"HTTP {exc.code}: {body[:500]}"
                if exc.code not in {408, 409, 429, 500, 502, 503, 504}:
                    raise RuntimeError(f"PostgREST {table}: {last_err}")
                time.sleep(attempt)
        else:
            raise RuntimeError(f"PostgREST {table}: {last_err}")
    return total


def make_evidence_id(source_path: str, row_no: int, fact_type: str) -> str:
    raw = f"{source_path}|{row_no}|{fact_type}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def ingest_directors(text: str, source_path: str, key: str, limit: int) -> Tuple[int, int, int, int]:
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return 0, 0, 0, 0

    people: Dict[str, Dict[str, Any]] = {}
    companies: Dict[str, Dict[str, Any]] = {}
    relationships: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    seen_rel = set()
    count = 0

    for row_no, row in enumerate(reader, 2):
        if count >= limit:
            break
        d = row_dict(header, row)
        uniform = getv(d, "統一編號", "統編")
        company = getv(d, "公司名稱", "公司")
        name = getv(d, "姓名", "董事姓名", "監察人姓名")
        position = getv(d, "職稱")
        representative = getv(d, "所代表法人")
        shares = getv(d, "持有股份數", "持股數")
        if not name or not company:
            continue
        person_key = name.strip()
        people[person_key] = {
            "name": name,
            "normalized_name": re.sub(r"\s+", "", name).upper(),
            "source_name": "董監事資料集",
            "source_record_id": f"{source_path}#{row_no}",
            "raw_data": d,
        }
        if uniform:
            companies[uniform] = {
                "uniform_number": uniform,
                "company_name": company,
                "representative_name": None,
                "source_name": "董監事資料集",
                "source_record_id": f"{source_path}#{row_no}",
                "raw_data": {k: v for k, v in d.items()},
            }
        rel_key = (uniform or company, name, position)
        if rel_key not in seen_rel:
            seen_rel.add(rel_key)
            relationships.append({
                "source_entity_type": "company",
                "source_entity_id": uniform or company,
                "relationship_type": position or "董監事",
                "target_entity_type": "person",
                "target_entity_id": name,
                "confidence": 1.0,
                "evidence_ids": [make_evidence_id(source_path, row_no, "director")],
                "observed_at": None,
                "source_name": "董監事資料集",
                "source_record_id": f"{source_path}#{row_no}",
            })
        evidence.append({
            "evidence_id": make_evidence_id(source_path, row_no, "director"),
            "source_type": "government_open_data",
            "source_name": "董監事資料集",
            "source_record_id": f"{source_path}#{row_no}",
            "source_url": None,
            "entity_id": uniform or company,
            "entity_type": "company",
            "fact_type": "director_relation",
            "relation_type": position or "董監事",
            "target_entity_id": name,
            "target_entity_type": "person",
            "title": f"{company}／{position}／{name}",
            "summary": f"公開董監事資料顯示 {name} 與 {company} 存在 {position or '董監事'} 關係。",
            "confidence": 1.0,
            "raw_payload_json": d,
        })
        count += 1

    people_count = postgrest_insert("people", list(people.values()), key)
    company_count = 0
    if companies:
        # upsert on uniform_number
        url = f"{SUPABASE_URL}/rest/v1/companies?on_conflict=uniform_number"
        req = urllib.request.Request(
            url,
            data=json.dumps(list(companies.values()), ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            resp.read()
        company_count = len(companies)
    rel_count = postgrest_insert("relationships", relationships, key)
    ev_count = postgrest_insert("evidence", evidence, key)
    return count, company_count, rel_count, ev_count


def ingest_generic_source(kind: str, text: str, source_path: str, key: str, limit: int) -> Tuple[int, int, int]:
    if source_path.lower().endswith(".json"):
        try:
            data = json.loads(text)
        except Exception:
            return 0, 0, 0
        if isinstance(data, dict):
            rows = data.get("data") or data.get("records") or data.get("items") or [data]
        elif isinstance(data, list):
            rows = data
        else:
            rows = []
        normalized_rows = [r for r in rows if isinstance(r, dict)][:limit]
    else:
        header, reader = parse_csv_rows(text.encode("utf-8"))
        normalized_rows = [row_dict(header, r) for _, r in zip(range(limit), reader)]

    records: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    table = "fraud_records" if kind == "fraud165" else "penalties"

    for idx, d in enumerate(normalized_rows, 1):
        blob = " ".join(str(v) for v in d.values())
        digest = make_evidence_id(source_path, idx, kind)
        if kind == "fraud165":
            records.append({
                "record_id": digest,
                "dataset_id": source_path,
                "record_type": "165",
                "entity_name": getv(d, "公司名稱", "名稱", "網站名稱", "網域名稱", "名稱/網址"),
                "uniform_number": getv(d, "統一編號", "統編"),
                "domain": getv(d, "網域", "網址", "網站", "URL", "網域名稱"),
                "reported_date": None,
                "blocked_date": None,
                "source_url": getv(d, "網址", "URL", "來源網址"),
                "source_record_id": f"{source_path}#{idx}",
                "raw_data": d,
            })
            title = "165 反詐資料"
            summary = blob[:1000]
        else:
            records.append({
                "case_id": digest,
                "agency_name": getv(d, "機關", "主管機關", "裁罰機關", "處分機關"),
                "party_name": getv(d, "受裁罰對象", "公司名稱", "事業單位名稱", "名稱", "相對人"),
                "uniform_number": getv(d, "統一編號", "統編"),
                "penalty_date": None,
                "legal_basis": getv(d, "違反法規", "法規", "法令依據", "法規依據"),
                "violation": getv(d, "違規情形", "違反法令", "違規事實", "違反法規條文"),
                "fine_amount": None,
                "source_url": getv(d, "網址", "URL", "來源網址", "案件網址"),
                "source_record_id": f"{source_path}#{idx}",
                "raw_data": d,
            })
            title = "政府裁罰資料"
            summary = blob[:1000]
        evidence.append({
            "evidence_id": digest,
            "source_type": "government_open_data",
            "source_name": "165" if kind == "fraud165" else "政府裁罰",
            "source_record_id": f"{source_path}#{idx}",
            "entity_id": getv(d, "統一編號", "統編") or getv(d, "公司名稱", "名稱", "事業單位名稱"),
            "entity_type": "company",
            "fact_type": kind,
            "relation_type": None,
            "target_entity_id": None,
            "target_entity_type": None,
            "title": title,
            "summary": summary,
            "confidence": 1.0,
            "raw_payload_json": d,
        })

    inserted = postgrest_insert(table, records, key)
    ev_inserted = postgrest_insert("evidence", evidence, key)
    return len(normalized_rows), inserted, ev_inserted


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["all", "directors", "fraud165", "penalty"], default="all")
    ap.add_argument("--limit", type=int, default=10000, help="每個檔案最多處理幾筆；all 時只影響單檔")
    ap.add_argument("--max-files", type=int, default=0, help="最多處理幾個原始檔；0=全部")
    args = ap.parse_args()

    key = __import__("getpass").getpass("請貼上 Supabase secret key（sb_secret_...）：").strip()
    if not key:
        print("沒有輸入 key")
        return 1

    objects = list_objects(key)
    print(f"找到 raw/ 原始物件：{len(objects)}")
    if args.max_files:
        objects = objects[:args.max_files]

    stats = defaultdict(int)
    for i, obj in enumerate(objects, 1):
        name = obj["name"]
        url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{urllib.parse.quote(name, safe='/')}"
        try:
            raw = http_bytes(url, key)
            text = decode_text(raw)
            kind = classify_text(name, text)
            stats[f"files_{kind}"] += 1
            print(f"[{i}/{len(objects)}] {name} -> {kind} ({len(raw):,} bytes)", flush=True)
            if args.source != "all" and kind != args.source:
                continue
            if kind == "directors":
                c, co, r, e = ingest_directors(text, name, key, args.limit)
                stats["rows"] += c
                stats["companies"] += co
                stats["relationships"] += r
                stats["evidence"] += e
            elif kind in {"fraud165", "penalty"}:
                c, ins, e = ingest_generic_source(kind, text, name, key, args.limit)
                stats["rows"] += c
                stats["inserted"] += ins
                stats["evidence"] += e
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(f"  ✗ HTTP {exc.code}: {body[:400]}")
            stats["errors"] += 1
        except Exception as exc:
            print(f"  ✗ {type(exc).__name__}: {exc}")
            stats["errors"] += 1

    print("\n====================")
    print("匯入完成")
    for k, v in sorted(stats.items()):
        print(f"{k}: {v}")
    print("====================")
    return 0 if stats["errors"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
