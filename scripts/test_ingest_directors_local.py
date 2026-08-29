#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke test: ingest the local director dataset into Supabase.

This intentionally reads the already-downloaded file from data/raw instead of
listing/downloading objects from Supabase Storage. Storage is the raw archive;
Postgres ingestion should consume the local raw files directly during the
initial load.
"""
from __future__ import annotations

import csv
import getpass
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SUPABASE_URL = "https://ohvrrqbogxyjivcigbpl.supabase.co"
ROOT = Path("data/raw")
LIMIT = 1000
BATCH = 100


def request_json(method: str, url: str, key: str, payload=None):
    data = None
    headers = {"apikey": key, "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=180) as r:
        body = r.read()
    if not body:
        return None
    return json.loads(body.decode("utf-8-sig"))


def post_rows(table, rows, key, conflict=None):
    if not rows:
        return
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if conflict:
        url += "?on_conflict=" + urllib.parse.quote(conflict, safe=",")
    for start in range(0, len(rows), BATCH):
        batch = rows[start:start + BATCH]
        req = urllib.request.Request(
            url,
            data=json.dumps(batch, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "apikey": key,
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal" if conflict else "resolution=ignore-duplicates,return=minimal",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                r.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase {table} HTTP {exc.code}: {body[:800]}") from exc


def norm(s: str) -> str:
    return re.sub(r"[\s　_\-()（）/]+", "", (s or "").strip().lower())


def getv(row, *names):
    mapping = {norm(k): v for k, v in row.items()}
    for n in names:
        value = mapping.get(norm(n), "")
        if value:
            return value.strip()
    return ""


def evidence_id(path: str, row_no: int) -> str:
    return hashlib.sha256(f"{path}|{row_no}|director".encode("utf-8")).hexdigest()


def open_csv(path: Path):
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            f = path.open("r", encoding=encoding, newline="")
            reader = csv.reader(f)
            header = next(reader)
            joined = "|".join(norm(x) for x in header)
            hits = sum(k in joined for k in ("統一編號", "公司名稱", "職稱", "姓名"))
            if hits >= 3:
                return f, header, reader
            f.close()
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    return None


def main() -> int:
    key = getpass.getpass("Supabase secret key（sb_secret_...；輸入不會顯示）：").strip()
    if not key:
        print("沒有輸入 key")
        return 1

    files = sorted(p for p in ROOT.rglob("*.csv") if p.is_file())
    if not files:
        print(f"找不到 CSV：{ROOT.resolve()}")
        return 1

    found = None
    for path in files:
        try:
            opened = open_csv(path)
        except Exception:
            continue
        if opened:
            found = (path, opened)
            break

    if not found:
        print("找不到符合『統一編號／公司名稱／職稱／姓名』欄位的董監事 CSV")
        return 2

    path, (f, header, reader) = found
    print(f"找到董監事資料：{path}")
    print(f"測試上限：{LIMIT} 筆")

    people = {}
    companies = {}
    relationships = []
    evidence = []
    seen_rel = set()
    rows_read = 0

    try:
        for row_no, row in enumerate(reader, 2):
            if rows_read >= LIMIT:
                break
            d = {header[i].strip(): (row[i].strip() if i < len(row) else "") for i in range(len(header))}
            uniform = getv(d, "統一編號", "統編")
            company = getv(d, "公司名稱", "公司")
            name = getv(d, "姓名", "董事姓名", "監察人姓名")
            position = getv(d, "職稱")
            if not name or not company:
                continue

            people.setdefault(name, {
                "name": name,
                "normalized_name": re.sub(r"\s+", "", name).upper(),
                "source_name": "董監事資料集",
                "source_record_id": f"{path}#{row_no}",
                "raw_data": d,
            })
            if uniform:
                companies.setdefault(uniform, {
                    "uniform_number": uniform,
                    "company_name": company,
                    "source_name": "董監事資料集",
                    "source_record_id": f"{path}#{row_no}",
                    "raw_data": d,
                })

            rel_key = (uniform or company, name, position)
            if rel_key not in seen_rel:
                seen_rel.add(rel_key)
                eid = evidence_id(str(path), row_no)
                relationships.append({
                    "source_entity_type": "company",
                    "source_entity_id": uniform or company,
                    "relationship_type": position or "董監事",
                    "target_entity_type": "person",
                    "target_entity_id": name,
                    "confidence": 1.0,
                    "evidence_ids": [eid],
                    "source_name": "董監事資料集",
                    "source_record_id": f"{path}#{row_no}",
                })
                evidence.append({
                    "evidence_id": eid,
                    "source_type": "government_open_data",
                    "source_name": "董監事資料集",
                    "source_record_id": f"{path}#{row_no}",
                    "entity_id": uniform or company,
                    "entity_type": "company",
                    "fact_type": "director_relation",
                    "relation_type": position or "董監事",
                    "target_entity_id": name,
                    "target_entity_type": "person",
                    "title": f"{company}/{position}/{name}",
                    "summary": f"公開董監事資料顯示 {name} 與 {company} 存在 {position or '董監事'} 關係。",
                    "confidence": 1.0,
                    "raw_payload_json": d,
                })
            rows_read += 1
    finally:
        f.close()

    print(f"讀取資料列：{rows_read}")
    print(f"人物：{len(people)} / 公司：{len(companies)} / 關係：{len(relationships)} / Evidence：{len(evidence)}")

    post_rows("people", list(people.values()), key)
    post_rows("companies", list(companies.values()), key, "uniform_number")
    post_rows("relationships", relationships, key)
    post_rows("evidence", evidence, key)

    print("\n✅ 董監事 1000 筆測試匯入成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
