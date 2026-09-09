-- Phase 2 security hardening: public search reads a deliberately safe projection
-- with SECURITY INVOKER. The private identifier registry remains inaccessible.
create table public.entity_search_terms (
  entity_id uuid not null references public.entities(id) on delete cascade,
  normalized_term text not null check (normalized_term = lower(btrim(normalized_term)) and btrim(normalized_term) <> ''),
  display_term text not null check (btrim(display_term) <> ''),
  term_kind text not null check (term_kind in ('display','canonical','alias')),
  primary key (entity_id, normalized_term, term_kind)
);
create index entity_search_terms_prefix_idx
  on public.entity_search_terms (normalized_term text_pattern_ops, entity_id);

create table public.entity_public_identifiers (
  entity_id uuid not null references public.entities(id) on delete cascade,
  namespace text not null check (namespace = 'tw:uniform_number'),
  value text not null check (value ~ '^[0-9]{8}$'),
  primary key (namespace, value),
  unique (entity_id, namespace)
);
create index entity_public_identifiers_entity_idx
  on public.entity_public_identifiers (entity_id);

do $$
begin
  if exists (
    select 1 from pg_opclass c
    join pg_namespace n on n.oid = c.opcnamespace
    where c.opcname = 'gin_trgm_ops'
  ) then
    execute 'create index entity_search_terms_trgm_idx on public.entity_search_terms using gin (normalized_term gin_trgm_ops)';
  end if;
end $$;

alter table public.entity_search_terms enable row level security;
alter table public.entity_public_identifiers enable row level security;
revoke all on public.entity_search_terms, public.entity_public_identifiers
  from public, anon, authenticated;
grant select on public.entity_search_terms, public.entity_public_identifiers
  to anon, authenticated;
grant select, insert, update, delete on public.entity_search_terms,
  public.entity_public_identifiers to service_role;
create policy service_access on public.entity_search_terms for all to service_role
  using (true) with check (true);
create policy service_access on public.entity_public_identifiers for all to service_role
  using (true) with check (true);
create policy published_search_terms on public.entity_search_terms for select to anon, authenticated
  using (exists (select 1 from public.entities e where e.id = entity_id));
create policy published_public_identifiers on public.entity_public_identifiers for select to anon, authenticated
  using (exists (select 1 from public.entities e where e.id = entity_id));

create function tei_private.refresh_entity_search(requested_entity_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  delete from public.entity_search_terms where entity_id = requested_entity_id;
  delete from public.entity_public_identifiers where entity_id = requested_entity_id;

  insert into public.entity_search_terms(entity_id, normalized_term, display_term, term_kind)
  select e.id, lower(btrim(term.value)), btrim(term.value), term.kind
    from public.entities e
    cross join lateral (values
      (e.display_name, 'display'),
      (e.canonical_name, 'canonical')
    ) as term(value, kind)
   where e.id = requested_entity_id and e.publication_status = 'published'
  on conflict do nothing;

  insert into public.entity_search_terms(entity_id, normalized_term, display_term, term_kind)
  select e.id, lower(btrim(a.alias)), btrim(a.alias), 'alias'
    from public.entities e
    join public.entity_aliases a on a.entity_id = e.id
   where e.id = requested_entity_id and e.publication_status = 'published'
  on conflict do nothing;

  insert into public.entity_public_identifiers(entity_id, namespace, value)
  select e.id, i.namespace, i.value
    from public.entities e
    join public.entity_identifiers i on i.entity_id = e.id
   where e.id = requested_entity_id
     and e.publication_status = 'published'
     and e.entity_type = 'Company'
     and i.namespace = 'tw:uniform_number'
     and i.value ~ '^[0-9]{8}$'
  on conflict do nothing;
end $$;

create function tei_private.refresh_entity_search_trigger()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op <> 'INSERT' then
    perform tei_private.refresh_entity_search(old.entity_id);
  end if;
  if tg_op <> 'DELETE' then
    perform tei_private.refresh_entity_search(new.entity_id);
  end if;
  return coalesce(new, old);
end $$;

create function tei_private.refresh_entity_row_search_trigger()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform tei_private.refresh_entity_search(coalesce(new.id, old.id));
  return coalesce(new, old);
end $$;

create trigger entity_search_refresh
after insert or update of canonical_name, display_name, publication_status or delete
on public.entities for each row
execute function tei_private.refresh_entity_row_search_trigger();
create trigger entity_alias_search_refresh
after insert or update or delete on public.entity_aliases for each row
execute function tei_private.refresh_entity_search_trigger();
create trigger entity_identifier_search_refresh
after insert or update or delete on public.entity_identifiers for each row
execute function tei_private.refresh_entity_search_trigger();

do $$ declare entity_row record;
begin
  for entity_row in select id from public.entities loop
    perform tei_private.refresh_entity_search(entity_row.id);
  end loop;
end $$;

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
  escaped := replace(normalized, '\', '\\');
  escaped := replace(escaped, '%', '\%');
  escaped := replace(escaped, '_', '\_');

  return query
  with matches as (
    select t.entity_id,
           case t.term_kind when 'display' then 10 when 'canonical' then 11 else 12 end as score
      from public.entity_search_terms t
      join public.entities e on e.id = t.entity_id
     where t.normalized_term = normalized
       and (entity_type_filter is null or e.entity_type = entity_type_filter)
    union all
    select t.entity_id,
           case t.term_kind when 'display' then 20 when 'canonical' then 21 else 22 end
      from public.entity_search_terms t
      join public.entities e on e.id = t.entity_id
     where t.normalized_term like escaped || '%' escape '\'
       and (entity_type_filter is null or e.entity_type = entity_type_filter)
    union all
    select t.entity_id,
           case t.term_kind when 'display' then 30 when 'canonical' then 31 else 32 end
      from public.entity_search_terms t
      join public.entities e on e.id = t.entity_id
     where t.normalized_term like '%' || escaped || '%' escape '\'
       and (entity_type_filter is null or e.entity_type = entity_type_filter)
    union all
    select i.entity_id, 0
      from public.entity_public_identifiers i
      join public.entities e on e.id = i.entity_id
     where normalized ~ '^[0-9]{8}$'
       and i.namespace = 'tw:uniform_number'
       and i.value = normalized
       and (entity_type_filter is null or entity_type_filter = 'Company')
  ), ranked as (
    select m.entity_id, min(m.score) as score
      from matches m group by m.entity_id
  )
  select e.id,
         e.entity_type,
         e.canonical_name,
         e.display_name,
         e.identity_status,
         identifier.value,
         case when e.entity_type = 'Company' and identifier.value is not null
              then '統一編號 / Company ID ' || identifier.value
              else relationship_context.label end,
         case when r.score = 0 then 'identifier_exact'
              when r.score < 20 then 'name_exact'
              when r.score < 30 then 'name_prefix'
              else 'name_contains' end
    from ranked r
    join public.entities e on e.id = r.entity_id
    left join public.entity_public_identifiers identifier
      on identifier.entity_id = e.id and identifier.namespace = 'tw:uniform_number'
    left join lateral (
      select concat_ws(' · ', nullif(rel.source_role, ''), target.display_name) as label
        from public.relationships rel
        join public.entities target on target.id = rel.target_entity_id
       where rel.source_entity_id = e.id and rel.status = 'published'
       order by rel.observed_at desc, rel.id limit 1
    ) relationship_context on true
   order by r.score, e.display_name, e.id
   limit result_limit;
end $$;

revoke all on function public.search_entities(text,text,integer) from public;
grant execute on function public.search_entities(text,text,integer)
  to anon, authenticated, service_role;
revoke all on function tei_private.refresh_entity_search(uuid),
  tei_private.refresh_entity_search_trigger(),
  tei_private.refresh_entity_row_search_trigger()
  from public, anon, authenticated;
grant execute on function tei_private.refresh_entity_search(uuid),
  tei_private.refresh_entity_search_trigger(),
  tei_private.refresh_entity_row_search_trigger()
  to service_role;

drop index if exists public.entities_published_display_prefix_idx;
drop index if exists public.entities_published_canonical_prefix_idx;
drop index if exists public.entity_aliases_prefix_idx;
drop index if exists public.entities_published_display_trgm_idx;
drop index if exists public.entities_published_canonical_trgm_idx;
drop index if exists public.entity_aliases_trgm_idx;
