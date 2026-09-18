-- Phase 1 hardening is additive: no table or public response shape changes.
-- Publication predicates are repeated in policy bodies as defense in depth;
-- correctness no longer depends only on projection-refresh trigger ordering.

drop policy if exists published_search_terms on public.entity_search_terms;
create policy published_search_terms
on public.entity_search_terms for select to anon, authenticated
using (
  exists (
    select 1
      from public.entities entity
     where entity.id = entity_id
       and entity.publication_status = 'published'
  )
);

drop policy if exists published_public_identifiers on public.entity_public_identifiers;
create policy published_public_identifiers
on public.entity_public_identifiers for select to anon, authenticated
using (
  exists (
    select 1
      from public.entities entity
     where entity.id = entity_id
       and entity.publication_status = 'published'
  )
);

drop policy if exists published_relationships on public.relationships;
create policy published_relationships
on public.relationships for select to anon, authenticated
using (
  status = 'published'
  and exists (
    select 1
      from public.evidence_records evidence
     where evidence.id = primary_evidence_id
       and evidence.status = 'active'
       and evidence.publication_status = 'published'
  )
  and exists (
    select 1
      from public.entities source
     where source.id = source_entity_id
       and source.publication_status = 'published'
  )
  and exists (
    select 1
      from public.entities target
     where target.id = target_entity_id
       and target.publication_status = 'published'
  )
);

drop policy if exists published_entity_evidence on public.entity_evidence;
create policy published_entity_evidence
on public.entity_evidence for select to anon, authenticated
using (
  exists (
    select 1
      from public.entities entity
     where entity.id = entity_id
       and entity.publication_status = 'published'
  )
  and exists (
    select 1
      from public.evidence_records evidence
     where evidence.id = evidence_id
       and evidence.status = 'active'
       and evidence.publication_status = 'published'
  )
);

drop policy if exists published_relationship_evidence on public.relationship_evidence;
create policy published_relationship_evidence
on public.relationship_evidence for select to anon, authenticated
using (
  exists (
    select 1
      from public.relationships relationship
     where relationship.id = relationship_id
       and relationship.status = 'published'
  )
  and exists (
    select 1
      from public.evidence_records evidence
     where evidence.id = evidence_id
       and evidence.status = 'active'
       and evidence.publication_status = 'published'
  )
);

-- Existing grants stay explicit when this migration is applied to projects
-- that no longer auto-expose new Data API objects.
grant select on public.entity_search_terms, public.entity_public_identifiers,
  public.entities, public.evidence_records, public.relationships,
  public.entity_evidence, public.relationship_evidence to anon, authenticated;
