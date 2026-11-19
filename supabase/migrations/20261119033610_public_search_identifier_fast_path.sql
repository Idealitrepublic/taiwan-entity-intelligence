-- Additive follow-up: retain caller RLS and the full ranked fallback.
create or replace function public.search_entities(
  search_query text,
  entity_type_filter text default null,
  result_limit integer default 20
) returns table (
  entity_id uuid, entity_type text, canonical_name text, display_name text,
  identity_status text, public_identifier text, context_label text, match_type text
)
language plpgsql stable security invoker
set search_path = ''
-- This bounded interactive read does not benefit from seconds of per-query JIT.
-- Scoped to this function only; no role/global timeout or planner settings change.
set jit = off
as $$
declare
  normalized text := lower(normalize(btrim(search_query), NFKC));
  escaped text;
begin
  if normalized is null or char_length(normalized) < 2 or char_length(normalized) > 100
     or normalized ~ '[[:cntrl:]]' then
    raise exception 'Search query must contain 2 to 100 printable characters'
      using errcode = '22023';
  end if;
  if result_limit is null or result_limit < 1 or result_limit > 20 then
    raise exception 'Search result limit must be between 1 and 20'
      using errcode = '22023';
  end if;
  if entity_type_filter is not null and not exists (
    select 1 from public.entity_types kind where kind.code = entity_type_filter
  ) then
    raise exception 'Unknown entity type' using errcode = '22023';
  end if;

  -- Uniform-number resolution is also used internally with limit=1. A
  -- visible unique exact identifier has score zero and must win, so avoid
  -- scanning every name or planning any relationship context in this case.
  if normalized ~ '^[0-9]{8}$' and result_limit = 1
     and (entity_type_filter is null or entity_type_filter = 'Company') then
    return query
    select entity.id, entity.entity_type, entity.canonical_name, entity.display_name,
           entity.identity_status, identifier.value,
           '統一編號 / Company ID ' || identifier.value, 'identifier_exact'::text
      from public.entity_public_identifiers identifier
      join public.entities entity on entity.id = identifier.entity_id
     where identifier.namespace = 'tw:uniform_number'
       and identifier.value = normalized
       and entity.publication_status = 'published'
       and entity.entity_type = 'Company'
     order by entity.display_name, entity.id
     limit 1;
    if found then return; end if;
  end if;

  escaped := replace(normalized, '\', '\\');
  escaped := replace(escaped, '%', '\%');
  escaped := replace(escaped, '_', '\_');

  return query
  with matches as (
    -- Contains already includes exact and prefix. Read once, retain the same
    -- score ordering and best term per entity as the former three UNION scans.
    select term.entity_id,
           (case when term.normalized_term = normalized then 10
                 when term.normalized_term like escaped || '%' escape '\' then 20
                 else 30 end
            + case term.term_kind when 'display' then 0 when 'canonical' then 1 else 2 end) as score
      from public.entity_search_terms term
      join public.entities entity on entity.id = term.entity_id
     where term.normalized_term like '%' || escaped || '%' escape '\'
       and entity.publication_status = 'published'
       and (entity_type_filter is null or entity.entity_type = entity_type_filter)
    union all
    select identifier.entity_id, 0
      from public.entity_public_identifiers identifier
      join public.entities entity on entity.id = identifier.entity_id
     where normalized ~ '^[0-9]{8}$'
       and identifier.namespace = 'tw:uniform_number'
       and identifier.value = normalized
       and entity.publication_status = 'published'
       and (entity_type_filter is null or entity_type_filter = 'Company')
  ), ranked as (
    select match.entity_id, min(match.score) as score
      from matches match group by match.entity_id
  ), selected as materialized (
    -- Bound expensive relationship/evidence RLS to the actual result page.
    -- UUID breaks name ties deterministically; no arbitrary candidate cutoff.
    select entity.id, entity.entity_type, entity.canonical_name,
           entity.display_name, entity.identity_status, ranked.score
      from ranked join public.entities entity on entity.id = ranked.entity_id
     where entity.publication_status = 'published'
     order by ranked.score, entity.display_name, entity.id
     limit result_limit
  )
  select entity.id, entity.entity_type, entity.canonical_name, entity.display_name,
         entity.identity_status, identifier.value,
         case when entity.entity_type = 'Company' and identifier.value is not null
              then '統一編號 / Company ID ' || identifier.value
              else relationship_context.label end,
         case when entity.score = 0 then 'identifier_exact'
              when entity.score < 20 then 'name_exact'
              when entity.score < 30 then 'name_prefix'
              else 'name_contains' end
    from selected entity
    left join public.entity_public_identifiers identifier
      on identifier.entity_id = entity.id and identifier.namespace = 'tw:uniform_number'
    left join lateral (
      select concat_ws(' · ', nullif(relationship.source_role, ''), target.display_name) as label
        from public.relationships relationship
        join public.entities target on target.id = relationship.target_entity_id
       where relationship.source_entity_id = entity.id
         and relationship.status = 'published'
         and target.publication_status = 'published'
         and (entity.entity_type <> 'Company' or identifier.value is null)
       order by relationship.observed_at desc, relationship.id
       limit 1
    ) relationship_context on true
   order by entity.score, entity.display_name, entity.id;
end $$;

comment on function public.search_entities(text,text,integer) is
  'Bounded NFKC public search: set-based RLS, one term scan, ranked page before context; caller RLS and exact/prefix/contains ordering retained.';
revoke all on function public.search_entities(text,text,integer) from public;
grant execute on function public.search_entities(text,text,integer)
  to anon, authenticated, service_role;
