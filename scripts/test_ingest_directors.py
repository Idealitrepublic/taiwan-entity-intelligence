#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Small smoke test: find the director CSV in Supabase Storage and ingest 1000 rows.

Uses modern Supabase sb_secret_* keys correctly: only the `apikey` header is sent.
No secret is written to disk or GitHub.
"""
from __future__ import annotations

import csv
import getpass
import hashlib
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request

SUPABASE_URL = "https://ohvrrqbogxyjivcigbpl.supabase.co"
BUCKET = "raw-data"
PREFIX = "raw/"
LIMIT = 1000


def request(method, url, key, payload=None):
    data = None
    headers = {"apikey": key, "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def list_objects(key):
    url = f"{SUPABASE_URL}/storage/v1/object/list/{BUCKET}"
    rows = json.loads(request("POST", url, key, {
        "prefix": PREFIX,
        "limit": 1000,
        "offset": 0,
        "sortBy": {"column": "name", "order": "asc"},
    }).decode("utf-8"))
    return [x for x in rows if isinstance(x, dict) and x.get("name")]


def decode(raw):
    for enc in ("utf-8-sig", "utf-8", "cp950", "big5", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def norm(s):
    return re.sub(r"[\s　_\-()（）/]+", "", (s or "").strip().lower())


def is_director(text):
    first = text.splitlines()[0] if text.splitlines() else ""
    try:
        cols = [norm(x) for x in next(csv.reader([first]), [])]
    except StopIteration:
        return False
    joined = "|".join(cols)
    return sum(k in joined for k in ("統一編號", "公司名稱", "職稱", "姓名", "所代表法人", "持有股份數")) >= 4


def row_dict(header, row):
    return {header[i].strip(): (row[i].strip() if i < len(row) else "") for i in range(len(header))}


def getv(d, *names):
    m = {norm(k): v for k, v in d.items()}
    for n in names:
        v = m.get(norm(n), "")
        if v:
            return v
    return ""


def evidence_id(path, row_no):
    return hashlib.sha256(f"{path}|{row_no}|director".encode()).hexdigest()


def post(table, rows, key, conflict=None):
    if not rows:
        return
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if conflict:
        url += "?on_conflict=" + urllib.parse.quote(conflict, safe=",")
    req = urllib.request.Request(
        url,
        data=json.dumps(rows, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "apikey": key,
            "Content-Type": "application/json",
            "Prefer": "resolution=ignore-duplicates,return=minimal",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        r.read()


def main():
    key = getpass.getpass("Supabase secret key（sb_secret_...；輸入不會顯示）：").strip()
    if not key:
        print("沒有輸入 key")
        return 1

    objects = list_objects(key)
    print(f"raw/ 物件：{len(objects)}")

    found = None
    text = ""
    for obj in objects:
        name = obj["name"]
        if name.endswith("/"):
            continue
        url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{urllib.parse.quote(name, safe='/')}"
        try:
            raw = request("GET", url, key)
        except Exception as e:
            print(f"跳過 {name}: {e}")
            continue
        t = decode(raw)
        if is_director(t):
            found = name
            text = t
            print(f"找到董監事資料：{name} ({len(raw):,} bytes)")
            break

    if not found:
        print("找不到符合董監事欄位的資料檔")
        return 2

    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    people, companies, rels, evs = [], [], [], []
    seen_people, seen_companies, seen_rels = set(), set(), set()
    count = 0

    for row_no, row in enumerate(reader, 2):
        if count >= LIMIT:
            break
        d = row_dict(header, row)
        uniform = getv(d, "統一編號", "統編")
        company = getv(d, "公司名稱", "公司")
        name = getv(d, "姓名", "董事姓名", "監察人姓名")
        position = getv(d, "職稱")
        if not name or not company:
            continue

        if name not in seen_people:
            seen_people.add(name)
            people.append({
                "name": name,
                "normalized_name": re.sub(r"\s+", "", name).upper(),
                "source_name": "董監事資料集",
                "source_record_id": f"{found}#{row_no}",
                "raw_data": d,
            })
        if uniform and uniform not in seen_companies:
            seen_companies.add(uniform)
            companies.append({
                "uniform_number": uniform,
                "company_name": company,
                "source_name": "董監事資料集",
                "source_record_id": f"{found}#{row_no}",
                "raw_data": d,
            })

        rid = (uniform or company, name, position)
        if rid not in seen_rels:
            seen_rels.add(rid)
            eid = evidence_id(found, row_no)
            rels.append({
                "source_entity_type": "company",
                "source_entity_id": uniform or company,
                "relationship_type": position or "董監事",
                "target_entity_type": "person",
                "target_entity_id": name,
                "confidence": 1.0,
                "evidence_ids": [eid],
                "source_name": "董監事資料集",
                "source_record_id": f"{found}#{row_no}",
            })
            evs.append({
                "evidence_id": eid,
                "source_type": "government_open_data",
                "source_name": "董監事資料集",
                "source_record_id": f"{found}#{row_no}",
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
        count += 1

    # Small batches keep requests reliable.
    for start in range(0, len(people), 100):
        post("people", people[start:start+100], key)
    for start in range(0, len(companies), 100):
        post("companies", companies[start:start+100], key, "uniform_number")
    for start in range(0, len(rels), 100):
        post("relationships", rels[start:start+100], key)
    for start in range(0, len(evs), 100):
        post("evidence", evs[start:start+100], key)

    print("\n✅ 董監事匯入測試成功")
    print(f"讀取資料列：{count}")
    print(f"人物：{len(people)}")
    print(f"公司：{len(companies)}")
    print(f"關係：{len(rels)}")
    print(f"Evidence：{len(evs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
