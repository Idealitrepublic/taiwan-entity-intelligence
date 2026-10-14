-- Find a direct link or an identical published intermediary for two published companies.
-- Endpoint-indexed joins avoid the older path RPC's arbitrary first-50 edge cutoff.
create function public.find_company_shared_node_path(
  start_entity_id uuid,
  end_entity_id uuid,
  max_depth integer default 3
) returns table (path_result jsonb)
language plpgsql
stable
security invoker
set search_path = ''
as $$
begin
  if start_entity_id = end_entity_id or max_depth is null or max_depth < 1 or max_depth > 3 then
    raise exception 'Invalid company path bounds' using errcode = '22023';
  end if;

  return query
  with source_entity as (
    select e.id, jsonb_build_object('id', e.id, 'entity_type', e.entity_type,
      'canonical_name', e.canonical_name, 'display_name', e.display_name,
      'identity_status', e.identity_status) as node
    from public.entities e
    where e.id = start_entity_id and e.entity_type = 'Company'
      and e.publication_status = 'published'
  ), target_entity as (
    select e.id, jsonb_build_object('id', e.id, 'entity_type', e.entity_type,
      'canonical_name', e.canonical_name, 'display_name', e.display_name,
      'identity_status', e.identity_status) as node
    from public.entities e
    where e.id = end_entity_id and e.entity_type = 'Company'
      and e.publication_status = 'published'
  ), adjacent as (
    select endpoint.id as endpoint_id, endpoint.node as endpoint_node,
      neighbor.id as neighbor_id,
      jsonb_build_object('id', neighbor.id, 'entity_type', neighbor.entity_type,
        'canonical_name', neighbor.canonical_name, 'display_name', neighbor.display_name,
        'identity_status', neighbor.identity_status) as neighbor_node,
      r.id as relationship_id, r.source_entity_id,
      jsonb_build_object('id', r.id, 'source_entity_id', r.source_entity_id,
        'target_entity_id', r.target_entity_id, 'relationship_type', r.relationship_type,
        'primary_evidence_id', r.primary_evidence_id, 'start_date', r.start_date,
        'end_date', r.end_date, 'date_precision', r.date_precision,
        'observed_at', r.observed_at, 'amount', r.amount, 'currency', r.currency,
        'percentage', r.percentage, 'quantity', r.quantity,
        'quantity_unit', r.quantity_unit, 'source_role', r.source_role,
        'confidence', r.confidence, 'status', r.status) as relationship,
      jsonb_build_object('id', evidence.id, 'source_name', evidence.source_name,
        'source_record_id', evidence.source_record_id, 'source_class', evidence.source_class,
        'source_url', evidence.source_url, 'source_locator', evidence.source_locator,
        'title', evidence.title, 'summary', evidence.summary,
        'observed_at', evidence.observed_at, 'retrieved_at', evidence.retrieved_at,
        'content_hash', evidence.content_hash, 'status', evidence.status) as evidence
    from (select * from source_entity union all select * from target_entity) endpoint
    join public.relationships r
      on r.source_entity_id = endpoint.id or r.target_entity_id = endpoint.id
    join public.entities neighbor on neighbor.id = case
      when r.source_entity_id = endpoint.id then r.target_entity_id
      else r.source_entity_id end
    join public.evidence_records evidence on evidence.id = r.primary_evidence_id
    where r.status = 'published' and neighbor.publication_status = 'published'
      and evidence.status = 'active' and evidence.publication_status = 'published'
  ), candidates as (
    select 1 as depth, array[a.relationship_id] as path_order,
      jsonb_build_array(jsonb_build_object(
        'from_entity', a.endpoint_node, 'to_entity', a.neighbor_node,
        'traversal_direction', case when a.source_entity_id = a.endpoint_id
          then 'forward' else 'reverse' end,
        'relationship', a.relationship, 'evidence', a.evidence)) as segments
    from adjacent a
    where a.endpoint_id = start_entity_id and a.neighbor_id = end_entity_id
    union all
    select 2, array[a.relationship_id, b.relationship_id],
      jsonb_build_array(
        jsonb_build_object('from_entity', a.endpoint_node, 'to_entity', a.neighbor_node,
          'traversal_direction', case when a.source_entity_id = a.endpoint_id
            then 'forward' else 'reverse' end,
          'relationship', a.relationship, 'evidence', a.evidence),
        jsonb_build_object('from_entity', b.neighbor_node, 'to_entity', b.endpoint_node,
          'traversal_direction', case when b.source_entity_id = b.neighbor_id
            then 'forward' else 'reverse' end,
          'relationship', b.relationship, 'evidence', b.evidence))
    from adjacent a
    join adjacent b on b.neighbor_id = a.neighbor_id
    where max_depth >= 2 and a.endpoint_id = start_entity_id
      and b.endpoint_id = end_entity_id
      and a.neighbor_id <> start_entity_id and a.neighbor_id <> end_entity_id
  )
  select jsonb_build_object('found', true, 'source_entity', source_entity.node,
    'target_entity', target_entity.node, 'depth', best.depth,
    'segments', best.segments, 'max_depth', max_depth,
    'relationship_limit_per_node', null, 'traversal_bounded', true,
    'truncated', false, 'shared_node_complete', true,
    'backend', 'company_shared_node')
  from source_entity cross join target_entity
  cross join lateral (select * from candidates order by depth, path_order limit 1) best;
end $$;

comment on function public.find_company_shared_node_path(uuid,uuid,integer) is
  'Shortest direct or shared-canonical-node company path, with public evidence and no first-N edge cutoff; depth 3 remains handled by the bounded generic finder.';
revoke all on function public.find_company_shared_node_path(uuid,uuid,integer) from public;
grant execute on function public.find_company_shared_node_path(uuid,uuid,integer)
  to anon, authenticated, service_role;
