-- DATA Phase 3: additive source/version identity for asset declaration lines.
alter table public.asset_declarations
  add column declaration_key text
    check (declaration_key is null or declaration_key ~ '^[0-9a-f]{64}$'),
  add column declaration_version smallint
    check (declaration_version is null or declaration_version between 1 and 999),
  add column supersedes_declaration_id uuid
    references public.asset_declarations(id);

alter table public.asset_declarations add constraint asset_declaration_version_fields
  check ((declaration_key is null) = (declaration_version is null));
alter table public.asset_declarations add constraint asset_declaration_not_self_superseding
  check (supersedes_declaration_id is null or supersedes_declaration_id <> id);

create unique index asset_declaration_version_identity_idx
  on public.asset_declarations(
    politician_id,declaration_year,declaration_key,declaration_version)
  where declaration_key is not null;
create unique index asset_declaration_one_published_version_idx
  on public.asset_declarations(politician_id,declaration_year,declaration_key)
  where declaration_key is not null and publication_status = 'published';
create index asset_declaration_supersedes_idx
  on public.asset_declarations(supersedes_declaration_id)
  where supersedes_declaration_id is not null;

create or replace function tei_private.validate_asset_declaration() returns trigger
language plpgsql set search_path = '' as $$
declare politician public.entities; company public.entities; proof public.evidence_records;
  linked public.relationships; prior public.asset_declarations;
  expected_relationship_type text; matched_uniform text;
  politician_namespace text; politician_value text;
begin
  if new.publication_status <> 'published' then return null; end if;
  select * into politician from public.entities where id = new.politician_id for share;
  select * into proof from public.evidence_records where id = new.primary_evidence_id for share;
  politician_namespace := proof.source_locator->>'politician_identifier_namespace';
  politician_value := proof.source_locator->>'politician_identifier_value';
  if politician.entity_type <> 'Politician' or politician.publication_status <> 'published'
     or proof.source_locator->>'politician_match_method' <> 'exact_official_identifier'
     or not exists (
       select 1 from public.entity_identifiers identifier
       where identifier.entity_id = new.politician_id
         and identifier.namespace = politician_namespace
         and identifier.value = politician_value
         and identifier.confidence = 'EXACT') then
    raise exception 'Published declaration requires an exactly identified Politician'
      using errcode = '23514';
  end if;
  if proof.status <> 'active' or proof.publication_status <> 'published'
     or proof.source_url is null or btrim(proof.source_url) = ''
     or proof.retrieved_at is null
     or proof.source_locator->>'declaration_key' is distinct from new.declaration_key
     or (proof.source_locator->>'declaration_version')::smallint
        is distinct from new.declaration_version then
    raise exception 'Published declaration requires active versioned Evidence'
      using errcode = '23514';
  end if;
  if new.declaration_key is null or new.declaration_version is null then
    raise exception 'Published declaration requires version identity' using errcode = '23514';
  end if;
  if new.supersedes_declaration_id is not null then
    select * into prior from public.asset_declarations
      where id = new.supersedes_declaration_id for share;
    if prior.politician_id <> new.politician_id
       or prior.declaration_year <> new.declaration_year
       or prior.declaration_key <> new.declaration_key
       or prior.declaration_version >= new.declaration_version
       or prior.publication_status <> 'withdrawn' then
      raise exception 'Superseded declaration must be an older withdrawn version'
        using errcode = '23514';
    end if;
  elsif new.declaration_version <> 1 then
    raise exception 'Later declaration versions must reference the prior version'
      using errcode = '23514';
  end if;
  if new.company_entity_id is null then
    if new.relationship_id is not null then
      raise exception 'Unresolved declaration company cannot have a Relationship'
        using errcode = '23514';
    end if;
    return null;
  end if;
  select * into company from public.entities where id = new.company_entity_id for share;
  matched_uniform := proof.source_locator->>'uniform_number';
  if company.entity_type <> 'Company' or company.publication_status <> 'published'
     or proof.source_locator->>'company_match_method' <> 'exact_uniform_number'
     or matched_uniform !~ '^[0-9]{8}$'
     or not exists (
       select 1 from public.entity_identifiers identifier
       where identifier.entity_id = new.company_entity_id
         and identifier.namespace = 'tw:uniform_number'
         and identifier.value = matched_uniform and identifier.confidence = 'EXACT') then
    raise exception 'Resolved declaration company requires an exact uniform-number match'
      using errcode = '23514';
  end if;
  expected_relationship_type := case
    when new.asset_type = 'BUSINESS_INVESTMENT' then 'BUSINESS_INVESTMENT'
    when new.asset_type in ('STOCK','BOND','FUND','SECURITY') then 'ASSET_OWNERSHIP'
    else null end;
  if new.relationship_id is null then return null; end if;
  select * into linked from public.relationships where id = new.relationship_id for share;
  if expected_relationship_type is null
     or linked.source_entity_id <> new.politician_id
     or linked.target_entity_id <> new.company_entity_id
     or linked.relationship_type <> expected_relationship_type
     or linked.primary_evidence_id <> new.primary_evidence_id
     or linked.status <> 'published'
     or linked.amount is distinct from new.amount
     or linked.currency is distinct from new.currency
     or linked.quantity is distinct from new.quantity
     or linked.quantity_unit is distinct from new.quantity_unit
     or linked.source_role is distinct from new.asset_type then
    raise exception 'Declaration Relationship does not match the asset line item'
      using errcode = '23514';
  end if;
  return null;
end $$;

create or replace function public.tei_ingest_asset_declaration_bundle(bundle jsonb)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare item jsonb; existing public.asset_declarations; processed integer := 0;
  proof jsonb; locator jsonb;
begin
  if jsonb_typeof(bundle) <> 'object' or octet_length(bundle::text) > 1048576
     or jsonb_array_length(coalesce(bundle->'asset_declarations','[]')) > 200 then
    raise exception 'Invalid or oversized asset declaration bundle' using errcode = '22023';
  end if;
  if jsonb_array_length(coalesce(bundle->'entities','[]')) <> 0
     or jsonb_array_length(coalesce(bundle->'identifiers','[]')) <> 0 then
    raise exception 'Asset ingestion cannot create or resolve entities' using errcode='22023';
  end if;
  for item in select value from jsonb_array_elements(coalesce(bundle->'asset_declarations','[]')) loop
    if coalesce(item->>'publication_status','draft') <> 'draft'
       or item->>'declaration_key' !~ '^[0-9a-f]{64}$'
       or (item->>'declaration_version')::smallint not between 1 and 999 then
      raise exception 'Asset ingestion accepts versioned draft lines only' using errcode='22023';
    end if;
    select value into proof from jsonb_array_elements(coalesce(bundle->'evidence','[]'))
      where value->>'id' = item->>'primary_evidence_id';
    locator := proof->'source_locator';
    if proof is null or coalesce(proof->>'publication_status','draft') <> 'draft'
       or nullif(btrim(proof->>'source_record_id'),'') is null
       or nullif(btrim(proof->>'source_url'),'') is null
       or locator->>'declaration_key' is distinct from item->>'declaration_key'
       or locator->>'declaration_version' is distinct from item->>'declaration_version'
       or locator->>'politician_match_method' <> 'exact_official_identifier'
       or nullif(btrim(locator->>'politician_identifier_namespace'),'') is null
       or nullif(btrim(locator->>'politician_identifier_value'),'') is null then
      raise exception 'Asset declaration Evidence lacks identity or provenance'
        using errcode='22023';
    end if;
  end loop;
  perform public.tei_ingest_bundle(bundle - 'asset_declarations');
  for item in select value from jsonb_array_elements(coalesce(bundle->'asset_declarations','[]')) loop
    select * into existing from public.asset_declarations where id = (item->>'id')::uuid;
    if found and (
       existing.politician_id <> (item->>'politician_id')::uuid
       or existing.declaration_year <> (item->>'declaration_year')::smallint
       or existing.declaration_key <> item->>'declaration_key'
       or existing.declaration_version <> (item->>'declaration_version')::smallint
       or existing.asset_type <> item->>'asset_type'
       or existing.asset_name <> item->>'asset_name'
       or existing.amount is distinct from (item->>'amount')::numeric
       or existing.currency is distinct from item->>'currency'
       or existing.quantity is distinct from (item->>'quantity')::numeric
       or existing.quantity_unit is distinct from item->>'quantity_unit'
       or existing.company_name is distinct from item->>'company_name'
       or existing.company_entity_id is distinct from (item->>'company_entity_id')::uuid
       or existing.relationship_id is distinct from (item->>'relationship_id')::uuid
       or existing.primary_evidence_id <> (item->>'primary_evidence_id')::uuid) then
      raise exception 'Asset declaration version collision' using errcode = '23505';
    end if;
    insert into public.asset_declarations(
      id,politician_id,declaration_year,declaration_key,declaration_version,
      supersedes_declaration_id,asset_type,asset_name,amount,currency,quantity,
      quantity_unit,company_name,company_entity_id,relationship_id,primary_evidence_id,
      publication_status)
    values ((item->>'id')::uuid,(item->>'politician_id')::uuid,
      (item->>'declaration_year')::smallint,item->>'declaration_key',
      (item->>'declaration_version')::smallint,
      (item->>'supersedes_declaration_id')::uuid,item->>'asset_type',item->>'asset_name',
      (item->>'amount')::numeric,item->>'currency',(item->>'quantity')::numeric,
      item->>'quantity_unit',item->>'company_name',(item->>'company_entity_id')::uuid,
      (item->>'relationship_id')::uuid,(item->>'primary_evidence_id')::uuid,'draft')
    on conflict(id) do nothing;
    processed := processed + 1;
  end loop;
  return jsonb_build_object('status','ok','asset_declarations_processed',processed);
end $$;

revoke all on function public.tei_ingest_asset_declaration_bundle(jsonb)
  from public, anon, authenticated;
grant execute on function public.tei_ingest_asset_declaration_bundle(jsonb) to service_role;
