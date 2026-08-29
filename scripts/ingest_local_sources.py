#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ingest downloaded government datasets from data/raw into T.E.I.

This first version intentionally excludes PCC files and company_basic.jsonl.
It handles the downloaded director, anti-fraud/165, and penalty datasets,
creating normalized entities plus Evidence records in Supabase.

Examples:
  python3 scripts/ingest_local_sources.py --source directors --limit 1000
  python3 scripts/ingest_local_sources.py --source fraud --limit 1000
  python3 scripts/ingest_local_sources.py --source penalties --limit 1000
  python3 scripts/ingest_local_sources.py --source all

The Supabase secret key is requested at runtime and is sent only as the
`apikey` header. It is never written to disk.
"""
from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SUPABASE_URL = "https://ohvrrqbogxyjivcigbpl.supabase.co"
BATCH = 250
EXCLUDED_DIRS = {"pcc", "company"}
SUPPORTED = {".csv", ".json", ".jsonl"}


def norm(s: Any) -> str:
    return re.sub(r"\s+", "", str(s or "")).strip()


def hash_id(*parts: Any) -> str:
    raw = "|".join(norm(x) for x in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def classify(path: Path) -> str:
    text = str(path).lower()
    if any(k in text for k in ("董監事", "董事", "監察人", "directors")):
        return "directors"
    if any(k in text for k in ("165", "反詐", "詐騙", "假投資", "fraud")):
        return "fraud"
    if any(k in text for k in ("裁罰", "勞動法", "環境部", "金管會", "證券期貨", "公平會", "penalt")):
        return "penalties"
    return "unknown"


def list_files(root: Path, source: str) -> List[Path]:
    out: List[Path] = []
    for p in root.rglob("*"):
        if not p.is_file() or p.name.startswith("."):
            continue
        if any(part in EXCLUDED_DIRS for part in p.relative_to(root).parts):
            continue
        if p.suffix.lower() not in SUPPORTED:
            continue
        if classify(p) == source or source == "all":
            out.append(p)
    return sorted(out)


def read_csv_rows(path: Path) -> Iterable[Dict[str, str]]:
    encodings = ["utf-8-sig", "cp950", "big5", "utf-8"]
    last: Optional[Exception] = None
    for enc in encodings:
        try:
            with path.open("r", encoding=enc, newline="") as f:
                sample = f.read(8192)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
                except csv.Error:
                    dialect = csv.excel
                reader = csv.DictReader(f, dialect=dialect)
                for row in reader:
                    yield {str(k or "").strip(): str(v or "").strip() for k, v in row.items()}
            return
        except UnicodeDecodeError as exc:
            last = exc
    raise RuntimeError(f"無法解碼 CSV：{path} :: {last}")


def read_json_rows(path: Path) -> Iterable[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".jsonl":
        for line in text.splitlines():
            if line.strip():
                item = json.loads(line)
                if isinstance(item, dict):
                    yield item
        return
    data = json.loads(text)
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                yield item
    elif isinstance(data, dict):
        for key in ("data", "records", "result", "items"):
            value = data.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        yield item
                return
        yield data


def rows(path: Path) -> Iterable[Dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        return read_csv_rows(path)
    return read_json_rows(path)


def first(row: Dict[str, Any], names: List[str]) -> str:
    normalized = {norm(k): v for k, v in row.items()}
    for name in names:
        value = normalized.get(norm(name))
        if value not in (None, ""):
            return str(value).strip()
    return ""


def detect_uniform(row: Dict[str, Any]) -> str:
    return first(row, [
        "統一編號", "統編", "Business_Accounting_NO", "公司統編", "事業單位統一編號",
        "統一編號（統編）", "證券代號", "company_uniform_number"
    ])


def detect_name(row: Dict[str, Any]) -> str:
    return first(row, [
        "公司名稱", "公司名", "事業單位名稱", "廠商名稱", "機構名稱", "單位名稱",
        "名稱", "entity_name", "party_name", "公司"
    ])


def detect_person(row: Dict[str, Any]) -> str:
    return first(row, ["姓名", "負責人", "董事姓名", "人員姓名", "person_name", "name"])


def detect_title(row: Dict[str, Any]) -> str:
    return first(row, ["職稱", "職務", "職位", "position"])


def post_json(path: str, payload: List[Dict[str, Any]], key: str, on_conflict: Optional[str] = None) -> None:
    if not payload:
        return
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    if on_conflict:
        url += "?on_conflict=" + urllib.parse.quote(on_conflict, safe=",")
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("apikey", key)
    req.add_header("Authorization", "Bearer " + key)
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "resolution=merge-duplicates,return=minimal")
    with urllib.request.urlopen(req, timeout=120) as resp:
        if resp.status not in (200, 201, 204):
            raise RuntimeError(f"Supabase HTTP {resp.status}")


def ingest_directors(path: Path, key: str, limit: Optional[int]) -> Tuple[int, int]:
    people: List[Dict[str, Any]] = []
    companies: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    seen_people = set()
    processed = 0
    written = 0
    source_name = f"director:{path.name}"

    for row_no, row in enumerate(rows(path), 1):
        if limit and processed >= limit:
            break
        processed += 1
        uniform = detect_uniform(row)
        company = detect_name(row)
        person = detect_person(row)
        title = detect_title(row)
        if not person:
            continue
        person_id = hash_id(source_name, person)
        if person_id not in seen_people:
            seen_people.add(person_id)
            people.append({
                "name": person,
                "normalized_name": norm(person),
                "source_name": source_name,
                "source_record_id": person_id,
                "raw_data": row,
            })
        if uniform and company:
            companies.append({
                "uniform_number": uniform,
                "company_name": company,
                "source_name": source_name,
                "source_record_id": hash_id(source_name, uniform),
                "raw_data": {"company_name": company, "uniform_number": uniform},
            })
            relations.append({
                "source_entity_type": "company",
                "source_entity_id": uniform,
                "relationship_type": title or "DIRECTOR_RELATION",
                "target_entity_type": "person",
                "target_entity_id": person_id,
                "confidence": 1,
                "evidence_ids": [hash_id(source_name, row_no)],
                "observed_at": None,
                "source_name": source_name,
                "source_record_id": hash_id(source_name, row_no),
            })
        evidence.append({
            "evidence_id": hash_id(source_name, row_no),
            "source_type": "government_dataset",
            "source_name": source_name,
            "source_record_id": str(row_no),
            "entity_id": uniform or person_id,
            "entity_type": "company" if uniform else "person",
            "fact_type": "director_officer",
            "title": f"{company} / {person} / {title}".strip(" /"),
            "summary": json.dumps(row, ensure_ascii=False),
            "confidence": 1,
            "raw_payload_json": row,
        })
        if len(people) >= BATCH:
            post_json("people", people, key, "source_name,source_record_id")
            people.clear()
        if len(companies) >= BATCH:
            post_json("companies", companies, key, "uniform_number")
            companies.clear()
        if len(relations) >= BATCH:
            post_json("relationships", relations, key, None)
            relations.clear()
        if len(evidence) >= BATCH:
            post_json("evidence", evidence, key, "evidence_id")
            evidence.clear()
        written += 1

    post_json("people", people, key, "source_name,source_record_id")
    post_json("companies", companies, key, "uniform_number")
    post_json("relationships", relations, key, None)
    post_json("evidence", evidence, key, "evidence_id")
    return processed, written


def ingest_fraud(path: Path, key: str, limit: Optional[int]) -> Tuple[int, int]:
    records: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    source_name = f"fraud165:{path.name}"
    processed = 0
    written = 0
    for row_no, row in enumerate(rows(path), 1):
        if limit and processed >= limit:
            break
        processed += 1
        name = detect_name(row)
        uniform = detect_uniform(row)
        record_id = hash_id(source_name, row_no, json.dumps(row, ensure_ascii=False, sort_keys=True))
        records.append({
            "record_id": record_id,
            "dataset_id": "165",
            "record_type": "fraud_warning",
            "entity_name": name,
            "uniform_number": uniform,
            "domain": first(row, ["網址", "網域", "domain", "URL", "詐騙網址"]),
            "reported_date": None,
            "blocked_date": None,
            "source_url": first(row, ["來源網址", "source_url", "URL"]),
            "source_record_id": str(row_no),
            "raw_data": row,
        })
        evidence.append({
            "evidence_id": hash_id(source_name, row_no),
            "source_type": "government_dataset",
            "source_name": source_name,
            "source_record_id": str(row_no),
            "entity_id": uniform or name or record_id,
            "entity_type": "company" if uniform else "organization",
            "fact_type": "fraud_warning",
            "title": name or first(row, ["標題", "名稱", "網域"]),
            "summary": json.dumps(row, ensure_ascii=False),
            "confidence": 1,
            "raw_payload_json": row,
        })
        if len(records) >= BATCH:
            post_json("fraud_records", records, key, "record_id")
            records.clear()
        if len(evidence) >= BATCH:
            post_json("evidence", evidence, key, "evidence_id")
            evidence.clear()
        written += 1
    post_json("fraud_records", records, key, "record_id")
    post_json("evidence", evidence, key, "evidence_id")
    return processed, written


def ingest_penalties(path: Path, key: str, limit: Optional[int]) -> Tuple[int, int]:
    penalties: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    source_name = f"penalty:{path.name}"
    processed = 0
    written = 0
    for row_no, row in enumerate(rows(path), 1):
        if limit and processed >= limit:
            break
        processed += 1
        party = detect_name(row)
        uniform = detect_uniform(row)
        agency = first(row, ["機關", "主管機關", "裁處機關", "agency_name"])
        date = first(row, ["裁罰日期", "處分日期", "公告日期", "裁處日期", "date"])
        violation = first(row, ["違反法令", "違反法規", "違規事實", "違規內容", "違反事項", "violation"])
        basis = first(row, ["法規依據", "法令依據", "legal_basis"])
        fine = first(row, ["罰鍰", "罰鍰金額", "處罰金額", "fine_amount"])
        case_id = hash_id(source_name, row_no, json.dumps(row, ensure_ascii=False, sort_keys=True))
        penalties.append({
            "case_id": case_id,
            "agency_name": agency,
            "party_name": party,
            "uniform_number": uniform,
            "penalty_date": date or None,
            "legal_basis": basis,
            "violation": violation,
            "fine_amount": float(re.sub(r"[^0-9.-]", "", fine)) if re.sub(r"[^0-9.-]", "", fine) else None,
            "source_url": first(row, ["來源網址", "source_url", "URL"]),
            "source_record_id": str(row_no),
            "raw_data": row,
        })
        evidence.append({
            "evidence_id": hash_id(source_name, row_no),
            "source_type": "government_dataset",
            "source_name": source_name,
            "source_record_id": str(row_no),
            "entity_id": uniform or party or case_id,
            "entity_type": "company" if uniform else "organization",
            "fact_type": "penalty",
            "title": f"{agency} / {party}".strip(" /"),
            "summary": json.dumps(row, ensure_ascii=False),
            "confidence": 1,
            "raw_payload_json": row,
        })
        if len(penalties) >= BATCH:
            post_json("penalties", penalties, key, "case_id")
            penalties.clear()
        if len(evidence) >= BATCH:
            post_json("evidence", evidence, key, "evidence_id")
            evidence.clear()
        written += 1
    post_json("penalties", penalties, key, "case_id")
    post_json("evidence", evidence, key, "evidence_id")
    return processed, written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/raw")
    ap.add_argument("--source", choices=["directors", "fraud", "penalties", "all"], required=True)
    ap.add_argument("--limit", type=int, default=None, help="每個檔案最多處理幾筆；不給則全量")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"找不到資料夾：{root}")
        return 1
    key = getpass.getpass("請貼上 Supabase secret key（sb_secret_...）：").strip()
    if not key:
        print("沒有輸入 key")
        return 1
    sources = [args.source] if args.source != "all" else ["directors", "fraud", "penalties"]
    grand_p = grand_w = 0
    for source in sources:
        files = list_files(root, source)
        print(f"\n[{source}] 找到 {len(files)} 個檔案", flush=True)
        for path in files:
            print(f"  → {path.relative_to(root)}", flush=True)
            try:
                if source == "directors":
                    p, w = ingest_directors(path, key, args.limit)
                elif source == "fraud":
                    p, w = ingest_fraud(path, key, args.limit)
                else:
                    p, w = ingest_penalties(path, key, args.limit)
                print(f"    完成：讀取 {p:,}；寫入 {w:,}", flush=True)
                grand_p += p
                grand_w += w
            except Exception as exc:
                print(f"    ❌ {type(exc).__name__}: {exc}", flush=True)
    print("\n==============================")
    print(f"完成：讀取 {grand_p:,}；寫入 {grand_w:,}")
    print("==============================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
