-- Phase 2: bounded global search over published entities. This migration does not
-- expose entity_identifiers; only the public Taiwan company number is projected.
create index entities_published_display_prefix_idx
  on public.entities (lower(display_name) text_pattern_ops, entity_type, id)
  where publication_status = 'published';
create index entities_published_canonical_prefix_idx
  on public.entities (lower(canonical_name) text_pattern_ops, entity_type, id)
  where publication_status = 'published';
create index entity_aliases_prefix_idx
  on public.entity_aliases (lower(alias) text_pattern_ops, entity_id);

-- Production already has pg_trgm. Keep the migration portable for local PGlite
-- by adding contains-search indexes only when its operator class is available.
do $$
begin
  if exists (
    select 1 from pg_opclass c
    join pg_namespace n on n.oid = c.opcnamespace
    where c.opcname = 'gin_trgm_ops'
  ) then
    execute 'create index entities_published_display_trgm_idx on public.entities using gin (lower(display_name) gin_trgm_ops) where publication_status = ''published''';
    execute 'create index entities_published_canonical_trgm_idx on public.entities using gin (lower(canonical_name) gin_trgm_ops) where publication_status = ''published''';
    execute 'create index entity_aliases_trgm_idx on public.entity_aliases using gin (lower(alias) gin_trgm_ops)';
  end if;
end $$;

create function public.search_entities(
  search_query text,
  entity_type_filter text default null,
  result_limit integer default 20
) returns table (
  entity_id uuid,
  entity_type text,
  canonical_name text,
  display_name text,
  identity_status text,
  public_identifier text,
  context_label text,
  match_type text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  normalized text := lower(btrim(search_query));
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
    select 1 from public.entity_types t where t.code = entity_type_filter
  ) then
    raise exception 'Unknown entity type' using errcode = '22023';
  end if;

  -- Escape LIKE metacharacters so user input is always literal text.
  escaped := replace(normalized, '\', '\\');
  escaped := replace(escaped, '%', '\%');
  escaped := replace(escaped, '_', '\_');

  return query
  with matches as (
    select e.id, 10 as score
      from public.entities e
     where e.publication_status = 'published'
       and (entity_type_filter is null or e.entity_type = entity_type_filter)
       and lower(e.display_name) = normalized
    union all
    select e.id, 11
      from public.entities e
     where e.publication_status = 'published'
       and (entity_type_filter is null or e.entity_type = entity_type_filter)
       and lower(e.canonical_name) = normalized
    union all
    select e.id, 20
      from public.entities e
     where e.publication_status = 'published'
       and (entity_type_filter is null or e.entity_type = entity_type_filter)
       and lower(e.display_name) like escaped || '%' escape '\'
    union all
    select e.id, 21
      from public.entities e
     where e.publication_status = 'published'
       and (entity_type_filter is null or e.entity_type = entity_type_filter)
       and lower(e.canonical_name) like escaped || '%' escape '\'
    union all
    select e.id, 30
      from public.entities e
     where e.publication_status = 'published'
       and (entity_type_filter is null or e.entity_type = entity_type_filter)
       and lower(e.display_name) like '%' || escaped || '%' escape '\'
    union all
    select e.id, 31
      from public.entities e
     where e.publication_status = 'published'
       and (entity_type_filter is null or e.entity_type = entity_type_filter)
       and lower(e.canonical_name) like '%' || escaped || '%' escape '\'
    union all
    select a.entity_id, case when lower(a.alias) = normalized then 12
                             when lower(a.alias) like escaped || '%' escape '\' then 22
                             else 32 end
      from public.entity_aliases a
      join public.entities e on e.id = a.entity_id
     where e.publication_status = 'published'
       and (entity_type_filter is null or e.entity_type = entity_type_filter)
       and lower(a.alias) like '%' || escaped || '%' escape '\'
    union all
    select i.entity_id, 0
      from public.entity_identifiers i
      join public.entities e on e.id = i.entity_id
     where normalized ~ '^[0-9]{8}$'
       and i.namespace = 'tw:uniform_number'
       and i.value = normalized
       and e.entity_type = 'Company'
       and e.publication_status = 'published'
       and (entity_type_filter is null or entity_type_filter = 'Company')
  ), ranked as (
    select m.id, min(m.score) as score
      from matches m
     group by m.id
  )
  select e.id,
         e.entity_type,
         e.canonical_name,
         e.display_name,
         e.identity_status,
         identifier.value,
         case
           when e.entity_type = 'Company' and identifier.value is not null
             then '統一編號 / Company ID ' || identifier.value
           else relationship_context.label
         end,
         case when r.score = 0 then 'identifier_exact'
              when r.score < 20 then 'name_exact'
              when r.score < 30 then 'name_prefix'
              else 'name_contains' end
    from ranked r
    join public.entities e on e.id = r.id
    left join lateral (
      select i.value
        from public.entity_identifiers i
       where i.entity_id = e.id and i.namespace = 'tw:uniform_number'
       order by i.value
       limit 1
    ) identifier on true
    left join lateral (
      select concat_ws(' · ', nullif(rel.source_role, ''), target.display_name) as label
        from public.relationships rel
        join public.entities target on target.id = rel.target_entity_id
       where rel.source_entity_id = e.id
         and rel.status = 'published'
         and target.publication_status = 'published'
       order by rel.observed_at desc, rel.id
       limit 1
    ) relationship_context on true
   order by r.score, e.display_name, e.id
   limit result_limit;
end $$;

comment on function public.search_entities(text,text,integer) is
  'Bounded public search. Returns published entity metadata, a public company number, and a published relationship context only.';
revoke all on function public.search_entities(text,text,integer) from public;
grant execute on function public.search_entities(text,text,integer) to anon, authenticated, service_role;
