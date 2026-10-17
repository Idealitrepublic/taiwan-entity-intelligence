#!/usr/bin/env python3
"""Read-only identity and published-edge audit for tei-development.

Never prints connection details or source records. No source-only observation is
promoted to a canonical entity by this audit.
"""

import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.audit_graph_coverage_dev import is_development_target  # noqa: E402
from scripts.audit_p0_data_chain import development_environment  # noqa: E402


SQL = """
BEGIN READ ONLY;
select jsonb_build_object(
  'published_companies', (select count(*) from public.entities where entity_type='Company' and publication_status='published'),
  'verified_company_ids', (select count(distinct e.id) from public.entities e
    join public.entity_identifiers i on i.entity_id=e.id
    where e.entity_type='Company' and e.publication_status='published'
      and e.identity_status='EXACT' and i.namespace='tw:uniform_number' and i.value~'^[0-9]{8}$'),
  'company_registry_evidence', (select count(distinct e.id) from public.entities e
    join public.entity_evidence ee on ee.entity_id=e.id
    join public.evidence_records ev on ev.id=ee.evidence_id
    where e.entity_type='Company' and e.publication_status='published'
      and ev.source_class='Official Registry' and ev.status='active' and ev.publication_status='published'),
  'published_people', (select count(*) from public.entities where entity_type='Person' and publication_status='published'),
  'published_politicians', (select count(*) from public.entities where entity_type='Politician' and publication_status='published'),
  'politicians_with_official_ids', (select count(distinct e.id) from public.entities e
    join public.entity_identifiers i on i.entity_id=e.id
    where e.entity_type='Politician' and e.publication_status='published'
      and i.namespace='tw:legislative_yuan:legislator_number' and i.value<>''),
  'politician_edges', (select count(*) from public.relationships r
    join public.entities p on p.id=r.source_entity_id
    where r.status='published' and p.entity_type='Politician'),
  'politician_edges_with_matching_official_id', (select count(*) from public.relationships r
    join public.entities p on p.id=r.source_entity_id
    join public.evidence_records ev on ev.id=r.primary_evidence_id
    join public.entity_identifiers i on i.entity_id=p.id
      and i.namespace='tw:legislative_yuan:legislator_number'
      and i.value=ev.source_locator->>'legislator_number'
    where r.status='published' and p.entity_type='Politician'),
  'published_edges', (select count(*) from public.relationships where status='published'),
  'invalid_edges', (select count(*) from public.relationships r
    left join public.relationship_types t on t.code=r.relationship_type
    left join public.entities s on s.id=r.source_entity_id
    left join public.entities d on d.id=r.target_entity_id
    left join public.evidence_records ev on ev.id=r.primary_evidence_id
    where r.status='published' and (s.id is null or d.id is null
      or s.publication_status<>'published' or d.publication_status<>'published'
      or not s.entity_type=any(t.source_types) or not d.entity_type=any(t.target_types)
      or ev.id is null or ev.status<>'active' or ev.publication_status<>'published'
      or ev.source_url is null or ev.source_locator='{}'::jsonb
      or ev.retrieved_at>now() or ev.observed_at>now() or r.observed_at>now()
      or r.confidence not in ('EXACT','HIGH')
      or not exists(select 1 from public.relationship_evidence re
        where re.relationship_id=r.id and re.evidence_id=r.primary_evidence_id))),
  'duplicate_edges', (select count(*) from (select 1 from public.relationships
    where status='published' group by source_entity_id,target_entity_id,relationship_type,primary_evidence_id
    having count(*)>1) duplicate)
);
ROLLBACK;
"""


def validate(counts):
    for key, value in counts.items():
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"Invalid nonnegative count: {key}")
    for total, verified in (
        ("published_companies", "verified_company_ids"),
        ("published_companies", "company_registry_evidence"),
        ("published_politicians", "politicians_with_official_ids"),
        ("politician_edges", "politician_edges_with_matching_official_id"),
    ):
        if counts[total] != counts[verified]:
            raise ValueError(f"Identity/evidence coverage mismatch: {verified}")
    if counts["invalid_edges"] or counts["duplicate_edges"]:
        raise ValueError("Published edge integrity failed")
    return counts


def main():
    env = development_environment()
    if not is_development_target(env):
        raise RuntimeError("Database target is not the verified tei-development project")
    result = subprocess.run(
        ["psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
        input=SQL, text=True, capture_output=True, env=env, timeout=90,
    )
    if result.returncode:
        raise RuntimeError("Read-only Development integrity query failed; connection details suppressed")
    print(json.dumps(validate(json.loads(result.stdout.strip())), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
