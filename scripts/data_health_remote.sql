-- DATA Phase 6: read-only shared-DB audit. Run in Supabase SQL editor.
-- This intentionally reads every publication state; anon Data API sees only published rows.
select 'politician_entities' as source, publication_status as state, count(*) as rows
from public.entities where entity_type = 'Politician' group by publication_status
union all
select 'politician_terms', publication_status, count(*)
from public.politician_terms group by publication_status
union all
select 'political_contributions', status, count(*)
from public.relationships where relationship_type = 'POLITICAL_CONTRIBUTION_TO' group by status
union all
select 'asset_declarations', publication_status, count(*)
from public.asset_declarations group by publication_status
order by source, state;

-- Presence of additive DATA Phase 1–3 ingestion entrypoints.
select to_regprocedure('public.tei_ingest_political_master_bundle(jsonb)') is not null
         as master_ingest,
       to_regprocedure('public.tei_ingest_political_contribution_bundle(jsonb)') is not null
         as contribution_ingest,
       to_regprocedure('public.tei_ingest_asset_declaration_bundle(jsonb)') is not null
         as asset_ingest,
       to_regprocedure('public.tei_ingest_bundle(jsonb)') is not null
         as core_ingest;

-- Confirm RLS visibility differs from storage; do not disable policies.
select tablename, policyname, cmd, roles
from pg_policies
where schemaname = 'public'
  and tablename in ('entities', 'politician_terms', 'relationships', 'asset_declarations')
order by tablename, policyname;
