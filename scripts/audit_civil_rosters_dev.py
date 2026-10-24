#!/usr/bin/env python3
"""Read-only Development audit for official civil-organization roster imports."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ingest_civil_organizations_dev import development_environment  # noqa: E402
from src.civil_roster_sources import SOURCES  # noqa: E402


def read_json(query, env):
    result = subprocess.run(["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1",
                             "-c", query], env=env, capture_output=True, text=True,
                            timeout=90)
    if result.returncode:
        raise RuntimeError("Development audit query failed")
    return json.loads(result.stdout.strip())


def main():
    env = development_environment()
    expected = {source["name"]: source["expected_rows"] for source in SOURCES.values()
                if source.get("expected_rows") is not None}
    counts = read_json("select coalesce(jsonb_object_agg(source,n),'{}'::jsonb) "
                       "from (select source,count(*) n from public.entities "
                       "where entity_type='CivilOrganization' and publication_status='published' "
                       "group by source) x", env)
    mismatches = {name: {"expected": count, "actual": counts.get(name, 0)}
                  for name, count in expected.items() if counts.get(name, 0) != count}
    result = read_json("select jsonb_build_object("
                       "'entities',count(*),'evidence_links',count(ee.evidence_id),"
                       "'missing_or_duplicate_evidence',count(*) filter (where links.n <> 1),"
                       "'missing_provenance',count(*) filter (where ev.source_url is null "
                       "or ev.retrieved_at is null or ev.source_locator->>'snapshot_sha256' is null "
                       "or ev.source_name <> e.source)) "
                       "from public.entities e "
                       "left join lateral (select count(*) n from public.entity_evidence x "
                       "where x.entity_id=e.id) links on true "
                       "left join public.entity_evidence ee on ee.entity_id=e.id "
                       "left join public.evidence_records ev on ev.id=ee.evidence_id "
                       "where e.entity_type='CivilOrganization' and e.publication_status='published'",
                       env)
    rls = read_json("select coalesce(jsonb_object_agg(relname,relrowsecurity),'{}'::jsonb) "
                    "from pg_class where relnamespace='public'::regnamespace "
                    "and relname in ('entities','evidence_records','entity_evidence')", env)
    size_mb = read_json("select to_jsonb(round(pg_database_size(current_database())/1024.0/1024.0,1))", env)
    output = {"new_source_count": len(expected), "new_source_rows": sum(expected.values()),
              "published_entities": result["entities"], "evidence_links": result["evidence_links"],
              "missing_or_duplicate_evidence": result["missing_or_duplicate_evidence"],
              "missing_provenance": result["missing_provenance"],
              "source_count_mismatches": mismatches, "rls": rls,
              "database_size_mb": size_mb}
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    if mismatches or result["missing_or_duplicate_evidence"] or result["missing_provenance"] \
            or not all(rls.get(table) is True for table in ("entities", "evidence_records", "entity_evidence")):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError):
        print("Development roster audit failed without exposing credentials", file=sys.stderr)
        raise SystemExit(1) from None
