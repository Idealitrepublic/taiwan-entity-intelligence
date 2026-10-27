-- Public exact counts were exceeding anon's 3s statement timeout (57014).
-- Cover the existing RLS predicates without changing policies or privileges.
-- Read paths can use index-only scans rather than scanning wide Evidence rows.
set local lock_timeout = '3s';
set local statement_timeout = '30s';

create index if not exists entities_published_type_id_idx
  on public.entities (entity_type, id)
  where publication_status = 'published';

create index if not exists evidence_records_public_active_id_idx
  on public.evidence_records (id)
  where publication_status = 'published' and status = 'active';

analyze public.entities;
analyze public.evidence_records;

-- Rollback, only if necessary: drop the two indexes above. No data, RLS policy,
-- role timeout, public grant or function changes are required in either direction.
