-- A source row is not an official person identifier. Reviewed crosswalks keep
-- the official-source chain separate from the exact LY identifier it resolves.
create table public.political_identity_crosswalks (
  id uuid primary key,
  source_kind text not null check (source_kind in ('contribution','asset')),
  source_record_id text not null,
  source_subject_name text not null,
  source_evidence_id uuid not null references public.evidence_records(id),
  politician_entity_id uuid not null references public.entities(id),
  official_legislator_number text not null check (official_legislator_number ~ '^[0-9]{5}$'),
  term_number smallint not null check (term_number between 1 and 99),
  constituency text not null,
  master_evidence_id uuid not null references public.evidence_records(id),
  company_entity_id uuid references public.entities(id),
  company_uniform_number text check (company_uniform_number ~ '^[0-9]{8}$'),
  independent_official_url text not null check (independent_official_url like 'https://%'),
  review_basis text not null check (review_basis in ('election_term_constituency','office_term_date')),
  reviewed_by text not null check (length(btrim(reviewed_by)) > 0),
  reviewed_at timestamptz not null,
  status text not null default 'approved' check (status in ('approved','withdrawn')),
  unique(source_kind,source_record_id),
  check ((company_entity_id is null) = (company_uniform_number is null)),
  check ((source_kind = 'contribution' and company_entity_id is not null and
          review_basis = 'election_term_constituency') or
         (source_kind = 'asset' and company_entity_id is null and
          review_basis = 'office_term_date'))
);
create index political_identity_crosswalks_politician_idx
  on public.political_identity_crosswalks(politician_entity_id,source_kind)
  where status = 'approved';
alter table public.political_identity_crosswalks enable row level security;
revoke all on public.political_identity_crosswalks from public, anon, authenticated;
grant select, insert, update on public.political_identity_crosswalks to service_role;

create function tei_private.validate_political_identity_crosswalk() returns trigger
language plpgsql set search_path = '' as $$
declare source_proof public.evidence_records; member public.entities;
  term public.politician_terms; company public.entities;
begin
  if tg_op = 'UPDATE' then
    if old.status <> 'approved' or new.status <> 'withdrawn' or
       (to_jsonb(new) - 'status' - 'reviewed_at') is distinct from
       (to_jsonb(old) - 'status' - 'reviewed_at') then
      raise exception 'Crosswalk is immutable except withdrawal' using errcode='23514';
    end if;
    return new;
  end if;
  select * into source_proof from public.evidence_records where id = new.source_evidence_id;
  select * into member from public.entities where id = new.politician_entity_id;
  select * into term from public.politician_terms
    where politician_entity_id = new.politician_entity_id
      and term_number = new.term_number
      and constituency = new.constituency
      and legislator_number = new.official_legislator_number
      and primary_evidence_id = new.master_evidence_id
      and publication_status = 'published';
  if source_proof.source_record_id is distinct from new.source_record_id or
     source_proof.source_url is null or source_proof.retrieved_at is null or
     member.entity_type <> 'Politician' or member.publication_status <> 'published' or
     member.display_name <> new.source_subject_name or term.id is null or
     not exists (select 1 from public.entity_identifiers i
                 where i.entity_id = new.politician_entity_id
                   and i.namespace = 'tw:legislative_yuan:legislator_number'
                   and i.value = new.official_legislator_number and i.confidence = 'EXACT') then
    raise exception 'Crosswalk lacks source Evidence, exact LY identity or matching term'
      using errcode='23514';
  end if;
  if new.source_kind = 'contribution' then
    select * into company from public.entities where id = new.company_entity_id;
    if source_proof.source_locator->>'candidate_name' <> new.source_subject_name or
       source_proof.source_locator->>'election_area' <> '臺北市' or
       new.constituency not like '臺北市%' or
       source_proof.source_locator->>'election' not like '%113年立法委員選舉%' or
       extract(year from term.start_date) <> 2024 or
       new.independent_official_url not like 'https://web.cec.gov.tw/%' or
       company.entity_type <> 'Company' or company.publication_status <> 'published' or
       source_proof.source_locator->>'donor_uniform_number' <> new.company_uniform_number or
       not exists (select 1 from public.entity_identifiers i
                   where i.entity_id = new.company_entity_id
                     and i.namespace = 'tw:uniform_number'
                     and i.value = new.company_uniform_number and i.confidence = 'EXACT') then
      raise exception 'Contribution crosswalk lacks election, district or exact company evidence'
        using errcode='23514';
    end if;
  else
    if source_proof.source_locator->>'declarant_name' <> new.source_subject_name or
       source_proof.source_locator->>'office' <> '立法委員' or
       (source_proof.source_locator->>'declaration_date')::date < term.start_date or
       (term.end_date is not null and
        (source_proof.source_locator->>'declaration_date')::date > term.end_date) or
       new.independent_official_url not like 'https://www.ly.gov.tw/%' then
      raise exception 'Asset crosswalk lacks office and overlapping term evidence'
        using errcode='23514';
    end if;
  end if;
  return new;
end $$;
create trigger political_identity_crosswalk_validate
  before insert or update on public.political_identity_crosswalks
  for each row execute function tei_private.validate_political_identity_crosswalk();

create function tei_private.require_reviewed_political_crosswalk() returns trigger
language plpgsql set search_path = '' as $$
declare proof public.evidence_records; crosswalk public.political_identity_crosswalks;
  expected_kind text; politician uuid; company uuid;
begin
  if tg_table_name = 'relationships' then
    if new.status <> 'published' or new.relationship_type <> 'POLITICAL_CONTRIBUTION_TO' then
      return null;
    end if;
    expected_kind := 'contribution'; politician := new.target_entity_id;
    company := new.source_entity_id;
  else
    if new.publication_status <> 'published' then return null; end if;
    expected_kind := 'asset'; politician := new.politician_id;
  end if;
  select * into proof from public.evidence_records where id = new.primary_evidence_id;
  if proof.source_locator->>'politician_identifier_origin' is distinct from 'reviewed_crosswalk' then
    return null;
  end if;
  select * into crosswalk from public.political_identity_crosswalks
    where id = (proof.source_locator->>'politician_crosswalk_id')::uuid;
  if crosswalk.id is null or crosswalk.status <> 'approved' or
     crosswalk.source_kind <> expected_kind or
     crosswalk.source_record_id <> proof.source_record_id or
     crosswalk.politician_entity_id <> politician or
     (expected_kind = 'contribution' and crosswalk.company_entity_id <> company) or
     proof.source_locator->>'politician_identifier_value' <>
       crosswalk.official_legislator_number then
    raise exception 'Published political fact lacks an approved source crosswalk'
      using errcode='23514';
  end if;
  return null;
end $$;
create constraint trigger contribution_reviewed_crosswalk_required
  after insert or update on public.relationships deferrable initially deferred
  for each row execute function tei_private.require_reviewed_political_crosswalk();
create constraint trigger asset_reviewed_crosswalk_required
  after insert or update on public.asset_declarations deferrable initially deferred
  for each row execute function tei_private.require_reviewed_political_crosswalk();
