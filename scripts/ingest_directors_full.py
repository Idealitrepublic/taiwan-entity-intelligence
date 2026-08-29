#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stream the downloaded director/officer CSV into Supabase safely.

This is deliberately separate from the generic multi-source importer because the
original full importer could send duplicate conflict keys in one PostgREST batch,
which PostgreSQL rejects with HTTP 500. This version deduplicates each batch and
prints progress so a long import never looks frozen.

Reads only local files under data/raw. The Supabase secret is requested at runtime
and sent only as the `apikey` header.
"""
from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SUPABASE_URL = "https://ohvrrqbogxyjivcigbpl.supabase.co"
ROOT_DEFAULT = Path("data/raw")
BATCH = 500
PROGRESS_EVERY = 5000
RETRIES = 4


def norm(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def hash_id(*parts: Any) -> str:
    return hashlib.sha256("|".join(norm(p) for p in parts).encode("utf-8")).hexdigest()


def first(row: Dict[str, str], names: List[str]) -> str:
    lookup = {norm(k): v for k, v in row.items()}
    for name in names:
        value = lookup.get(norm(name), "")
        if value:
            return str(value).strip()
    return ""


def director_files(root: Path) -> List[Path]:
    hits: List[Path] = []
    for p in sorted(root.rglob("*.csv")):
        if not p.is_file() or any(x in p.relative_to(root).parts for x in ("pcc",)):
            continue
        try:
            with p.open("r", encoding="utf-8-sig", newline="") as f:
                header = next(csv.reader([f.readline()]))
            cols = "|".join(norm(x) for x in header)
            if sum(k in cols for k in ("統一編號", "公司名稱", "職稱", "姓名")) >= 3:
                hits.append(p)
        except Exception:
            continue
    return hits


def rows(path: Path) -> Iterable[Tuple[int, Dict[str, str]]]:
    encodings = ("utf-8-sig", "cp950", "big5", "utf-8")
    last: Optional[Exception] = None
    for enc in encodings:
        try:
            with path.open("r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                for n, row in enumerate(reader, 2):
                    yield n, {str(k or "").strip(): str(v or "").strip() for k, v in row.items()}
            return
        except UnicodeDecodeError as exc:
            last = exc
    raise RuntimeError(f"無法解碼：{path} :: {last}")


def post_json(table: str, payload: List[Dict[str, Any]], key: str, conflict: Optional[str] = None) -> None:
    if not payload:
        return
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if conflict:
        url += "?on_conflict=" + urllib.parse.quote(conflict, safe=",")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(1, RETRIES + 1):
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "apikey": key,
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                resp.read()
            return
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code not in {408, 409, 429, 500, 502, 503, 504} or attempt == RETRIES:
                raise RuntimeError(f"Supabase {table} HTTP {exc.code}: {detail[:800]}") from exc
        except Exception as exc:
            if attempt == RETRIES:
                raise RuntimeError(f"Supabase {table}: {type(exc).__name__}: {exc}") from exc
        time.sleep(min(10, 2 ** (attempt - 1)))


def flush(
    people: Dict[str, Dict[str, Any]],
    companies: Dict[str, Dict[str, Any]],
    relationships: Dict[Tuple[str, str, str, str, str], Dict[str, Any]],
    evidence: Dict[str, Dict[str, Any]],
    key: str,
) -> Tuple[int, int, int, int]:
    post_json("people", list(people.values()), key, "source_name,source_record_id")
    post_json("companies", list(companies.values()), key, "uniform_number")
    post_json(
        "relationships",
        list(relationships.values()),
        key,
        "source_entity_type,source_entity_id,relationship_type,target_entity_type,target_entity_id",
    )
    post_json("evidence", list(evidence.values()), key, "evidence_id")
    counts = (len(people), len(companies), len(relationships), len(evidence))
    people.clear(); companies.clear(); relationships.clear(); evidence.clear()
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT_DEFAULT))
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    files = director_files(root)
    if not files:
        print(f"找不到董監事 CSV：{root}")
        return 1
    print(f"找到 {len(files)} 個董監事檔案：")
    for p in files:
        print(f"  → {p.relative_to(root)}", flush=True)

    key = getpass.getpass("Supabase secret key（sb_secret_...；輸入不會顯示）：").strip()
    if not key:
        print("沒有輸入 key")
        return 1

    people: Dict[str, Dict[str, Any]] = {}
    companies: Dict[str, Dict[str, Any]] = {}
    relationships: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
    evidence: Dict[str, Dict[str, Any]] = {}
    processed = 0
    written = 0
    batch_total = (0, 0, 0, 0)

    for path in files:
        print(f"\n開始：{path.relative_to(root)}", flush=True)
        for row_no, row in rows(path):
            processed += 1
            if args.limit and processed > args.limit:
                break

            uniform = first(row, ["統一編號", "統編", "公司統編"])
            company = first(row, ["公司名稱", "公司"])
            person = first(row, ["姓名", "董事姓名", "監察人姓名", "人員姓名"])
            title = first(row, ["職稱", "職務", "職位"])
            if not person:
                continue

            source_name = f"director:{path.name}"
            person_source_id = hash_id(source_name, row_no, person)
            people[person_source_id] = {
                "name": person,
                "normalized_name": norm(person),
                "source_name": source_name,
                "source_record_id": person_source_id,
                "raw_data": row,
            }

            if uniform and company:
                companies[uniform] = {
                    "uniform_number": uniform,
                    "company_name": company,
                    "source_name": source_name,
                    "source_record_id": hash_id(source_name, uniform),
                    "raw_data": {"uniform_number": uniform, "company_name": company},
                }
                target_type = "person"
                rel_key = ("company", uniform, title or "DIRECTOR_RELATION", target_type, person_source_id)
                eid = hash_id(source_name, row_no, "director")
                relationships[rel_key] = {
                    "source_entity_type": "company",
                    "source_entity_id": uniform,
                    "relationship_type": title or "DIRECTOR_RELATION",
                    "target_entity_type": target_type,
                    "target_entity_id": person_source_id,
                    "confidence": 1,
                    "evidence_ids": [eid],
                    "source_name": source_name,
                    "source_record_id": f"{source_name}#{row_no}",
                }
                evidence[eid] = {
                    "evidence_id": eid,
                    "source_type": "government_dataset",
                    "source_name": source_name,
                    "source_record_id": str(row_no),
                    "entity_id": uniform,
                    "entity_type": "company",
                    "fact_type": "director_officer",
                    "relation_type": title or "DIRECTOR_RELATION",
                    "target_entity_id": person_source_id,
                    "target_entity_type": target_type,
                    "title": f"{company} / {person} / {title}".strip(" /"),
                    "summary": json.dumps(row, ensure_ascii=False),
                    "confidence": 1,
                    "raw_payload_json": row,
                }

            if len(people) >= BATCH or len(companies) >= BATCH or len(relationships) >= BATCH or len(evidence) >= BATCH:
                c = flush(people, companies, relationships, evidence, key)
                batch_total = tuple(a + b for a, b in zip(batch_total, c))
                written += c[0]
                if processed % PROGRESS_EVERY < BATCH:
                    print(f"  進度：讀取 {processed:,} 列；已送出人物 {batch_total[0]:,} / 公司 {batch_total[1]:,} / 關係 {batch_total[2]:,} / Evidence {batch_total[3]:,}", flush=True)

        if args.limit and processed >= args.limit:
            break

    if people or companies or relationships or evidence:
        c = flush(people, companies, relationships, evidence, key)
        batch_total = tuple(a + b for a, b in zip(batch_total, c))

    print("\n==============================")
    print("✅ 董監事完整匯入完成")
    print(f"讀取資料列：{processed:,}")
    print(f"人物：{batch_total[0]:,}")
    print(f"公司：{batch_total[1]:,}")
    print(f"關係：{batch_total[2]:,}")
    print(f"Evidence：{batch_total[3]:,}")
    print("==============================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
