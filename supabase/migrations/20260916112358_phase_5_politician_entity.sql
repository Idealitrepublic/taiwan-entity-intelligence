-- Phase 5 is additive: a politician remains a canonical Entity. Terms are
-- source-backed attributes; party, committee and bill links remain Relationships.
create table public.politician_terms (
  id uuid primary key default gen_random_uuid(),
  politician_entity_id uuid not null references public.entities(id),
  term_number smallint not null check (term_number between 1 and 99),
  constituency text not null check (length(btrim(constituency)) between 1 and 200),
  constituency_type text not null default 'unknown'
    check (constituency_type in ('district','proportional','indigenous','unknown')),
  party_entity_id uuid references public.entities(id),
  start_date date not null,
  end_date date,
  primary_evidence_id uuid not null references public.evidence_records(id),
  publication_status text not null default 'draft'
    check (publication_status in ('draft','published','withdrawn')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (end_date is null or end_date >= start_date),
  unique (politician_entity_id, term_number, start_date)
);

create index politician_terms_entity_period_idx
  on public.politician_terms (politician_entity_id, term_number desc, start_date desc, id);
create index politician_terms_party_idx on public.politician_terms (party_entity_id)
  where party_entity_id is not null;
create index politician_terms_evidence_idx on public.politician_terms (primary_evidence_id);

create trigger politician_terms_updated before update on public.politician_terms
for each row execute function tei_private.touch_updated_at();

create function tei_private.validate_politician_term() returns trigger
language plpgsql set search_path = '' as $$
declare politician public.entities; party public.entities; proof public.evidence_records;
begin
  if new.publication_status <> 'published' then return new; end if;
  select * into politician from public.entities where id = new.politician_entity_id for share;
  if politician.entity_type <> 'Politician' or politician.publication_status <> 'published' then
    raise exception 'Published term requires a published Politician entity' using errcode='23514';
  end if;
  if new.party_entity_id is not null then
    select * into party from public.entities where id = new.party_entity_id for share;
    if party.entity_type <> 'PoliticalParty' or party.publication_status <> 'published' then
      raise exception 'Published term party must be a published PoliticalParty entity' using errcode='23514';
    end if;
  end if;
  select * into proof from public.evidence_records where id = new.primary_evidence_id for share;
  if proof.status <> 'active' or proof.publication_status <> 'published' then
    raise exception 'Published term requires active published Evidence' using errcode='23514';
  end if;
  return new;
end $$;

create constraint trigger politician_terms_valid
after insert or update on public.politician_terms
deferrable initially deferred for each row execute function tei_private.validate_politician_term();

alter table public.politician_terms enable row level security;
revoke all on table public.politician_terms from public, anon, authenticated;
grant select, insert, update, delete on table public.politician_terms to service_role;
grant select on table public.politician_terms to anon, authenticated;
create policy service_access on public.politician_terms for all to service_role
  using (true) with check (true);
create policy published_politician_terms on public.politician_terms for select to anon, authenticated
  using (
    publication_status = 'published'
    and exists (
      select 1 from public.entities e
      where e.id = politician_entity_id
        and e.entity_type = 'Politician'
        and e.publication_status = 'published'
    )
    and (party_entity_id is null or exists (
      select 1 from public.entities p
      where p.id = party_entity_id
        and p.entity_type = 'PoliticalParty'
        and p.publication_status = 'published'
    ))
    and exists (
      select 1 from public.evidence_records ev
      where ev.id = primary_evidence_id
        and ev.status = 'active'
        and ev.publication_status = 'published'
    )
  );
