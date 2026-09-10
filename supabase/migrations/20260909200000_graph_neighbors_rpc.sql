-- Phase 3: one bounded, RLS-aware round trip per lazy node expansion.
create function public.graph_entity_neighbors(
  focus_id uuid,
  result_limit integer default 12,
  after_relationship_id uuid default null,
  relationship_type_filter text default null
) returns table (
  focus_entity jsonb,
  relationship jsonb,
  source_entity jsonb,
  target_entity jsonb,
  primary_evidence jsonb
)
language plpgsql
stable
security invoker
set search_path = ''
as $$
begin
  if result_limit is null or result_limit < 1 or result_limit > 25 then
    raise exception 'Graph result limit must be between 1 and 25' using errcode = '22023';
  end if;
  if relationship_type_filter is not null and not exists (
    select 1 from public.relationship_types t where t.code = relationship_type_filter
  ) then
    raise exception 'Unknown relationship type' using errcode = '22023';
  end if;

  return query
  select jsonb_build_object(
           'id', focus.id, 'entity_type', focus.entity_type,
           'canonical_name', focus.canonical_name, 'display_name', focus.display_name,
           'identity_status', focus.identity_status
         ),
         case when neighbor.relationship_id is null then null else jsonb_build_object(
           'id', neighbor.relationship_id,
           'source_entity_id', neighbor.source_entity_id,
           'target_entity_id', neighbor.target_entity_id,
           'relationship_type', neighbor.relationship_type,
           'primary_evidence_id', neighbor.primary_evidence_id,
           'start_date', neighbor.start_date,
           'end_date', neighbor.end_date,
           'date_precision', neighbor.date_precision,
           'observed_at', neighbor.observed_at,
           'amount', neighbor.amount,
           'currency', neighbor.currency,
           'percentage', neighbor.percentage,
           'quantity', neighbor.quantity,
           'quantity_unit', neighbor.quantity_unit,
           'source_role', neighbor.source_role,
           'confidence', neighbor.confidence,
           'status', neighbor.status
         ) end,
         case when neighbor.relationship_id is null then null else jsonb_build_object(
           'id', neighbor.source_id, 'entity_type', neighbor.source_type,
           'canonical_name', neighbor.source_canonical_name,
           'display_name', neighbor.source_display_name,
           'identity_status', neighbor.source_identity_status
         ) end,
         case when neighbor.relationship_id is null then null else jsonb_build_object(
           'id', neighbor.target_id, 'entity_type', neighbor.target_type,
           'canonical_name', neighbor.target_canonical_name,
           'display_name', neighbor.target_display_name,
           'identity_status', neighbor.target_identity_status
         ) end,
         case when neighbor.relationship_id is null then null else jsonb_build_object(
           'id', neighbor.evidence_id,
           'source_name', neighbor.evidence_source_name,
           'source_record_id', neighbor.evidence_source_record_id,
           'source_class', neighbor.evidence_source_class,
           'source_url', neighbor.evidence_source_url,
           'source_locator', neighbor.evidence_source_locator,
           'title', neighbor.evidence_title,
           'summary', neighbor.evidence_summary,
           'observed_at', neighbor.evidence_observed_at,
           'retrieved_at', neighbor.evidence_retrieved_at,
           'content_hash', neighbor.evidence_content_hash,
           'status', neighbor.evidence_status
         ) end
    from public.entities focus
    left join lateral (
      select r.id as relationship_id, r.source_entity_id, r.target_entity_id,
             r.relationship_type, r.primary_evidence_id, r.start_date, r.end_date,
             r.date_precision, r.observed_at, r.amount, r.currency, r.percentage,
             r.quantity, r.quantity_unit, r.source_role, r.confidence, r.status,
             source.id as source_id, source.entity_type as source_type,
             source.canonical_name as source_canonical_name,
             source.display_name as source_display_name,
             source.identity_status as source_identity_status,
             target.id as target_id, target.entity_type as target_type,
             target.canonical_name as target_canonical_name,
             target.display_name as target_display_name,
             target.identity_status as target_identity_status,
             evidence.id as evidence_id, evidence.source_name as evidence_source_name,
             evidence.source_record_id as evidence_source_record_id,
             evidence.source_class as evidence_source_class,
             evidence.source_url as evidence_source_url,
             evidence.source_locator as evidence_source_locator,
             evidence.title as evidence_title, evidence.summary as evidence_summary,
             evidence.observed_at as evidence_observed_at,
             evidence.retrieved_at as evidence_retrieved_at,
             evidence.content_hash as evidence_content_hash,
             evidence.status as evidence_status
        from public.relationships r
        join public.entities source on source.id = r.source_entity_id
        join public.entities target on target.id = r.target_entity_id
        join public.evidence_records evidence on evidence.id = r.primary_evidence_id
       where (r.source_entity_id = focus.id or r.target_entity_id = focus.id)
         and r.status = 'published'
         and evidence.status = 'active'
         and (after_relationship_id is null or r.id > after_relationship_id)
         and (relationship_type_filter is null or r.relationship_type = relationship_type_filter)
       order by r.id
       limit result_limit + 1
    ) neighbor on true
   where focus.id = focus_id and focus.publication_status = 'published'
   order by neighbor.relationship_id nulls first;
end $$;

comment on function public.graph_entity_neighbors(uuid,integer,uuid,text) is
  'RLS-aware one-hop graph expansion. Returns at most result_limit + 1 rows so callers can expose a bounded cursor.';
revoke all on function public.graph_entity_neighbors(uuid,integer,uuid,text) from public;
grant execute on function public.graph_entity_neighbors(uuid,integer,uuid,text)
  to anon, authenticated, service_role;
