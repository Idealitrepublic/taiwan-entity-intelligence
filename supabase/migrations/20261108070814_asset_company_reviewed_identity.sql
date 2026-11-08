-- Keep the Gazette Evidence immutable while allowing a separately reviewed,
-- row-scoped official identifier to resolve a declaration counterparty.
alter table public.asset_declarations
  add column company_identity_evidence_id uuid
    references public.evidence_records(id);

create index asset_declarations_company_identity_evidence_idx
  on public.asset_declarations(company_identity_evidence_id)
  where company_identity_evidence_id is not null;

comment on column public.asset_declarations.company_identity_evidence_id is
  'Immutable row-scoped Evidence documenting reviewed company identity; primary_evidence_id remains the original declaration.';

create or replace function tei_private.validate_asset_declaration() returns trigger
language plpgsql set search_path = '' as $$
declare
  politician public.entities;
  company public.entities;
  proof public.evidence_records;
  identity_proof public.evidence_records;
  register_proof public.evidence_records;
  prior_review public.evidence_records;
  linked public.relationships;
  expected_relationship_type text;
  matched_uniform text;
  identity_namespace text;
  identity_value text;
  register_evidence_id uuid;
  prior_review_evidence_id uuid;
  expected_identity_role text;
begin
  if new.publication_status <> 'published' then return null; end if;

  select * into politician from public.entities where id = new.politician_id for share;
  select * into proof from public.evidence_records where id = new.primary_evidence_id for share;
  if politician.entity_type <> 'Politician' or politician.publication_status <> 'published'
     or proof.source_locator->>'politician_match_method' <> 'exact_official_identifier'
     or not exists (
       select 1 from public.entity_identifiers identifier
       where identifier.entity_id = new.politician_id
         and identifier.namespace = proof.source_locator->>'politician_identifier_namespace'
         and identifier.value = proof.source_locator->>'politician_identifier_value'
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

  if new.company_entity_id is null then
    if new.company_identity_evidence_id is not null or new.relationship_id is not null then
      raise exception 'Unresolved declaration cannot have a company identity or Relationship'
        using errcode = '23514';
    end if;
    return null;
  end if;

  select * into company from public.entities where id = new.company_entity_id for share;
  if company.entity_type <> 'Company' or company.publication_status <> 'published' then
    raise exception 'Resolved declaration company must be published' using errcode = '23514';
  end if;

  if new.company_identity_evidence_id is null then
    -- Backward-compatible path: an identifier must be present on the original
    -- source locator itself. A reviewed match must use the additive path below.
    matched_uniform := proof.source_locator->>'uniform_number';
    if proof.source_locator->>'company_match_method' <> 'exact_uniform_number'
       or matched_uniform !~ '^[0-9]{8}$'
       or not exists (
         select 1 from public.entity_identifiers identifier
         where identifier.entity_id = new.company_entity_id
           and identifier.namespace = 'tw:uniform_number'
           and identifier.value = matched_uniform and identifier.confidence = 'EXACT') then
      raise exception 'Company link requires source-exact identifier or reviewed identity Evidence'
        using errcode = '23514';
    end if;
  else
    select * into identity_proof from public.evidence_records
      where id = new.company_identity_evidence_id for share;
    identity_namespace := identity_proof.source_locator->>'identifier_namespace';
    identity_value := identity_proof.source_locator->>'identifier_value';
    expected_identity_role := case when new.asset_type = 'INSURANCE'
      then 'insurance_provider' else 'stock_issuer' end;
    register_evidence_id := (identity_proof.source_locator->>'register_evidence_id')::uuid;
    prior_review_evidence_id := (identity_proof.source_locator->>'prior_review_evidence_id')::uuid;
    if identity_proof.source_name <> '財產申報公司識別核准 / Asset issuer resolution approval'
       or identity_proof.source_class <> 'Derived Data'
       or identity_proof.status <> 'active' or identity_proof.publication_status <> 'published'
       or identity_proof.source_locator->>'decision' <> 'approved'
       or identity_proof.source_locator->>'identity_confidence' <> 'HIGH'
       or identity_proof.source_locator->>'matching_method' <> 'manual_row_scoped_official_registry_review'
       or identity_proof.source_locator->>'asset_declaration_id' <> new.id::text
       or identity_proof.source_locator->>'declaration_evidence_id' <> new.primary_evidence_id::text
       or identity_proof.source_locator->>'company_entity_id' <> new.company_entity_id::text
       or identity_proof.source_locator->>'source_company_name' is distinct from new.company_name
       or identity_proof.source_locator->>'role' <> expected_identity_role
       or identity_namespace not in ('tw:uniform_number','us:sec:cik')
       or (identity_namespace = 'tw:uniform_number' and identity_value !~ '^[0-9]{8}$')
       or (identity_namespace = 'us:sec:cik' and identity_value !~ '^[0-9]{10}$')
       or not exists (
         select 1 from public.entity_identifiers identifier
         where identifier.entity_id = new.company_entity_id
           and identifier.namespace = identity_namespace
           and identifier.value = identity_value
           and identifier.confidence = 'EXACT') then
      raise exception 'Reviewed company identity Evidence does not verify this declaration row and identifier'
        using errcode = '23514';
    end if;
    select * into register_proof from public.evidence_records where id = register_evidence_id for share;
    select * into prior_review from public.evidence_records where id = prior_review_evidence_id for share;
    if register_proof.source_name <> '申報對象官方登記識別 / Official counterparty register'
       or register_proof.source_class <> 'Official Registry'
       or register_proof.status <> 'active' or register_proof.publication_status <> 'published'
       or register_proof.source_locator->>'identifier_namespace' is distinct from identity_namespace
       or register_proof.source_locator->>'identifier_value' is distinct from identity_value
       or register_proof.source_locator->>'official_name' is distinct from company.canonical_name
       or prior_review.source_name <> '財產申報公司識別覆核 / Asset issuer identity review'
       or prior_review.status <> 'active' or prior_review.publication_status <> 'published'
       or prior_review.source_locator->>'asset_declaration_id' <> new.id::text
       or prior_review.source_locator->>'declaration_evidence_id' <> new.primary_evidence_id::text
       or prior_review.source_locator->>'register_evidence_id' <> register_evidence_id::text
       or prior_review.source_locator->>'identifier_namespace' <> identity_namespace
       or prior_review.source_locator->>'identifier_value' <> identity_value
       or prior_review.source_locator->>'source_company_name' is distinct from new.company_name
       or prior_review.source_locator->>'role' <> expected_identity_role
       or not exists (select 1 from public.entity_evidence link
         where link.entity_id = new.company_entity_id and link.evidence_id = register_evidence_id)
       or not exists (select 1 from public.entity_evidence link
         where link.entity_id = new.company_entity_id
           and link.evidence_id = new.company_identity_evidence_id) then
      raise exception 'Reviewed company identity lacks active registry and row-review provenance'
        using errcode = '23514';
    end if;
  end if;

  expected_relationship_type := case
    when new.asset_type = 'BUSINESS_INVESTMENT' then 'BUSINESS_INVESTMENT'
    when new.asset_type in ('STOCK','BOND','FUND','SECURITY') then 'ASSET_OWNERSHIP'
    else null end;
  if expected_relationship_type is null then
    if new.relationship_id is not null then
      raise exception 'Non-ownership asset cannot have an ownership Relationship'
        using errcode = '23514';
    end if;
    return null;
  end if;
  if new.relationship_id is null then
    raise exception 'Resolved ownership asset requires its published Relationship'
      using errcode = '23514';
  end if;
  select * into linked from public.relationships where id = new.relationship_id for share;
  if linked.source_entity_id <> new.politician_id
     or linked.target_entity_id <> new.company_entity_id
     or linked.relationship_type <> expected_relationship_type
     or linked.primary_evidence_id <> new.primary_evidence_id
     or linked.status <> 'published'
     or linked.confidence not in ('EXACT','HIGH')
     or linked.amount is distinct from new.amount
     or linked.currency is distinct from new.currency
     or linked.quantity is distinct from new.quantity
     or linked.quantity_unit is distinct from new.quantity_unit
     or linked.source_role is distinct from new.asset_type then
    raise exception 'Declaration Relationship does not match the verified asset line item'
      using errcode = '23514';
  end if;
  if new.company_identity_evidence_id is not null and (
       not exists (select 1 from public.relationship_evidence link
         where link.relationship_id = new.relationship_id
           and link.evidence_id = new.company_identity_evidence_id and link.support_type = 'supports')
       or not exists (select 1 from public.relationship_evidence link
         where link.relationship_id = new.relationship_id
           and link.evidence_id = register_evidence_id and link.support_type = 'context')) then
    raise exception 'Ownership Relationship must retain reviewed identity and registry Evidence'
      using errcode = '23514';
  end if;
  return null;
end $$;

create or replace function tei_private.withdraw_asset_declarations() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_table_name = 'evidence_records' then
    if new.status <> 'active' or new.publication_status <> 'published' then
      update public.relationships set status = 'retracted'
      where id in (
        select a.relationship_id from public.asset_declarations a
        where a.relationship_id is not null and a.publication_status = 'published'
          and (a.primary_evidence_id = new.id
            or a.company_identity_evidence_id = new.id
            or exists (select 1 from public.evidence_records review
              where review.id = a.company_identity_evidence_id
                and (review.source_locator->>'register_evidence_id' = new.id::text
                  or review.source_locator->>'prior_review_evidence_id' = new.id::text))));
      update public.asset_declarations set publication_status = 'withdrawn'
      where publication_status = 'published'
        and (primary_evidence_id = new.id or company_identity_evidence_id = new.id
          or exists (select 1 from public.evidence_records review
            where review.id = company_identity_evidence_id
              and (review.source_locator->>'register_evidence_id' = new.id::text
                or review.source_locator->>'prior_review_evidence_id' = new.id::text)));
    end if;
  elsif new.publication_status <> 'published' then
    update public.asset_declarations set publication_status = 'withdrawn'
    where (politician_id = new.id or company_entity_id = new.id)
      and publication_status = 'published';
  end if;
  return null;
end $$;

drop policy published_asset_declarations on public.asset_declarations;
create policy published_asset_declarations on public.asset_declarations
for select to anon, authenticated using (
  asset_declarations.publication_status = 'published'
  and exists (
    select 1 from public.entities politician
    where politician.id = asset_declarations.politician_id and politician.entity_type = 'Politician'
      and politician.publication_status = 'published')
  and exists (
    select 1 from public.evidence_records proof
    where proof.id = asset_declarations.primary_evidence_id and proof.status = 'active'
      and proof.publication_status = 'published')
  and (asset_declarations.company_entity_id is null or exists (
    select 1 from public.entities company
    where company.id = asset_declarations.company_entity_id and company.entity_type = 'Company'
      and company.publication_status = 'published'))
  and (asset_declarations.company_identity_evidence_id is null or exists (
    select 1 from public.evidence_records identity_proof
    join public.evidence_records register_proof
      on register_proof.id = (identity_proof.source_locator->>'register_evidence_id')::uuid
    join public.evidence_records prior_review
      on prior_review.id = (identity_proof.source_locator->>'prior_review_evidence_id')::uuid
    where identity_proof.id = asset_declarations.company_identity_evidence_id
      and identity_proof.status = 'active' and identity_proof.publication_status = 'published'
      and register_proof.status = 'active' and register_proof.publication_status = 'published'
      and prior_review.status = 'active' and prior_review.publication_status = 'published'))
  and (asset_declarations.relationship_id is null or exists (
    select 1 from public.relationships linked
    where linked.id = asset_declarations.relationship_id and linked.status = 'published'))
);

-- A repeated source bundle may still contain null company ids from the original
-- publication run. Preserve a separately reviewed link instead of treating it
-- as a source collision or overwriting it during an idempotent replay.
create or replace function public.tei_ingest_asset_declaration_bundle(bundle jsonb)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare item jsonb; existing public.asset_declarations; processed integer := 0;
  proof jsonb; locator jsonb; incoming_company uuid; incoming_relationship uuid;
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
      raise exception 'Asset declaration Evidence lacks identity or provenance' using errcode='22023';
    end if;
  end loop;
  perform public.tei_ingest_bundle(bundle - 'asset_declarations');
  for item in select value from jsonb_array_elements(coalesce(bundle->'asset_declarations','[]')) loop
    incoming_company := (item->>'company_entity_id')::uuid;
    incoming_relationship := (item->>'relationship_id')::uuid;
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
       or (existing.company_entity_id is distinct from incoming_company
           and not (incoming_company is null and existing.company_entity_id is not null
                    and existing.company_identity_evidence_id is not null))
       or (existing.relationship_id is distinct from incoming_relationship
           and not (incoming_relationship is null and existing.relationship_id is not null
                    and existing.company_identity_evidence_id is not null))
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
      item->>'quantity_unit',item->>'company_name',incoming_company,incoming_relationship,
      (item->>'primary_evidence_id')::uuid,'draft') on conflict(id) do nothing;
    processed := processed + 1;
  end loop;
  return jsonb_build_object('status','ok','asset_declarations_processed',processed);
end $$;

revoke all on function tei_private.validate_asset_declaration() from public, anon, authenticated;
revoke all on function tei_private.withdraw_asset_declarations() from public, anon, authenticated;
revoke all on function public.tei_ingest_asset_declaration_bundle(jsonb)
  from public, anon, authenticated;
grant execute on function tei_private.validate_asset_declaration() to service_role;
grant execute on function tei_private.withdraw_asset_declarations() to service_role;
grant execute on function public.tei_ingest_asset_declaration_bundle(jsonb) to service_role;
