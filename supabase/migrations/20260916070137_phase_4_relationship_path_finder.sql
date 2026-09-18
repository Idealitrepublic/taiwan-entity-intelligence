-- Phase 4: bounded, evidence-backed shortest paths between published entities.
create function public.find_entity_relationship_path(
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
  if start_entity_id = end_entity_id then
    raise exception 'Path endpoints must be different' using errcode = '22023';
  end if;
  if max_depth is null or max_depth < 1 or max_depth > 3 then
    raise exception 'Path max depth must be between 1 and 3' using errcode = '22023';
  end if;

  return query
  with recursive
  source_entity as (
    select e.* from public.entities e
     where e.id = start_entity_id and e.publication_status = 'published'
  ),
  target_entity as (
    select e.* from public.entities e
     where e.id = end_entity_id and e.publication_status = 'published'
  ),
  walk(current_id, visited_ids, segments, depth, path_order) as (
    select source_entity.id, array[source_entity.id], '[]'::jsonb, 0, array[]::uuid[]
      from source_entity
    union all
    select step.next_id,
           walk.visited_ids || step.next_id,
           walk.segments || jsonb_build_array(jsonb_build_object(
             'from_entity', step.from_entity,
             'to_entity', step.to_entity,
             'traversal_direction', step.traversal_direction,
             'relationship', step.relationship,
             'evidence', step.evidence
           )),
           walk.depth + 1,
           walk.path_order || step.relationship_id
      from walk
      cross join lateral (
        select r.id as relationship_id,
               next_entity.id as next_id,
               case when r.source_entity_id = walk.current_id then 'forward' else 'reverse' end
                 as traversal_direction,
               jsonb_build_object(
                 'id', current_entity.id,
                 'entity_type', current_entity.entity_type,
                 'canonical_name', current_entity.canonical_name,
                 'display_name', current_entity.display_name,
                 'identity_status', current_entity.identity_status
               ) as from_entity,
               jsonb_build_object(
                 'id', next_entity.id,
                 'entity_type', next_entity.entity_type,
                 'canonical_name', next_entity.canonical_name,
                 'display_name', next_entity.display_name,
                 'identity_status', next_entity.identity_status
               ) as to_entity,
               jsonb_build_object(
                 'id', r.id,
                 'source_entity_id', r.source_entity_id,
                 'target_entity_id', r.target_entity_id,
                 'relationship_type', r.relationship_type,
                 'primary_evidence_id', r.primary_evidence_id,
                 'start_date', r.start_date,
                 'end_date', r.end_date,
                 'date_precision', r.date_precision,
                 'observed_at', r.observed_at,
                 'amount', r.amount,
                 'currency', r.currency,
                 'percentage', r.percentage,
                 'quantity', r.quantity,
                 'quantity_unit', r.quantity_unit,
                 'source_role', r.source_role,
                 'confidence', r.confidence,
                 'status', r.status
               ) as relationship,
               jsonb_build_object(
                 'id', evidence.id,
                 'source_name', evidence.source_name,
                 'source_record_id', evidence.source_record_id,
                 'source_class', evidence.source_class,
                 'source_url', evidence.source_url,
                 'source_locator', evidence.source_locator,
                 'title', evidence.title,
                 'summary', evidence.summary,
                 'observed_at', evidence.observed_at,
                 'retrieved_at', evidence.retrieved_at,
                 'content_hash', evidence.content_hash,
                 'status', evidence.status
               ) as evidence
          from public.relationships r
          join public.entities current_entity on current_entity.id = walk.current_id
          join public.entities next_entity on next_entity.id = case
                 when r.source_entity_id = walk.current_id then r.target_entity_id
                 else r.source_entity_id end
          join public.evidence_records evidence on evidence.id = r.primary_evidence_id
         where (r.source_entity_id = walk.current_id or r.target_entity_id = walk.current_id)
           and r.status = 'published'
           and current_entity.publication_status = 'published'
           and next_entity.publication_status = 'published'
           and evidence.status = 'active'
           and evidence.publication_status = 'published'
           and not (next_entity.id = any(walk.visited_ids))
         order by r.id
         limit 50
      ) step
     where walk.depth < max_depth
  ),
  best_path as (
    select walk.segments, walk.depth
      from walk
     where walk.current_id = end_entity_id and walk.depth > 0
     order by walk.depth, walk.path_order
     limit 1
  )
  select jsonb_build_object(
           'found', best_path.depth is not null,
           'source_entity', jsonb_build_object(
             'id', source_entity.id,
             'entity_type', source_entity.entity_type,
             'canonical_name', source_entity.canonical_name,
             'display_name', source_entity.display_name,
             'identity_status', source_entity.identity_status
           ),
           'target_entity', jsonb_build_object(
             'id', target_entity.id,
             'entity_type', target_entity.entity_type,
             'canonical_name', target_entity.canonical_name,
             'display_name', target_entity.display_name,
             'identity_status', target_entity.identity_status
           ),
           'depth', best_path.depth,
           'segments', coalesce(best_path.segments, '[]'::jsonb),
           'max_depth', max_depth,
           'relationship_limit_per_node', 50,
           'traversal_bounded', true
         )
    from source_entity
    cross join target_entity
    left join best_path on true;
end $$;

comment on function public.find_entity_relationship_path(uuid,uuid,integer) is
  'Shortest evidence-backed path within max depth 3; cycle-free and capped at 50 relationships per expanded entity.';
revoke all on function public.find_entity_relationship_path(uuid,uuid,integer) from public;
grant execute on function public.find_entity_relationship_path(uuid,uuid,integer)
  to anon, authenticated, service_role;
