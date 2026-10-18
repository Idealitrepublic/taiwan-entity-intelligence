#!/usr/bin/env python3
"""Read-only graph coverage baseline for the isolated tei-development project.

Prints aggregate counts only. It never promotes name matches or writes to a DB.
"""
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.audit_p0_data_chain import development_environment  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_REF = "canqjiokrtcxkwblhmml"
SQL = r"""
BEGIN READ ONLY;
select jsonb_build_object(
  'entities', (select coalesce(jsonb_object_agg(entity_type,n),'{}'::jsonb) from
    (select entity_type,count(*)::int n from public.entities
     where publication_status='published' group by entity_type) t),
  'relationships', (select coalesce(jsonb_object_agg(relationship_type,n),'{}'::jsonb) from
    (select relationship_type,count(*)::int n from public.relationships
     where status='published' group by relationship_type) t),
  'published_evidence', (select count(*)::int from public.evidence_records
    where publication_status='published' and status='active'),
  'published_evidence_freshness', (select coalesce(jsonb_object_agg(source_name,latest),'{}'::jsonb)
    from (select source_name,max(retrieved_at) as latest from public.evidence_records
      where publication_status='published' and status='active' group by source_name) t),
  'traceable_edges', (select count(*)::int from public.relationships r
    join public.evidence_records ev on ev.id=r.primary_evidence_id
    join public.entities s on s.id=r.source_entity_id
    join public.entities t on t.id=r.target_entity_id
    where r.status='published' and ev.publication_status='published'
      and ev.status='active' and (ev.source_url is not null or ev.source_locator<>'{}'::jsonb)
      and s.publication_status='published' and t.publication_status='published'),
  'source_records', (select coalesce(jsonb_object_agg(dataset,n),'{}'::jsonb) from
    (select dataset,count(*)::int n from public.source_records group by dataset) t),
  'labor_identifier_candidates', (select count(*)::int from public.source_records
    where dataset='penalties' and (uniform_number ~ '^[0-9]{8}$'
      or raw ?| array['統一編號','統編','Business_Accounting_NO']
      or raw->>'事業單位名稱或負責人' ~ '(統一編號|統編|\t)[ :：]*[0-9]{8}[[:space:]]*$')),
  'labor_distinct_source_names', (select count(distinct company_name)::int
    from public.source_records where dataset='penalties'),
  'labor_exact_id_rows', (select count(*)::int from public.source_records
    where dataset='penalties' and uniform_number ~ '^[0-9]{8}$'),
  'labor_exact_id_published_company_rows', (select count(distinct s.id)::int
    from public.source_records s
    join public.entity_identifiers i on i.namespace='tw:uniform_number'
      and i.value=s.uniform_number
    join public.entities e on e.id=i.entity_id
      and e.entity_type='Company' and e.publication_status='published'
    where s.dataset='penalties' and s.uniform_number ~ '^[0-9]{8}$'),
  'donor_candidate_ids', (with donors as (
    select ev.source_locator->>'donor_uniform_number' as uniform,
      regexp_replace(ev.title,'^政治獻金來源紀錄：','') as donor_name
    from public.evidence_records ev
    where ev.source_name='監察院政治獻金公開查閱平臺'
      and ev.source_locator->>'donor_uniform_number' ~ '^[0-9]{8}$'
  ), grouped as (
    select uniform,count(distinct donor_name) labels,
      bool_and(donor_name ~ '(股份有限公司|有限公司)$') legal_suffix
    from donors group by uniform
  ) select jsonb_build_object(
      'all',count(*)::int,
      'single_company_label',count(*) filter(where labels=1 and legal_suffix)::int,
      'conflicting_labels',count(*) filter(where labels>1)::int,
      'noncompany_form',count(*) filter(where labels=1 and not legal_suffix)::int)
    from grouped)
  ,'donor_ids_with_published_company', (with ids as (
    select distinct ev.source_locator->>'donor_uniform_number' as uniform
    from public.evidence_records ev
    where ev.source_name='監察院政治獻金公開查閱平臺'
      and ev.publication_status='draft'
      and ev.source_locator->>'donor_uniform_number' ~ '^[0-9]{8}$'
  ) select count(*)::int from ids where exists (
    select 1 from public.entity_identifiers i
    join public.entities e on e.id=i.entity_id
    where i.namespace='tw:uniform_number' and i.value=ids.uniform
      and e.entity_type='Company' and e.publication_status='published'))
  ,'draft_contribution_candidate_ids', (select count(distinct ev.source_locator->>'candidate_id')::int
    from public.evidence_records ev
    where ev.source_name='監察院政治獻金公開查閱平臺'
      and ev.publication_status='draft' and ev.source_locator ? 'candidate_id')
);
ROLLBACK;
"""


def read_development_counts():
    env = development_environment()
    # Direct DB host or transaction-pooler username must identify this project.
    if not is_development_target(env):
        raise RuntimeError("Database target is not the verified tei-development project")
    result = subprocess.run(
        ["psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
        input=SQL, text=True, capture_output=True, env=env, timeout=90,
    )
    if result.returncode:
        raise RuntimeError("Read-only Development coverage query failed; connection details suppressed")
    return json.loads(result.stdout.strip())


def is_development_target(env):
    target = f"{env.get('PGHOST', '')} {env.get('PGUSER', '')}"
    return DEVELOPMENT_REF in target


def summarize(counts, judicial_index):
    entities = counts["entities"]
    relationships = counts["relationships"]
    total_edges = sum(relationships.values())
    traceable = counts["traceable_edges"]
    if any(not isinstance(value, int) or value < 0 for value in
           [*entities.values(), *relationships.values(), counts["published_evidence"],
            *counts["source_records"].values(), traceable,
            counts["labor_identifier_candidates"], counts["labor_distinct_source_names"],
            counts["labor_exact_id_rows"], counts["labor_exact_id_published_company_rows"],
            counts["donor_ids_with_published_company"],
            counts["draft_contribution_candidate_ids"], judicial_index["records"],
            *counts["donor_candidate_ids"].values()]):
        raise ValueError("Coverage counters must be nonnegative integers")
    if traceable > total_edges:
        raise ValueError("Traceable edges exceed published edges")
    if counts["labor_identifier_candidates"] > counts["source_records"].get("penalties", 0):
        raise ValueError("Labor identifier candidates exceed indexed labor rows")
    if (counts["labor_exact_id_rows"] > counts["labor_identifier_candidates"]
            or counts["labor_exact_id_published_company_rows"] > counts["labor_exact_id_rows"]
            or counts["labor_distinct_source_names"] > counts["source_records"].get("penalties", 0)):
        raise ValueError("Labor identifier or name counters do not reconcile")
    donor = counts["donor_candidate_ids"]
    if (donor["single_company_label"] + donor["conflicting_labels"]
            + donor["noncompany_form"] != donor["all"]):
        raise ValueError("Donor identifier categories do not reconcile")
    if counts["donor_ids_with_published_company"] > donor["all"]:
        raise ValueError("Verified donor-company IDs exceed donor candidates")
    if not judicial_index.get("generated_at"):
        raise ValueError("Judicial index timestamp is required")
    return {
        "environment": "tei-development",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "published": {
            "companies": entities.get("Company", 0),
            "people": entities.get("Person", 0),
            "politicians": entities.get("Politician", 0),
            "contracts": entities.get("Contract", 0),
            "judgments": entities.get("Judgment", 0),
            "penalties": entities.get("Penalty", 0),
            "contract_edges": relationships.get("CONTRACT_WITH", 0),
            "judgment_edges": relationships.get("RELATED_TO_JUDGMENT", 0),
            "penalty_edges": relationships.get("RELATED_TO_PENALTY", 0),
            "all_edges": total_edges,
            "traceable_edges": traceable,
            "active_evidence": counts["published_evidence"],
            "evidence_latest_retrieved_at_by_source": counts["published_evidence_freshness"],
        },
        "source_only": {
            "labor_index_rows": counts["source_records"].get("penalties", 0),
            "labor_identifier_field_candidates": counts["labor_identifier_candidates"],
            "labor_distinct_source_names": counts["labor_distinct_source_names"],
            "labor_exact_id_rows": counts["labor_exact_id_rows"],
            "labor_exact_id_published_company_rows": counts["labor_exact_id_published_company_rows"],
            "political_donor_identifier_candidates": donor,
            "donor_ids_with_published_company": counts["donor_ids_with_published_company"],
            "draft_contribution_candidate_ids": counts["draft_contribution_candidate_ids"],
            "judicial_company_name_index_rows": judicial_index["records"],
            "judicial_index_generated_at": judicial_index["generated_at"],
            "procurement": "live first-page lookup; no persisted source-record denominator",
            "directors": "live per-company registry lookup; no persisted source-record denominator",
        },
        "interpretation": [
            "Counts are Development snapshots, not national coverage or source recall.",
            "A labor identifier-field candidate still requires exact ID and registry-name verification before publication.",
            "Distinct labor source names are not distinct verified companies; name-only rows are not canonical links.",
            "Political donor IDs are draft source candidates; company-form labels are not registry verification.",
            "A verified donor Company does not establish the Candidate/Politician endpoint of a donation Relationship.",
            "Judicial company-name index rows are candidates, not verified case-role relationships.",
            "Published edges are counted only when both endpoints and active primary Evidence are public.",
        ],
    }


def main():
    index = json.loads((ROOT / "data/judicial_company_index.json").read_text())
    report = summarize(read_development_counts(), {
        "records": len(index.get("records") or []),
        "generated_at": index.get("generated_at"),
    })
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
