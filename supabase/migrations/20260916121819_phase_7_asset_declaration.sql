-- Phase 7 stores source-backed declaration line items. AssetDeclaration remains
-- an available Entity type, but a line item is not promoted to a duplicate Entity.
create table public.asset_declarations (
  id uuid primary key default gen_random_uuid(),
  politician_id uuid not null references public.entities(id),
  declaration_year smallint not null check (declaration_year between 1912 and 2200),
  asset_type text not null check (asset_type in (
    'REAL_ESTATE','CASH','DEPOSIT','STOCK','BOND','FUND','SECURITY','CLAIM','DEBT',
    'BUSINESS_INVESTMENT','INSURANCE','VEHICLE','OTHER')),
  asset_name text not null check (length(btrim(asset_name)) between 1 and 500),
  amount numeric check (amount >= 0 and amount <> 'NaN'::numeric and amount <> 'Infinity'::numeric),
  currency text check (currency ~ '^[A-Z]{3}$'),
  quantity numeric check (quantity >= 0 and quantity <> 'NaN'::numeric and quantity <> 'Infinity'::numeric),
  quantity_unit text check (quantity_unit is null or length(btrim(quantity_unit)) between 1 and 50),
  company_name text check (company_name is null or length(btrim(company_name)) between 1 and 500),
  company_entity_id uuid references public.entities(id),
  relationship_id uuid unique references public.relationships(id),
  primary_evidence_id uuid not null references public.evidence_records(id),
  publication_status text not null default 'draft'
    check (publication_status in ('draft','published','withdrawn')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((amount is null) = (currency is null)),
  check ((quantity is null) = (quantity_unit is null)),
  unique (politician_id, primary_evidence_id)
);

create index asset_declarations_politician_id_idx
  on public.asset_declarations (politician_id, id);
create index asset_declarations_politician_year_idx
  on public.asset_declarations (politician_id, declaration_year, id);
create index asset_declarations_politician_type_idx
  on public.asset_declarations (politician_id, asset_type, id);
create index asset_declarations_company_idx
  on public.asset_declarations (company_entity_id, id) where company_entity_id is not null;
create index asset_declarations_evidence_idx
  on public.asset_declarations (primary_evidence_id);

create trigger asset_declarations_updated before update on public.asset_declarations
for each row execute function tei_private.touch_updated_at();

create function tei_private.validate_asset_declaration() returns trigger
language plpgsql set search_path = '' as $$
declare politician public.entities; company public.entities; proof public.evidence_records;
  linked public.relationships; expected_relationship_type text; matched_uniform text;
begin
  if new.publication_status <> 'published' then return null; end if;
  select * into politician from public.entities where id = new.politician_id for share;
  select * into proof from public.evidence_records where id = new.primary_evidence_id for share;
  if politician.entity_type <> 'Politician' or politician.publication_status <> 'published' then
    raise exception 'Published declaration requires a published Politician entity'
      using errcode = '23514';
  end if;
  if proof.status <> 'active' or proof.publication_status <> 'published' then
    raise exception 'Published declaration requires active published Evidence'
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
         and identifier.value = matched_uniform and identifier.confidence = 'EXACT'
     ) then
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

create constraint trigger asset_declarations_valid
after insert or update on public.asset_declarations
deferrable initially deferred for each row execute function tei_private.validate_asset_declaration();

create function tei_private.withdraw_asset_declarations() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_table_name = 'evidence_records' then
    if new.status <> 'active' or new.publication_status <> 'published' then
      update public.asset_declarations set publication_status = 'withdrawn'
      where primary_evidence_id = new.id and publication_status = 'published';
    end if;
  elsif new.publication_status <> 'published' then
    update public.asset_declarations set publication_status = 'withdrawn'
    where (politician_id = new.id or company_entity_id = new.id)
      and publication_status = 'published';
  end if;
  return null;
end $$;

create trigger asset_evidence_withdrawal
after update of status, publication_status on public.evidence_records
for each row execute function tei_private.withdraw_asset_declarations();
create trigger asset_entity_withdrawal
after update of publication_status on public.entities
for each row execute function tei_private.withdraw_asset_declarations();

alter table public.asset_declarations enable row level security;
revoke all on table public.asset_declarations from public, anon, authenticated;
grant select, insert, update, delete on table public.asset_declarations to service_role;
grant select on table public.asset_declarations to anon, authenticated;
create policy service_access on public.asset_declarations for all to service_role
  using (true) with check (true);
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
  and (asset_declarations.relationship_id is null or exists (
    select 1 from public.relationships linked
    where linked.id = asset_declarations.relationship_id and linked.status = 'published'))
);

-- One bounded, service-role-only transaction extends the existing generic bundle.
create function public.tei_ingest_asset_declaration_bundle(bundle jsonb) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare item jsonb; existing public.asset_declarations; processed integer := 0;
begin
  if jsonb_typeof(bundle) <> 'object' or octet_length(bundle::text) > 1048576
     or jsonb_array_length(coalesce(bundle->'asset_declarations','[]')) > 400 then
    raise exception 'Invalid or oversized asset declaration bundle' using errcode = '22023';
  end if;
  perform public.tei_ingest_bundle(bundle);
  for item in select value from jsonb_array_elements(coalesce(bundle->'asset_declarations','[]')) loop
    select * into existing from public.asset_declarations where id = (item->>'id')::uuid;
    if found and (
       existing.politician_id <> (item->>'politician_id')::uuid
       or existing.declaration_year <> (item->>'declaration_year')::smallint
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
      id,politician_id,declaration_year,asset_type,asset_name,amount,currency,quantity,
      quantity_unit,company_name,company_entity_id,relationship_id,primary_evidence_id,
      publication_status)
    values (
      (item->>'id')::uuid,(item->>'politician_id')::uuid,
      (item->>'declaration_year')::smallint,item->>'asset_type',item->>'asset_name',
      (item->>'amount')::numeric,item->>'currency',(item->>'quantity')::numeric,
      item->>'quantity_unit',item->>'company_name',(item->>'company_entity_id')::uuid,
      (item->>'relationship_id')::uuid,(item->>'primary_evidence_id')::uuid,
      coalesce(item->>'publication_status','draft')) on conflict(id) do nothing;
    processed := processed + 1;
  end loop;
  return jsonb_build_object('status','ok','asset_declarations_processed',processed);
end $$;

revoke all on function public.tei_ingest_asset_declaration_bundle(jsonb)
  from public, anon, authenticated;
grant execute on function public.tei_ingest_asset_declaration_bundle(jsonb) to service_role;
revoke all on function tei_private.validate_asset_declaration()
  from public, anon, authenticated;
revoke all on function tei_private.withdraw_asset_declarations()
  from public, anon, authenticated;
grant execute on function tei_private.validate_asset_declaration() to service_role;
grant execute on function tei_private.withdraw_asset_declarations() to service_role;
