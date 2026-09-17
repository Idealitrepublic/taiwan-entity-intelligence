-- Phase 10 adds private Entity watchlists and in-dashboard alert events.
-- Detection is bounded, evidence-backed, owner-scoped, and never sends mail
-- or an external notification.
create table public.watchlist_entries (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  entity_id uuid not null references public.entities(id),
  created_at timestamptz not null default now(),
  unique (owner_user_id, entity_id),
  unique (id, owner_user_id)
);

create table public.watchlist_events (
  id uuid primary key default gen_random_uuid(),
  watchlist_entry_id uuid not null,
  owner_user_id uuid not null default auth.uid(),
  entity_id uuid not null references public.entities(id),
  event_type text not null check (event_type in (
    'PROCUREMENT','JUDGMENT','PENALTY','OFFICER',
    'POLITICAL_CONTRIBUTION','ASSET_DECLARATION')),
  source_kind text not null check (source_kind in ('RELATIONSHIP','ASSET_DECLARATION')),
  relationship_id uuid references public.relationships(id),
  asset_declaration_id uuid references public.asset_declarations(id),
  evidence_id uuid not null references public.evidence_records(id),
  event_observed_at timestamptz not null,
  first_seen_at timestamptz not null default now(),
  read_at timestamptz,
  constraint watchlist_events_entry_owner_fkey
    foreign key (watchlist_entry_id, owner_user_id)
    references public.watchlist_entries(id, owner_user_id) on delete cascade,
  unique (watchlist_entry_id, source_kind, relationship_id),
  unique (watchlist_entry_id, source_kind, asset_declaration_id),
  check (read_at is null or read_at >= first_seen_at),
  check (
    (source_kind = 'RELATIONSHIP' and relationship_id is not null
      and asset_declaration_id is null)
    or (source_kind = 'ASSET_DECLARATION' and asset_declaration_id is not null
      and relationship_id is null)
  )
);

create index watchlist_entries_owner_created_idx
  on public.watchlist_entries (owner_user_id, created_at desc, id);
create index watchlist_entries_entity_idx
  on public.watchlist_entries (entity_id, id);
create index watchlist_events_owner_unread_idx
  on public.watchlist_events (owner_user_id, first_seen_at desc, id)
  where read_at is null;
create index watchlist_events_owner_seen_idx
  on public.watchlist_events (owner_user_id, first_seen_at desc, id);
create index watchlist_events_entry_seen_idx
  on public.watchlist_events (watchlist_entry_id, first_seen_at desc, id);
create index watchlist_events_evidence_idx
  on public.watchlist_events (evidence_id, id);
create index watchlist_events_relationship_idx
  on public.watchlist_events (relationship_id, id) where relationship_id is not null;
create index watchlist_events_asset_idx
  on public.watchlist_events (asset_declaration_id, id)
  where asset_declaration_id is not null;

create function tei_private.validate_watchlist_entry() returns trigger
language plpgsql set search_path = '' as $$
declare watched public.entities;
begin
  select * into watched from public.entities where id = new.entity_id;
  if watched.id is null or watched.publication_status <> 'published'
     or watched.entity_type not in ('Company','Person','Politician') then
    raise exception 'Watchlist supports published Company, Person, or Politician entities'
      using errcode = '23514';
  end if;
  return new;
end $$;

create trigger watchlist_entries_valid before insert or update on public.watchlist_entries
for each row execute function tei_private.validate_watchlist_entry();

create function tei_private.validate_watchlist_event() returns trigger
language plpgsql set search_path = '' as $$
declare watched public.watchlist_entries; relation public.relationships;
  asset public.asset_declarations; proof public.evidence_records; expected_type text;
begin
  select * into watched from public.watchlist_entries
  where id = new.watchlist_entry_id and owner_user_id = new.owner_user_id;
  if watched.id is null or watched.entity_id <> new.entity_id then
    raise exception 'Watchlist event owner or entity mismatch' using errcode = '23514';
  end if;
  select * into proof from public.evidence_records where id = new.evidence_id;
  if proof.id is null or proof.status <> 'active'
     or proof.publication_status <> 'published' or proof.retrieved_at < watched.created_at then
    raise exception 'Watchlist event requires new active published Evidence'
      using errcode = '23514';
  end if;
  if new.source_kind = 'RELATIONSHIP' then
    select * into relation from public.relationships where id = new.relationship_id;
    expected_type := case
      when relation.relationship_type = 'CONTRACT_WITH' then 'PROCUREMENT'
      when relation.relationship_type = 'RELATED_TO_JUDGMENT' then 'JUDGMENT'
      when relation.relationship_type = 'RELATED_TO_PENALTY' then 'PENALTY'
      when relation.relationship_type in ('DIRECTOR_OF','OFFICER_OF') then 'OFFICER'
      when relation.relationship_type = 'POLITICAL_CONTRIBUTION_TO'
        then 'POLITICAL_CONTRIBUTION'
      else null end;
    if relation.id is null or relation.status <> 'published'
       or relation.primary_evidence_id <> new.evidence_id
       or new.entity_id not in (relation.source_entity_id, relation.target_entity_id)
       or expected_type is distinct from new.event_type
       or new.event_observed_at <> relation.observed_at then
      raise exception 'Invalid relationship watchlist event' using errcode = '23514';
    end if;
  else
    select * into asset from public.asset_declarations where id = new.asset_declaration_id;
    if asset.id is null or asset.publication_status <> 'published'
       or asset.primary_evidence_id <> new.evidence_id
       or (new.entity_id <> asset.politician_id
         and new.entity_id is distinct from asset.company_entity_id)
       or new.event_type <> 'ASSET_DECLARATION'
       or new.event_observed_at <> proof.observed_at then
      raise exception 'Invalid asset declaration watchlist event' using errcode = '23514';
    end if;
  end if;
  return new;
end $$;

create trigger watchlist_events_valid before insert on public.watchlist_events
for each row execute function tei_private.validate_watchlist_event();

create function tei_private.keep_watchlist_event_identity() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.id <> old.id or new.watchlist_entry_id <> old.watchlist_entry_id
     or new.owner_user_id <> old.owner_user_id or new.entity_id <> old.entity_id
     or new.event_type <> old.event_type or new.source_kind <> old.source_kind
     or new.relationship_id is distinct from old.relationship_id
     or new.asset_declaration_id is distinct from old.asset_declaration_id
     or new.evidence_id <> old.evidence_id
     or new.event_observed_at <> old.event_observed_at
     or new.first_seen_at <> old.first_seen_at then
    raise exception 'Watchlist event identity is immutable' using errcode = '23514';
  end if;
  return new;
end $$;

create trigger watchlist_events_identity before update on public.watchlist_events
for each row execute function tei_private.keep_watchlist_event_identity();

alter table public.watchlist_entries enable row level security;
alter table public.watchlist_events enable row level security;
revoke all on table public.watchlist_entries from public, anon, authenticated;
revoke all on table public.watchlist_events from public, anon, authenticated;
grant select, insert, delete on table public.watchlist_entries to authenticated;
grant select, insert, update on table public.watchlist_events to authenticated;

create policy watchlist_entries_owner_select on public.watchlist_entries
for select to authenticated using ((select auth.uid()) = owner_user_id);
create policy watchlist_entries_owner_insert on public.watchlist_entries
for insert to authenticated with check ((select auth.uid()) = owner_user_id);
create policy watchlist_entries_owner_delete on public.watchlist_entries
for delete to authenticated using ((select auth.uid()) = owner_user_id);
create policy watchlist_events_owner_select on public.watchlist_events
for select to authenticated using ((select auth.uid()) = owner_user_id);
create policy watchlist_events_owner_insert on public.watchlist_events
for insert to authenticated with check ((select auth.uid()) = owner_user_id);
create policy watchlist_events_owner_update on public.watchlist_events
for update to authenticated using ((select auth.uid()) = owner_user_id)
with check ((select auth.uid()) = owner_user_id);

create function public.sync_watchlist_events(scan_limit integer default 25)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare inserted_count integer := 0; watched_count integer := 0;
begin
  if (select auth.uid()) is null then
    raise exception 'Authentication required' using errcode = '42501';
  end if;
  if scan_limit < 1 or scan_limit > 25 then
    raise exception 'scan_limit must be between 1 and 25' using errcode = '22023';
  end if;
  with watched as materialized (
    select w.id, w.owner_user_id, w.entity_id, w.created_at
    from public.watchlist_entries w
    where w.owner_user_id = (select auth.uid())
    order by w.created_at, w.id limit scan_limit
  ), candidates as (
    select w.id watchlist_entry_id, w.owner_user_id, w.entity_id,
      case
        when r.relationship_type = 'CONTRACT_WITH' then 'PROCUREMENT'
        when r.relationship_type = 'RELATED_TO_JUDGMENT' then 'JUDGMENT'
        when r.relationship_type = 'RELATED_TO_PENALTY' then 'PENALTY'
        when r.relationship_type in ('DIRECTOR_OF','OFFICER_OF') then 'OFFICER'
        when r.relationship_type = 'POLITICAL_CONTRIBUTION_TO'
          then 'POLITICAL_CONTRIBUTION'
      end event_type,
      'RELATIONSHIP'::text source_kind, r.id relationship_id,
      null::uuid asset_declaration_id, r.primary_evidence_id evidence_id,
      r.observed_at event_observed_at
    from watched w join public.relationships r
      on w.entity_id in (r.source_entity_id, r.target_entity_id)
    join public.evidence_records e on e.id = r.primary_evidence_id
    where r.status = 'published'
      and r.relationship_type in ('CONTRACT_WITH','RELATED_TO_JUDGMENT',
        'RELATED_TO_PENALTY','DIRECTOR_OF','OFFICER_OF','POLITICAL_CONTRIBUTION_TO')
      and e.status = 'active' and e.publication_status = 'published'
      and e.retrieved_at >= w.created_at
    union all
    select w.id, w.owner_user_id, w.entity_id, 'ASSET_DECLARATION',
      'ASSET_DECLARATION', null::uuid, a.id, a.primary_evidence_id, e.observed_at
    from watched w join public.asset_declarations a
      on w.entity_id = a.politician_id or w.entity_id = a.company_entity_id
    join public.evidence_records e on e.id = a.primary_evidence_id
    where a.publication_status = 'published' and e.status = 'active'
      and e.publication_status = 'published' and e.retrieved_at >= w.created_at
  ), inserted as (
    insert into public.watchlist_events
      (watchlist_entry_id,owner_user_id,entity_id,event_type,source_kind,
       relationship_id,asset_declaration_id,evidence_id,event_observed_at)
    select watchlist_entry_id,owner_user_id,entity_id,event_type,source_kind,
      relationship_id,asset_declaration_id,evidence_id,event_observed_at
    from candidates order by event_observed_at desc limit 500
    on conflict do nothing returning id
  ) select count(*) into inserted_count from inserted;
  select count(*) into watched_count from public.watchlist_entries
  where owner_user_id = (select auth.uid());
  return jsonb_build_object('inserted', inserted_count,
    'watched', least(watched_count, scan_limit),
    'watchlist_has_more', watched_count > scan_limit, 'event_cap', 500);
end $$;

revoke execute on function public.sync_watchlist_events(integer)
from public, anon, service_role;
grant execute on function public.sync_watchlist_events(integer) to authenticated;
