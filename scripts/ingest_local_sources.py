#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ingest downloaded government datasets from data/raw into T.E.I.

Sources:
- 董監事資料 -> people / companies / relationships / evidence
- 165 / 反詐 -> fraud_records / evidence
- 裁罰 -> penalties / evidence

The script reads the local raw files directly. It does not touch PCC files or
company_basic.jsonl. Modern Supabase sb_secret_* keys are sent only via the
apikey header; no Authorization: Bearer header is used.
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
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

SUPABASE_URL = "https://ohvrrqbogxyjivcigbpl.supabase.co"
ROOT_DEFAULT = Path("data/raw")
BATCH = 100
EXCLUDED_DIRS = {"pcc", "company"}
SUPPORTED = {".csv", ".json", ".jsonl"}


def norm(value: Any) -> str:
    return re.sub(r"[\s　]+", "", str(value or "")).strip()


def hash_id(*parts: Any) -> str:
    return hashlib.sha256("|".join(norm(p) for p in parts).encode("utf-8")).hexdigest()


def classify(path: Path) -> str:
    s = str(path).lower()
    if any(k in s for k in ("董監事", "董事", "監察人", "directors")):
        return "directors"
    if any(k in s for k in ("165", "反詐", "詐騙", "假投資", "fraud")):
        return "fraud"
    if any(k in s for k in ("裁罰", "勞動法", "環境部", "金管會", "證券期貨", "公平會", "penalt")):
        return "penalties"
    return "unknown"


def list_files(root: Path, source: str) -> List[Path]:
    files: List[Path] = []
    for p in root.rglob("*"):
        if not p.is_file() or p.name.startswith("."):
            continue
        parts = p.relative_to(root).parts
        if any(part in EXCLUDED_DIRS for part in parts):
            continue
        if p.suffix.lower() not in SUPPORTED:
            continue
        if classify(p) == source:
            files.append(p)
    return sorted(files)


def read_rows(path: Path) -> Iterator[Dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        encodings = ("utf-8-sig", "cp950", "big5", "utf-8")
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
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".jsonl":
        for line in text.splitlines():
            if line.strip():
                obj = json.loads(line)
                if isinstance(obj, dict):
                    yield obj
        return
    data = json.loads(text)
    if isinstance(data, list):
        for obj in data:
            if isinstance(obj, dict):
                yield obj
        return
    if isinstance(data, dict):
        for key in ("data", "records", "result", "items"):
            value = data.get(key)
            if isinstance(value, list):
                for obj in value:
                    if isinstance(obj, dict):
                        yield obj
                return
        yield data


def first(row: Dict[str, Any], names: Iterable[str]) -> str:
    mapping = {norm(k): v for k, v in row.items()}
    for name in names:
        value = mapping.get(norm(name))
        if value not in (None, ""):
            return str(value).strip()
    return ""


def uniform(row: Dict[str, Any]) -> str:
    return first(row, ("統一編號", "統編", "Business_Accounting_NO", "公司統編", "事業單位統一編號", "company_uniform_number"))


def entity_name(row: Dict[str, Any]) -> str:
    return first(row, ("公司名稱", "公司名", "事業單位名稱", "廠商名稱", "機構名稱", "單位名稱", "名稱", "entity_name", "party_name", "公司"))


def person_name(row: Dict[str, Any]) -> str:
    return first(row, ("姓名", "董事姓名", "監察人姓名", "人員姓名", "person_name", "負責人"))


def title(row: Dict[str, Any]) -> str:
    return first(row, ("職稱", "職務", "職位", "position"))


def api_request(method: str, path: str, key: str, payload: Any = None, query: str = "") -> bytes:
    url = f"{SUPABASE_URL}{path}"
    if query:
        url += ("&" if "?" in url else "?") + query
    data = None
    headers = {"apikey": key, "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def post_rows(table: str, rows: List[Dict[str, Any]], key: str, conflict: Optional[str] = None) -> int:
    if not rows:
        return 0
    query = f"on_conflict={urllib.parse.quote(conflict, safe=',')}" if conflict else ""
    written = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i+BATCH]
        try:
            api_request("POST", f"/rest/v1/{table}", key, batch, query)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase {table} HTTP {exc.code}: {body[:800]}") from exc
        written += len(batch)
    return written


def flush_directors(people: Dict[str, Dict[str, Any]], companies: Dict[str, Dict[str, Any]], rels: List[Dict[str, Any]], evs: List[Dict[str, Any]], key: str) -> None:
    # Deduplicate company upserts inside each request. A Postgres upsert cannot
    # update the same unique row twice in one INSERT statement.
    post_rows("people", list(people.values()), key, "source_name,source_record_id")
    post_rows("companies", list(companies.values()), key, "uniform_number")
    post_rows("relationships", rels, key, None)
    post_rows("evidence", evs, key, "evidence_id")


def ingest_directors(path: Path, key: str, limit: Optional[int]) -> Tuple[int, int, int, int]:
    people: Dict[str, Dict[str, Any]] = {}
    companies: Dict[str, Dict[str, Any]] = {}
    rels: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    evs: Dict[str, Dict[str, Any]] = {}
    processed = 0
    source_name = f"director:{path.name}"

    for row_no, row in enumerate(read_rows(path), 1):
        if limit is not None and processed >= limit:
            break
        processed += 1
        person = person_name(row)
        company = entity_name(row)
        u = uniform(row)
        t = title(row)
        if not person or not company:
            continue
        person_id = hash_id(source_name, person)
        evidence_id = hash_id(source_name, row_no, "director")
        people[person_id] = {
            "name": person,
            "normalized_name": norm(person),
            "source_name": source_name,
            "source_record_id": person_id,
            "raw_data": row,
        }
        if u:
            companies[u] = {
                "uniform_number": u,
                "company_name": company,
                "source_name": source_name,
                "source_record_id": hash_id(source_name, u),
                "raw_data": {"company_name": company, "uniform_number": u},
            }
        if u:
            rel_key = (u, person_id, t or "DIRECTOR_RELATION")
            rels[rel_key] = {
                "source_entity_type": "company",
                "source_entity_id": u,
                "relationship_type": t or "DIRECTOR_RELATION",
                "target_entity_type": "person",
                "target_entity_id": person_id,
                "confidence": 1,
                "evidence_ids": [evidence_id],
                "source_name": source_name,
                "source_record_id": hash_id(source_name, row_no),
            }
        evs[evidence_id] = {
            "evidence_id": evidence_id,
            "source_type": "government_dataset",
            "source_name": source_name,
            "source_record_id": str(row_no),
            "entity_id": u or person_id,
            "entity_type": "company" if u else "person",
            "fact_type": "director_officer",
            "relation_type": t or "DIRECTOR_RELATION",
            "target_entity_id": person_id,
            "target_entity_type": "person",
            "title": f"{company} / {t or '董監事'} / {person}",
            "summary": json.dumps(row, ensure_ascii=False),
            "confidence": 1,
            "raw_payload_json": row,
        }
        if len(people) >= BATCH or len(companies) >= BATCH or len(rels) >= BATCH or len(evs) >= BATCH:
            flush_directors(people, companies, list(rels.values()), list(evs.values()), key)
            people.clear(); companies.clear(); rels.clear(); evs.clear()

    flush_directors(people, companies, list(rels.values()), list(evs.values()), key)
    # Return logical row count plus current generated counts for visibility.
    return processed, len(people), len(rels), len(evs)


def parse_fine(value: str) -> Optional[float]:
    cleaned = re.sub(r"[^0-9.\-]", "", value or "")
    if cleaned in ("", "-", "."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def ingest_fraud(path: Path, key: str, limit: Optional[int]) -> Tuple[int, int]:
    records: List[Dict[str, Any]] = []
    evs: List[Dict[str, Any]] = []
    source_name = f"fraud165:{path.name}"
    processed = 0
    for row_no, row in enumerate(read_rows(path), 1):
        if limit is not None and processed >= limit:
            break
        processed += 1
        rid = hash_id(source_name, row_no, json.dumps(row, ensure_ascii=False, sort_keys=True))
        u = uniform(row)
        name = entity_name(row)
        domain = first(row, ("網址", "網域", "網域名稱", "URL", "詐騙網址"))
        records.append({
            "record_id": rid,
            "dataset_id": "165",
            "record_type": "fraud_warning",
            "entity_name": name,
            "uniform_number": u,
            "domain": domain,
            "reported_date": None,
            "blocked_date": None,
            "source_url": first(row, ("來源網址", "source_url")),
            "source_record_id": str(row_no),
            "raw_data": row,
        })
        evs.append({
            "evidence_id": hash_id(source_name, row_no),
            "source_type": "government_dataset",
            "source_name": source_name,
            "source_record_id": str(row_no),
            "entity_id": u or name or rid,
            "entity_type": "company" if u else "organization",
            "fact_type": "fraud_warning",
            "title": name or domain or "165 反詐資料",
            "summary": json.dumps(row, ensure_ascii=False),
            "confidence": 1,
            "raw_payload_json": row,
        })
        if len(records) >= BATCH:
            post_rows("fraud_records", records, key, "record_id"); records.clear()
            post_rows("evidence", evs, key, "evidence_id"); evs.clear()
    post_rows("fraud_records", records, key, "record_id")
    post_rows("evidence", evs, key, "evidence_id")
    return processed, processed


def ingest_penalties(path: Path, key: str, limit: Optional[int]) -> Tuple[int, int]:
    records: List[Dict[str, Any]] = []
    evs: List[Dict[str, Any]] = []
    source_name = f"penalty:{path.name}"
    processed = 0
    for row_no, row in enumerate(read_rows(path), 1):
        if limit is not None and processed >= limit:
            break
        processed += 1
        cid = hash_id(source_name, row_no, json.dumps(row, ensure_ascii=False, sort_keys=True))
        u = uniform(row)
        party = entity_name(row)
        agency = first(row, ("機關", "主管機關", "裁處機關", "處分機關", "agency_name"))
        date = first(row, ("裁罰日期", "處分日期", "公告日期", "裁處日期", "date"))
        violation = first(row, ("違反法令", "違反法規", "違規事實", "違規內容", "違反事項", "violation"))
        basis = first(row, ("法規依據", "法令依據", "legal_basis"))
        fine = first(row, ("罰鍰", "罰鍰金額", "處罰金額", "fine_amount"))
        records.append({
            "case_id": cid,
            "agency_name": agency,
            "party_name": party,
            "uniform_number": u,
            "penalty_date": date or None,
            "legal_basis": basis,
            "violation": violation,
            "fine_amount": parse_fine(fine),
            "source_url": first(row, ("來源網址", "source_url", "URL")),
            "source_record_id": str(row_no),
            "raw_data": row,
        })
        evs.append({
            "evidence_id": hash_id(source_name, row_no),
            "source_type": "government_dataset",
            "source_name": source_name,
            "source_record_id": str(row_no),
            "entity_id": u or party or cid,
            "entity_type": "company" if u else "organization",
            "fact_type": "penalty",
            "title": f"{agency} / {party}".strip(" /"),
            "summary": json.dumps(row, ensure_ascii=False),
            "confidence": 1,
            "raw_payload_json": row,
        })
        if len(records) >= BATCH:
            post_rows("penalties", records, key, "case_id"); records.clear()
            post_rows("evidence", evs, key, "evidence_id"); evs.clear()
    post_rows("penalties", records, key, "case_id")
    post_rows("evidence", evs, key, "evidence_id")
    return processed, processed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT_DEFAULT))
    parser.add_argument("--source", choices=("directors", "fraud", "penalties", "all"), required=True)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"找不到資料夾：{root}")
        return 1
    key = getpass.getpass("請貼上 Supabase secret key（sb_secret_...）：").strip()
    if not key:
        print("沒有輸入 key")
        return 1

    sources = [args.source] if args.source != "all" else ["directors", "fraud", "penalties"]
    total_read = 0
    total_written = 0
    for source in sources:
        files = list_files(root, source)
        print(f"\n[{source}] 找到 {len(files)} 個檔案", flush=True)
        for path in files:
            print(f"  → {path.relative_to(root)}", flush=True)
            try:
                if source == "directors":
                    read, written, _, _ = ingest_directors(path, key, args.limit)
                elif source == "fraud":
                    read, written = ingest_fraud(path, key, args.limit)
                else:
                    read, written = ingest_penalties(path, key, args.limit)
                print(f"    完成：讀取 {read:,}；寫入 {written:,}", flush=True)
                total_read += read
                total_written += written
            except Exception as exc:
                print(f"    ❌ {type(exc).__name__}: {exc}", flush=True)
    print("\n==============================")
    print(f"完成：讀取 {total_read:,}；寫入 {total_written:,}")
    print("==============================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
