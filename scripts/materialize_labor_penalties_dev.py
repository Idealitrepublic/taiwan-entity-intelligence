#!/usr/bin/env python3
"""Connect existing, explicitly identified MOL source records to canonical facts.

No name-only publication, Production connection, service-role key or new source.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.audit_p0_data_chain import development_environment, query  # noqa: E402
from src.entities.repository import MOEA_COMPANY_API  # noqa: E402
from src.labor_materialization import build_penalty_bundle, explicit_company_identifier  # noqa: E402


def apply_bundle(bundle, record_id, uniform):
    quoted = json.dumps(bundle, ensure_ascii=False).replace("'", "''")
    sql = ("BEGIN; SELECT public.tei_ingest_bundle('" + quoted + "'::jsonb);"
           " UPDATE public.source_records SET uniform_number='" + uniform + "'"
           " WHERE id='" + record_id.replace("'", "''") + "' AND (uniform_number IS NULL OR uniform_number='" + uniform + "'); COMMIT;")
    result = subprocess.run(["psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
                            input=sql, text=True, capture_output=True,
                            env=development_environment(), timeout=60)
    if result.returncode:
        raise RuntimeError("Development materialization failed; transaction rolled back; credentials suppressed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rows = json.loads(query("""
select coalesce(jsonb_agg(x),'[]') from (
 select id,source_file_id,source_url,indexed_at,uniform_number,raw from source_records
 where dataset='penalties' and (nullif(uniform_number,'') is not null
 or raw ?| array['統一編號','統編','Business_Accounting_NO']
 or raw->>'事業單位名稱或負責人' ~ '(統一編號|統編|\t)[ :：]*[0-9]{8}[[:space:]]*$')
 order by id limit 201)x;
"""))
    if len(rows) > 200:
        raise RuntimeError("Identifier-stage batch exceeds 200; no truncated coverage is accepted")
    applied = 0
    for record in rows:
        uniform = explicit_company_identifier(record)
        if not uniform:
            continue
        params = urllib.parse.urlencode({"$format": "json", "$filter": f"Business_Accounting_NO eq {uniform}", "$top": "1"})
        with urllib.request.urlopen(MOEA_COMPANY_API + "?" + params, timeout=20) as result:
            registry = json.load(result)
        if len(registry) != 1:
            raise RuntimeError("Official registry identifier did not resolve uniquely")
        existing = query("select coalesce(jsonb_agg(e),'[]') from entities e join entity_identifiers i on i.entity_id=e.id where i.namespace='tw:uniform_number' and i.value='" + uniform + "';")
        entities = json.loads(existing)
        if entities and (entities[0]["entity_type"] != "Company" or entities[0]["publication_status"] != "published"):
            raise RuntimeError("Existing identifier must reference a published Company; review required")
        bundle = build_penalty_bundle(record, registry[0],
                                      registry_retrieved_at=datetime.now(timezone.utc).isoformat(),
                                      company_entity_id=entities[0]["id"] if entities else None)
        if args.apply:
            apply_bundle(bundle, record["id"], uniform)
        applied += 1
    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "explicit_identifier_records": len(rows),
                      "verified_materializations": applied, "name_only_records": "not published"}))


if __name__ == "__main__":
    main()
