#!/usr/bin/env python3
"""Verify the official CEC registration ZIP and append a compact Development catalog."""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ingest_civil_organizations_dev import capacity_guard_sql, development_environment  # noqa: E402
from scripts.ops_restore_drill import query  # noqa: E402
from src.election_2026 import (  # noqa: E402
    COUNTIES, DATASET, EXPECTED_COUNT, ROSTER_URL, SNAPSHOT_DATE, SOURCES, ZIP_URL, read_roster,
)
from src.entities.models import stable_id, web_url  # noqa: E402


def prepare_context(rows):
    reviews = json.loads((ROOT / "src/election_2026_context.json").read_text())
    context = {}
    for review in reviews:
        matching = [r for r in rows if (r.name, r.district, r.office, r.recommending_party) ==
                    (review["name"], review["district"], review["office"], review["party"])]
        if len(matching) != 1:
            raise ValueError("Curated context must reference one exact CEC registration")
        facts = []
        for group in review["groups"]:
            source = web_url(group["source_url"])
            observations = group.get("facts") or [
                {"type": group["type"], "target": target, "role": group["role"]}
                for target in group["targets"]
            ]
            facts.extend({**fact, "source_url": source} for fact in observations)
        context[matching[0].id] = {
            "identity_url": web_url(review["identity_url"]),
            "entity_id": review.get("entity_id"),
            "related": facts,
        }
    return context


def county_payloads(rows, context):
    counties = defaultdict(list)
    for row in rows:
        record = asdict(row)
        if row.id in context:
            record["context"] = context[row.id]
        counties[row.district[:3]].append(record)
    return [
        {"id": f"{DATASET}:{SNAPSHOT_DATE}:{number:02d}", "county": county,
         "rows": counties[county]}
        for number, county in enumerate(COUNTIES)
    ]


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def import_sql(payloads, archive, digests, retrieved_at):
    file_id = stable_id("source-file", DATASET, SNAPSHOT_DATE)
    metadata = json.dumps({"scope": "registration_snapshot", "document_sha256": digests,
                           "office_counts": dict(zip((source[1] for source in SOURCES),
                                                     [sum(r["office"] == i for p in payloads for r in p["rows"])
                                                      for i in range(len(SOURCES))])),
                           "public_zip_url": ZIP_URL, "storage": "external_official_source"},
                          ensure_ascii=False)
    payload = json.dumps(payloads, ensure_ascii=False, separators=(",", ":"))
    return f"""BEGIN;
SET LOCAL standard_conforming_strings = on;
SET LOCAL statement_timeout = '60s';
{capacity_guard_sql()}
CREATE TEMP TABLE cec_stage ON COMMIT DROP AS
SELECT id, county, rows FROM jsonb_to_recordset({literal(payload)}::jsonb)
AS x(id text, county text, rows jsonb);
INSERT INTO public.source_files
  (id,dataset,object_path,file_name,format,size_bytes,sha256,source_url,
   downloaded_at,indexed_at,status,metadata)
VALUES ('{file_id}','{DATASET}','official/cec/2026/64709.zip','64709.zip','zip',
        {archive.stat().st_size},'{sha256(archive.read_bytes()).hexdigest()}','{ROSTER_URL}',
        '{retrieved_at}',now(),'indexed',{literal(metadata)}::jsonb)
ON CONFLICT (id) DO NOTHING;
INSERT INTO public.source_records (id,source_file_id,dataset,title,source_url,raw)
SELECT id,'{file_id}','{DATASET}',county,'{ROSTER_URL}',
       jsonb_build_object('county',county,'rows',rows,'snapshot_date','{SNAPSHOT_DATE}')
FROM cec_stage ON CONFLICT (id) DO NOTHING;
DO $$BEGIN
IF EXISTS (
  SELECT 1 FROM cec_stage s
  LEFT JOIN public.source_records r ON r.id=s.id
  WHERE r.id IS NULL OR r.source_file_id <> '{file_id}' OR r.dataset <> '{DATASET}'
      OR r.raw IS DISTINCT FROM jsonb_build_object('county',s.county,'rows',s.rows,
                                                   'snapshot_date','{SNAPSHOT_DATE}')
) OR (SELECT count(*) FROM public.source_records WHERE dataset='{DATASET}') <> {len(COUNTIES)}
THEN RAISE EXCEPTION 'Registration snapshot differs from the stored catalog'; END IF;
END$$;
{capacity_guard_sql()}
COMMIT;"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--apply-dev", action="store_true")
    args = parser.parse_args()
    archive = args.archive.resolve()
    if archive.is_relative_to(ROOT) or archive.parent.stat().st_mode & 0o077:
        parser.error("Use an owner-only source directory outside Git")
    rows, digests = read_roster(archive)
    context = prepare_context(rows)
    shards = county_payloads(rows, context)
    summary = {
        "registered": len(rows), "searchable_names": sum(row.name is not None for row in rows),
        "image_names_pending": sum(row.name is None for row in rows),
        "counties": len(shards), "offices": len({row.office for row in rows}),
        "party_recommendations": sum(row.recommending_party is not None for row in rows),
        "related_facts": dict(Counter(fact["type"] for item in context.values()
                                     for fact in item["related"])),
        "published_to_development": args.apply_dev,
    }
    if args.apply_dev:
        env = development_environment()
        query(env, import_sql(shards, archive, digests, datetime.now(timezone.utc).isoformat()),
              read_only=False)
        check = query(env, f"""select json_build_object('rows',sum(jsonb_array_length(raw->'rows')),
          'shards',count(*),'db_bytes',pg_database_size(current_database()))
          from public.source_records where dataset='{DATASET}'""")
        if check["rows"] != EXPECTED_COUNT or check["shards"] != len(COUNTIES):
            raise RuntimeError("Development catalog readback count differs")
        summary.update(check)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
