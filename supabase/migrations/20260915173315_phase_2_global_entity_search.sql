-- Phase 2 keeps the existing RPC signature and response columns. Search terms
-- use Unicode NFKC so full-width company numbers and compatibility characters
-- resolve consistently across Company, Person, Politician and Agency entities.

create or replace function tei_private.refresh_entity_search(requested_entity_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  delete from public.entity_search_terms where entity_id = requested_entity_id;
  delete from public.entity_public_identifiers where entity_id = requested_entity_id;

  insert into public.entity_search_terms(entity_id, normalized_term, display_term, term_kind)
  select entity.id,
         lower(normalize(btrim(term.value), NFKC)),
         btrim(term.value),
         term.kind
    from public.entities entity
    cross join lateral (values
      (entity.display_name, 'display'),
      (entity.canonical_name, 'canonical')
    ) as term(value, kind)
   where entity.id = requested_entity_id
     and entity.publication_status = 'published'
  on conflict do nothing;

  insert into public.entity_search_terms(entity_id, normalized_term, display_term, term_kind)
  select entity.id,
         lower(normalize(btrim(alias.alias), NFKC)),
         btrim(alias.alias),
         'alias'
    from public.entities entity
    join public.entity_aliases alias on alias.entity_id = entity.id
   where entity.id = requested_entity_id
     and entity.publication_status = 'published'
  on conflict do nothing;

  insert into public.entity_public_identifiers(entity_id, namespace, value)
  select entity.id, identifier.namespace, identifier.value
    from public.entities entity
    join public.entity_identifiers identifier on identifier.entity_id = entity.id
   where entity.id = requested_entity_id
     and entity.publication_status = 'published'
     and entity.entity_type = 'Company'
     and identifier.namespace = 'tw:uniform_number'
     and identifier.value ~ '^[0-9]{8}$'
  on conflict do nothing;
end $$;

do $$
declare entity_row record;
begin
  for entity_row in select id from public.entities loop
    perform tei_private.refresh_entity_search(entity_row.id);
  end loop;
end $$;

alter table public.entity_search_terms
  add constraint entity_search_terms_nfkc
  check (normalized_term = lower(normalize(btrim(normalized_term), NFKC)))
  not valid;
alter table public.entity_search_terms validate constraint entity_search_terms_nfkc;

create or replace function public.search_entities(
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
security invoker
set search_path = ''
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

  escaped := replace(normalized, '\', '\\');
  escaped := replace(escaped, '%', '\%');
  escaped := replace(escaped, '_', '\_');

  return query
  with matches as (
    select term.entity_id,
           case term.term_kind when 'display' then 10 when 'canonical' then 11 else 12 end as score
      from public.entity_search_terms term
      join public.entities entity on entity.id = term.entity_id
     where term.normalized_term = normalized
       and entity.publication_status = 'published'
       and (entity_type_filter is null or entity.entity_type = entity_type_filter)
    union all
    select term.entity_id,
           case term.term_kind when 'display' then 20 when 'canonical' then 21 else 22 end
      from public.entity_search_terms term
      join public.entities entity on entity.id = term.entity_id
     where term.normalized_term like escaped || '%' escape '\'
       and entity.publication_status = 'published'
       and (entity_type_filter is null or entity.entity_type = entity_type_filter)
    union all
    select term.entity_id,
           case term.term_kind when 'display' then 30 when 'canonical' then 31 else 32 end
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
      from matches match
     group by match.entity_id
  )
  select entity.id,
         entity.entity_type,
         entity.canonical_name,
         entity.display_name,
         entity.identity_status,
         identifier.value,
         case when entity.entity_type = 'Company' and identifier.value is not null
              then '統一編號 / Company ID ' || identifier.value
              else relationship_context.label end,
         case when ranked.score = 0 then 'identifier_exact'
              when ranked.score < 20 then 'name_exact'
              when ranked.score < 30 then 'name_prefix'
              else 'name_contains' end
    from ranked
    join public.entities entity on entity.id = ranked.entity_id
    left join public.entity_public_identifiers identifier
      on identifier.entity_id = entity.id and identifier.namespace = 'tw:uniform_number'
    left join lateral (
      select concat_ws(' · ', nullif(relationship.source_role, ''), target.display_name) as label
        from public.relationships relationship
        join public.entities target on target.id = relationship.target_entity_id
       where relationship.source_entity_id = entity.id
         and relationship.status = 'published'
         and target.publication_status = 'published'
       order by relationship.observed_at desc, relationship.id
       limit 1
    ) relationship_context on true
   where entity.publication_status = 'published'
   order by ranked.score, entity.display_name, entity.id
   limit result_limit;
end $$;

comment on function public.search_entities(text,text,integer) is
  'Bounded NFKC-normalized global search across published Entity types; identifiers are limited to the public company-number projection.';
revoke all on function public.search_entities(text,text,integer) from public;
grant execute on function public.search_entities(text,text,integer)
  to anon, authenticated, service_role;
