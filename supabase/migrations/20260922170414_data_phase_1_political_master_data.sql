-- DATA Phase 1: additive Political Master Data ingestion.
-- The public read contract remains backward compatible; all ingestion lands as
-- draft and requires a separate review/publication action.
alter table public.politician_terms
  add column legislator_number text
    check (legislator_number is null or legislator_number ~ '^[0-9]{4,8}$'),
  add column source_name text
    check (source_name is null or btrim(source_name) <> ''),
  add column source_record_id text
    check (source_record_id is null or btrim(source_record_id) <> '');

create unique index politician_terms_source_record_idx
  on public.politician_terms (source_name, source_record_id)
  where source_name is not null and source_record_id is not null;
create index politician_terms_legislator_number_idx
  on public.politician_terms (legislator_number, term_number, id)
  where legislator_number is not null;

create or replace function tei_private.validate_politician_term() returns trigger
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
  if new.legislator_number is not null and not exists (
    select 1 from public.entity_identifiers identifier
    where identifier.entity_id = new.politician_entity_id
      and identifier.namespace = 'tw:legislative_yuan:legislator_number'
      and identifier.value = new.legislator_number
  ) then
    raise exception 'Published term legislator number must exactly identify its Politician'
      using errcode='23514';
  end if;
  select * into proof from public.evidence_records where id = new.primary_evidence_id for share;
  if proof.status <> 'active' or proof.publication_status <> 'published' then
    raise exception 'Published term requires active published Evidence' using errcode='23514';
  end if;
  return new;
end $$;

create function public.tei_ingest_political_master_bundle(bundle jsonb) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare item jsonb; existing public.politician_terms; core_result jsonb; n integer := 0;
begin
  if jsonb_typeof(bundle) <> 'object' or octet_length(bundle::text) > 1048576 then
    raise exception 'Invalid or oversized political master bundle' using errcode='22023';
  end if;
  if jsonb_array_length(coalesce(bundle->'politician_terms','[]')) > 200 then
    raise exception 'Political master bundle exceeds term limit' using errcode='22023';
  end if;

  core_result := public.tei_ingest_bundle(bundle - 'politician_terms');
  for item in select value from jsonb_array_elements(coalesce(bundle->'politician_terms','[]')) loop
    if coalesce(item->>'publication_status','draft') <> 'draft' then
      raise exception 'Political master ingestion accepts draft terms only' using errcode='22023';
    end if;
    if nullif(btrim(item->>'source_name'),'') is null
       or nullif(btrim(item->>'source_record_id'),'') is null then
      raise exception 'Political master term requires source identity' using errcode='22023';
    end if;

    select * into existing from public.politician_terms where id = (item->>'id')::uuid;
    if found and (
      existing.politician_entity_id <> (item->>'politician_entity_id')::uuid
      or existing.term_number <> (item->>'term_number')::smallint
      or existing.source_name is distinct from item->>'source_name'
      or existing.source_record_id is distinct from item->>'source_record_id'
    ) then
      raise exception 'Political master term identity collision' using errcode='23505';
    end if;
    if found and existing.publication_status = 'published' and (
      existing.constituency <> item->>'constituency'
      or existing.constituency_type <> coalesce(item->>'constituency_type','unknown')
      or existing.party_entity_id is distinct from (item->>'party_entity_id')::uuid
      or existing.legislator_number is distinct from item->>'legislator_number'
      or existing.start_date <> (item->>'start_date')::date
      or existing.end_date is distinct from (item->>'end_date')::date
      or existing.primary_evidence_id <> (item->>'primary_evidence_id')::uuid
    ) then
      raise exception 'Published political master term requires reviewed correction'
        using errcode='23514';
    end if;

    insert into public.politician_terms(
      id,politician_entity_id,term_number,constituency,constituency_type,
      party_entity_id,legislator_number,start_date,end_date,primary_evidence_id,
      source_name,source_record_id,publication_status)
    values (
      (item->>'id')::uuid,(item->>'politician_entity_id')::uuid,
      (item->>'term_number')::smallint,item->>'constituency',
      coalesce(item->>'constituency_type','unknown'),
      (item->>'party_entity_id')::uuid,item->>'legislator_number',
      (item->>'start_date')::date,(item->>'end_date')::date,
      (item->>'primary_evidence_id')::uuid,item->>'source_name',
      item->>'source_record_id','draft')
    on conflict (id) do update set
      constituency = excluded.constituency,
      constituency_type = excluded.constituency_type,
      party_entity_id = excluded.party_entity_id,
      legislator_number = excluded.legislator_number,
      start_date = excluded.start_date,
      end_date = excluded.end_date,
      primary_evidence_id = excluded.primary_evidence_id,
      updated_at = now()
    where public.politician_terms.publication_status = 'draft';
    n := n + 1;
  end loop;
  return core_result || jsonb_build_object('politician_terms_processed',n);
end $$;

revoke all on function public.tei_ingest_political_master_bundle(jsonb)
  from public, anon, authenticated;
grant execute on function public.tei_ingest_political_master_bundle(jsonb) to service_role;
