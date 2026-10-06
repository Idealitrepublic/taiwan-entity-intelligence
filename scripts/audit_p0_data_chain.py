#!/usr/bin/env python3
"""Read-only Development data-chain audit; never print connection credentials."""
import os
from pathlib import Path
import subprocess

def development_environment():
    value = os.environ.get("TEI_DEV_DATABASE_URL", "")
    if not value:
        for line in Path(".env.local").read_text().splitlines():
            if line.startswith("TEI_DEV_DATABASE_URL="):
                value = line.split("=", 1)[1].strip().strip("\"'")
    from scripts.ops_backup import database_environment
    env = os.environ.copy()
    env.update(database_environment(value), PGCONNECT_TIMEOUT="10")
    return env


def query(sql):
    result = subprocess.run(
        ["psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
        input="BEGIN READ ONLY;\n" + sql + "\nROLLBACK;\n", text=True,
        capture_output=True, env=development_environment(), timeout=90)
    if result.returncode:
        raise RuntimeError("Development read-only query failed; credentials suppressed")
    return result.stdout.strip()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    print(query("""
select jsonb_build_object(
 'legacy',jsonb_build_object('companies',(select count(*) from companies),'people',(select count(*) from people),'evidence',(select count(*) from evidence)),
 'canonical',jsonb_build_object('entities',(select count(*) from entities),'companies',(select count(*) from entities where entity_type='Company'),'people',(select count(*) from entities where entity_type='Person'),'politicians',(select count(*) from entities where entity_type='Politician'),'entity_evidence',(select count(*) from entity_evidence),'evidence_records',(select count(*) from evidence_records),'relationships',(select count(*) from relationships),'penalty_relationships',(select count(*) from relationships where relationship_type='RELATED_TO_PENALTY')),
 'source_records',(select count(*) from source_records),
 'workspace_items',(select count(*) from workspace_items),
 'broken_workspace_references',(select count(*) from workspace_items i left join entities e on e.id=coalesce(i.entity_id,i.graph_root_entity_id) left join relationships r on r.id=i.relationship_id left join evidence_records ev on ev.id=i.evidence_id where (coalesce(i.entity_id,i.graph_root_entity_id) is not null and e.id is null) or (i.relationship_id is not null and r.id is null) or (i.evidence_id is not null and ev.id is null)));
"""))
