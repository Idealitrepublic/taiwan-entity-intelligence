-- Phase 1 is additive. Existing companies / people / evidence / source tables are untouched.
create schema if not exists tei_private;
revoke all on schema tei_private from public, anon, authenticated;
grant usage on schema tei_private to service_role;

create table public.entity_types (
  code text primary key
);
insert into public.entity_types(code) values
('Company'),('Person'),('Politician'),('GovernmentOfficial'),('GovernmentAgency'),
('PoliticalParty'),('Contract'),('Judgment'),('Penalty'),('PoliticalContribution'),
('AssetDeclaration'),('LegislativeBill'),('LobbyingRecord');

create table public.entities (
  id uuid primary key default gen_random_uuid(),
  entity_type text not null references public.entity_types(code),
  canonical_name text not null check (length(btrim(canonical_name)) between 1 and 500),
  display_name text not null check (length(btrim(display_name)) between 1 and 500),
  source text not null check (btrim(source) <> ''),
  source_id text not null check (btrim(source_id) <> ''),
  identity_status text not null default 'SOURCE_SCOPED'
    check (identity_status in ('EXACT','SOURCE_SCOPED','UNRESOLVED')),
  publication_status text not null default 'draft'
    check (publication_status in ('draft','published','withdrawn')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(source, source_id)
);
create index entities_type_name_idx on public.entities(entity_type, canonical_name, id);

-- Identifiers may be sensitive: deliberately not granted to public clients.
create table public.entity_identifiers (
  id uuid primary key default gen_random_uuid(),
  entity_id uuid not null references public.entities(id),
  namespace text not null check (btrim(namespace) <> ''),
  value text not null check (btrim(value) <> ''),
  confidence text not null default 'EXACT' check (confidence = 'EXACT'),
  created_at timestamptz not null default now(),
  unique(namespace, value)
);
create index entity_identifiers_entity_idx on public.entity_identifiers(entity_id);
create table public.entity_aliases (
  id uuid primary key default gen_random_uuid(),
  entity_id uuid not null references public.entities(id),
  alias text not null check (btrim(alias) <> ''),
  source text not null,
  created_at timestamptz not null default now(),
  unique(entity_id, alias, source)
);
create index entity_aliases_name_idx on public.entity_aliases(alias);

create table public.evidence_records (
  id uuid primary key default gen_random_uuid(),
  source_name text not null check (btrim(source_name) <> ''),
  source_record_id text not null check (btrim(source_record_id) <> ''),
  source_class text not null check (source_class in
    ('Primary Source','Government Open Data','Official Registry','Court Record','Derived Data')),
  source_url text check (source_url ~ '^https?://[^/@[:space:]]+([/:?#]|$)' and source_url !~ '^https?://[^/]*@'),
  source_locator jsonb not null default '{}' check (jsonb_typeof(source_locator) = 'object'),
  title text not null check (btrim(title) <> ''),
  summary text not null default '',
  observed_at timestamptz not null,
  retrieved_at timestamptz not null,
  content_hash text not null check (content_hash ~ '^[0-9a-f]{64}$'),
  status text not null default 'active' check (status in ('active','superseded','retracted')),
  publication_status text not null default 'draft' check (publication_status in ('draft','published','withdrawn')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(source_name, source_record_id, content_hash),
  check (source_url is not null or source_locator <> '{}')
);
create index evidence_records_source_idx on public.evidence_records(source_name, source_record_id);
create table public.entity_sources (
  id uuid primary key default gen_random_uuid(),
  entity_id uuid not null references public.entities(id),
  evidence_id uuid not null references public.evidence_records(id),
  source text not null,
  source_id text not null,
  observed_at timestamptz not null,
  unique(entity_id, source, source_id, evidence_id)
);
create index entity_sources_evidence_idx on public.entity_sources(evidence_id);
create table public.entity_evidence (
  entity_id uuid not null references public.entities(id),
  evidence_id uuid not null references public.evidence_records(id),
  fact_type text not null check (btrim(fact_type) <> ''),
  primary key(entity_id, evidence_id, fact_type)
);
create index entity_evidence_evidence_idx on public.entity_evidence(evidence_id);

create table public.relationship_types (
  code text primary key,
  source_types text[] not null,
  target_types text[] not null,
  directed boolean not null default true
);
insert into public.relationship_types(code, source_types, target_types) values
('DIRECTOR_OF',array['Person','Politician','GovernmentOfficial','Company'],array['Company']),
('OFFICER_OF',array['Person','Politician','GovernmentOfficial'],array['Company','GovernmentAgency']),
('OWNER_OF',array['Person','Politician','GovernmentOfficial','Company'],array['Company']),
('SHAREHOLDER_OF',array['Person','Politician','GovernmentOfficial','Company'],array['Company']),
('POLITICAL_CONTRIBUTION_TO',array['Company','Person','Politician','GovernmentOfficial'],array['Politician','PoliticalParty','Person']),
('CONTRACT_WITH',array['Company','GovernmentAgency','Contract'],array['Company','GovernmentAgency','Contract']),
('MEMBER_OF',array['Person','Politician','GovernmentOfficial'],array['PoliticalParty','GovernmentAgency','Company']),
('EMPLOYED_BY',array['Person','Politician','GovernmentOfficial'],array['Company','GovernmentAgency']),
('GOVERNMENT_POSITION',array['Person','Politician','GovernmentOfficial'],array['GovernmentAgency']),
('LEGISLATOR_OF',array['Person','Politician'],array['GovernmentAgency']),
('COMMITTEE_MEMBER',array['Person','Politician','GovernmentOfficial'],array['GovernmentAgency']),
('PROPOSED_BILL',array['Person','Politician','GovernmentAgency'],array['LegislativeBill']),
('CO_SPONSORED_BILL',array['Person','Politician'],array['LegislativeBill']),
('ASSET_OWNERSHIP',array['Person','Politician','GovernmentOfficial'],array['Company','AssetDeclaration']),
('BUSINESS_INVESTMENT',array['Person','Politician','GovernmentOfficial','Company'],array['Company']),
('RELATED_TO_JUDGMENT',array['Company','Person','Politician','GovernmentOfficial','GovernmentAgency'],array['Judgment']),
('RELATED_TO_PENALTY',array['Company','Person','Politician','GovernmentOfficial','GovernmentAgency'],array['Penalty']);

create table public.relationships (
  id uuid primary key default gen_random_uuid(),
  source_entity_id uuid not null references public.entities(id),
  target_entity_id uuid not null references public.entities(id),
  relationship_type text not null references public.relationship_types(code),
  primary_evidence_id uuid not null references public.evidence_records(id),
  start_date date,
  end_date date,
  date_precision text not null default 'unknown' check (date_precision in ('day','month','year','unknown')),
  observed_at timestamptz not null,
  amount numeric check (amount >= 0 and amount <> 'NaN'::numeric and amount <> 'Infinity'::numeric),
  currency text check (currency ~ '^[A-Z]{3}$'),
  percentage numeric check (percentage between 0 and 100 and percentage <> 'NaN'::numeric),
  quantity numeric check (quantity >= 0 and quantity <> 'NaN'::numeric and quantity <> 'Infinity'::numeric),
  quantity_unit text,
  source_role text,
  confidence text not null default 'UNRESOLVED' check (confidence in ('EXACT','HIGH','MEDIUM','LOW','UNRESOLVED')),
  status text not null default 'draft' check (status in ('draft','published','retracted')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (source_entity_id <> target_entity_id),
  check (end_date is null or start_date is null or end_date >= start_date),
  check (date_precision = 'unknown' or start_date is not null or end_date is not null),
  check ((amount is null) = (currency is null)),
  check ((quantity is null) = (quantity_unit is null)),
  check (status <> 'published' or confidence in ('EXACT','HIGH'))
);
create index relationships_source_type_idx on public.relationships(source_entity_id, relationship_type, id);
create index relationships_target_type_idx on public.relationships(target_entity_id, relationship_type, id);
create index relationships_primary_evidence_idx on public.relationships(primary_evidence_id);
create table public.relationship_evidence (
  relationship_id uuid not null references public.relationships(id),
  evidence_id uuid not null references public.evidence_records(id),
  support_type text not null default 'supports' check (support_type in ('supports','context','refutes')),
  primary key(relationship_id, evidence_id)
);
create index relationship_evidence_evidence_idx on public.relationship_evidence(evidence_id);
create table public.resolution_candidates (
  id uuid primary key default gen_random_uuid(),
  source_entity_id uuid not null references public.entities(id),
  candidate_entity_id uuid references public.entities(id),
  confidence text not null check (confidence in ('EXACT','HIGH','MEDIUM','LOW','UNRESOLVED')),
  reason text not null,
  evidence_id uuid not null references public.evidence_records(id),
  status text not null default 'pending' check (status in ('pending','accepted','rejected')),
  created_at timestamptz not null default now(),
  check (source_entity_id <> candidate_entity_id)
);
create index resolution_candidates_source_idx on public.resolution_candidates(source_entity_id);
create index resolution_candidates_target_idx on public.resolution_candidates(candidate_entity_id);
create index resolution_candidates_evidence_idx on public.resolution_candidates(evidence_id);
create table public.legacy_entity_map (
  legacy_namespace text not null,
  legacy_id text not null,
  entity_id uuid not null references public.entities(id),
  created_at timestamptz not null default now(),
  primary key(legacy_namespace, legacy_id)
);
create index legacy_entity_map_entity_idx on public.legacy_entity_map(entity_id);

create function tei_private.touch_updated_at() returns trigger language plpgsql
set search_path = '' as $$ begin new.updated_at := now(); return new; end $$;
create trigger entities_updated before update on public.entities
for each row execute function tei_private.touch_updated_at();
create trigger relationships_updated before update on public.relationships
for each row execute function tei_private.touch_updated_at();
create trigger evidence_updated before update on public.evidence_records
for each row execute function tei_private.touch_updated_at();

create function tei_private.immutable_entity_identity() returns trigger language plpgsql
set search_path = '' as $$
begin
  if row(new.id,new.entity_type,new.source,new.source_id) is distinct from
     row(old.id,old.entity_type,old.source,old.source_id) then
    raise exception 'Entity identity is immutable; use reviewed resolution mappings' using errcode='23514';
  end if;
  return new;
end $$;
create trigger entity_identity_immutable before update on public.entities
for each row execute function tei_private.immutable_entity_identity();

create function tei_private.immutable_evidence() returns trigger language plpgsql
set search_path = '' as $$
begin
  if (to_jsonb(new) - array['status','publication_status','updated_at'])
       is distinct from (to_jsonb(old) - array['status','publication_status','updated_at']) then
    raise exception 'Evidence is immutable; insert a new version' using errcode = '23514';
  end if;
  return new;
end $$;
create trigger evidence_immutable before update on public.evidence_records
for each row execute function tei_private.immutable_evidence();

create function tei_private.validate_relationship() returns trigger language plpgsql
set search_path = '' as $$
declare r public.relationships; kinds public.relationship_types; primary_record public.evidence_records;
  source_record public.entities; target_record public.entities;
begin
  select * into r from public.relationships where id = new.id;
  if not found then return null; end if;
  select * into kinds from public.relationship_types where code = r.relationship_type;
  if not exists(select 1 from public.entities where id = r.source_entity_id and entity_type = any(kinds.source_types))
     or not exists(select 1 from public.entities where id = r.target_entity_id and entity_type = any(kinds.target_types)) then
    raise exception 'Relationship direction or endpoint type is invalid' using errcode = '23514';
  end if;
  if r.status = 'published' then
    select * into primary_record from public.evidence_records where id=r.primary_evidence_id for share;
    select * into source_record from public.entities where id=r.source_entity_id for share;
    select * into target_record from public.entities where id=r.target_entity_id for share;
    if primary_record.status <> 'active' or primary_record.publication_status <> 'published' then
      raise exception 'Published relationship requires active published primary evidence' using errcode = '23514';
    end if;
    if source_record.publication_status <> 'published' or target_record.publication_status <> 'published' then
      raise exception 'Published relationship requires published endpoints' using errcode = '23514';
    end if;
  end if;
  return null;
end $$;
create constraint trigger relationships_valid after insert or update on public.relationships
  deferrable initially deferred for each row execute function tei_private.validate_relationship();

-- A withdrawal never leaves a published edge relying on invalid primary evidence.
-- Secondary evidence is preserved for review; replacing primary evidence is explicit.
create function tei_private.withdraw_dependents() returns trigger language plpgsql
set search_path = '' as $$
begin
  if tg_table_name = 'evidence_records' then
    if new.status <> 'active' or new.publication_status <> 'published' then
      update public.relationships set status = 'retracted'
      where primary_evidence_id = new.id and status = 'published';
    end if;
  elsif new.publication_status <> 'published' then
    update public.relationships set status = 'retracted'
    where (source_entity_id = new.id or target_entity_id = new.id) and status = 'published';
  end if;
  return null;
end $$;
create trigger evidence_withdrawal after update of status, publication_status on public.evidence_records
for each row execute function tei_private.withdraw_dependents();
create trigger entity_withdrawal after update of publication_status on public.entities
for each row execute function tei_private.withdraw_dependents();

-- Explicitly undo inherited Supabase default grants on ONLY the new objects.
do $$ declare t text; begin
  foreach t in array array['entity_types','entities','entity_identifiers','entity_aliases',
    'evidence_records','entity_sources','entity_evidence','relationship_types','relationships',
    'relationship_evidence','resolution_candidates','legacy_entity_map'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on table public.%I from public, anon, authenticated', t);
    execute format('grant select, insert, update, delete on table public.%I to service_role', t);
    execute format('create policy service_access on public.%I for all to service_role using (true) with check (true)', t);
  end loop;
end $$;
grant select on public.entity_types, public.relationship_types, public.entities,
 public.evidence_records, public.relationships, public.entity_evidence,
 public.relationship_evidence to anon, authenticated;
create policy public_types on public.entity_types for select to anon, authenticated using (true);
create policy public_relationship_types on public.relationship_types for select to anon, authenticated using (true);
create policy published_entities on public.entities for select to anon, authenticated
 using (publication_status = 'published');
create policy published_evidence on public.evidence_records for select to anon, authenticated
 using (publication_status = 'published' and status = 'active');
create policy published_relationships on public.relationships for select to anon, authenticated
 using (status = 'published'
   and exists(select 1 from public.evidence_records e where e.id = primary_evidence_id)
   and exists(select 1 from public.entities e where e.id = source_entity_id)
   and exists(select 1 from public.entities e where e.id = target_entity_id));
create policy published_entity_evidence on public.entity_evidence for select to anon, authenticated
 using (exists(select 1 from public.entities e where e.id = entity_id)
   and exists(select 1 from public.evidence_records e where e.id = evidence_id));
create policy published_relationship_evidence on public.relationship_evidence for select to anon, authenticated
 using (exists(select 1 from public.relationships r where r.id = relationship_id)
   and exists(select 1 from public.evidence_records e where e.id = evidence_id));

-- One transaction per bounded bundle. No public write RPC or SECURITY DEFINER.
create function public.tei_ingest_bundle(bundle jsonb) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare item jsonb; existing public.entities; ev public.evidence_records; rel public.relationships;
  mapped uuid; n integer := 0;
begin
  if jsonb_typeof(bundle) <> 'object' or octet_length(bundle::text) > 1048576 then
    raise exception 'Invalid or oversized ingestion bundle' using errcode = '22023';
  end if;
  if jsonb_array_length(coalesce(bundle->'entities','[]')) > 200
     or jsonb_array_length(coalesce(bundle->'relationships','[]')) > 200
     or jsonb_array_length(coalesce(bundle->'evidence','[]')) > 400 then
    raise exception 'Ingestion bundle exceeds record limit' using errcode = '22023';
  end if;
  for item in select value from jsonb_array_elements(coalesce(bundle->'entities','[]')) loop
    select * into existing from public.entities where id = (item->>'id')::uuid;
    if found and (existing.entity_type <> item->>'entity_type' or existing.source <> item->>'source'
       or existing.source_id <> item->>'source_id') then
      raise exception 'Entity identity collision' using errcode = '23505';
    end if;
    insert into public.entities(id,entity_type,canonical_name,display_name,source,source_id,identity_status,publication_status)
    values ((item->>'id')::uuid,item->>'entity_type',item->>'canonical_name',item->>'display_name',
      item->>'source',item->>'source_id',item->>'identity_status',coalesce(item->>'publication_status','draft'))
    on conflict(id) do nothing;
  end loop;
  for item in select value from jsonb_array_elements(coalesce(bundle->'evidence','[]')) loop
    select * into ev from public.evidence_records where id = (item->>'id')::uuid;
    if found and (ev.source_name <> item->>'source_name' or ev.source_record_id <> item->>'source_record_id'
       or ev.content_hash <> item->>'content_hash' or ev.title <> item->>'title'
       or ev.summary <> item->>'summary' or ev.source_locator <> item->'source_locator'
       or ev.source_url is distinct from item->>'source_url'
       or ev.source_class <> item->>'source_class') then
      raise exception 'Evidence version collision' using errcode = '23505';
    end if;
    insert into public.evidence_records(id,source_name,source_record_id,source_class,source_url,source_locator,
      title,summary,observed_at,retrieved_at,content_hash,publication_status,status)
    values ((item->>'id')::uuid,item->>'source_name',item->>'source_record_id',item->>'source_class',
      item->>'source_url',item->'source_locator',item->>'title',item->>'summary',
      (item->>'observed_at')::timestamptz,(item->>'retrieved_at')::timestamptz,item->>'content_hash',
      coalesce(item->>'publication_status','draft'),coalesce(item->>'status','active')) on conflict(id) do nothing;
  end loop;
  for item in select value from jsonb_array_elements(coalesce(bundle->'identifiers','[]')) loop
    insert into public.entity_identifiers(entity_id,namespace,value)
    values ((item->>'entity_id')::uuid,item->>'namespace',item->>'value') on conflict(namespace,value) do nothing;
    select entity_id into mapped from public.entity_identifiers where namespace=item->>'namespace' and value=item->>'value';
    if mapped <> (item->>'entity_id')::uuid then raise exception 'Identifier collision' using errcode='23505'; end if;
  end loop;
  for item in select value from jsonb_array_elements(coalesce(bundle->'entity_evidence','[]')) loop
    insert into public.entity_evidence(entity_id,evidence_id,fact_type)
    values ((item->>'entity_id')::uuid,(item->>'evidence_id')::uuid,item->>'fact_type') on conflict do nothing;
    insert into public.entity_sources(entity_id,evidence_id,source,source_id,observed_at)
    select e.id,v.id,e.source,e.source_id,v.observed_at from public.entities e
      join public.evidence_records v on v.id=(item->>'evidence_id')::uuid
      where e.id=(item->>'entity_id')::uuid on conflict do nothing;
  end loop;
  for item in select value from jsonb_array_elements(coalesce(bundle->'relationships','[]')) loop
    select * into rel from public.relationships where id = (item->>'id')::uuid;
    if found and (rel.source_entity_id <> (item->>'source_entity_id')::uuid
      or rel.target_entity_id <> (item->>'target_entity_id')::uuid
      or rel.relationship_type <> item->>'relationship_type'
      or rel.primary_evidence_id <> (item->>'primary_evidence_id')::uuid
      or rel.amount is distinct from (item->>'amount')::numeric
      or rel.currency is distinct from item->>'currency'
      or rel.percentage is distinct from (item->>'percentage')::numeric
      or rel.quantity is distinct from (item->>'quantity')::numeric
      or rel.quantity_unit is distinct from item->>'quantity_unit'
      or rel.start_date is distinct from (item->>'start_date')::date
      or rel.end_date is distinct from (item->>'end_date')::date
      or rel.date_precision <> coalesce(item->>'date_precision','unknown')
      or rel.source_role is distinct from item->>'source_role'
      or rel.confidence <> item->>'confidence') then
      raise exception 'Relationship version collision' using errcode = '23505';
    end if;
    insert into public.relationships(id,source_entity_id,target_entity_id,relationship_type,primary_evidence_id,
      observed_at,confidence,status,start_date,end_date,date_precision,amount,currency,percentage,quantity,quantity_unit,source_role)
    values ((item->>'id')::uuid,(item->>'source_entity_id')::uuid,(item->>'target_entity_id')::uuid,
      item->>'relationship_type',(item->>'primary_evidence_id')::uuid,(item->>'observed_at')::timestamptz,
      item->>'confidence',coalesce(item->>'status','draft'),(item->>'start_date')::date,(item->>'end_date')::date,
      coalesce(item->>'date_precision','unknown'),(item->>'amount')::numeric,item->>'currency',
      (item->>'percentage')::numeric,(item->>'quantity')::numeric,item->>'quantity_unit',item->>'source_role')
    on conflict(id) do nothing;
    n := n + 1;
  end loop;
  for item in select value from jsonb_array_elements(coalesce(bundle->'relationship_evidence','[]')) loop
    insert into public.relationship_evidence(relationship_id,evidence_id,support_type)
    values ((item->>'relationship_id')::uuid,(item->>'evidence_id')::uuid,coalesce(item->>'support_type','supports'))
    on conflict do nothing;
  end loop;
  for item in select value from jsonb_array_elements(coalesce(bundle->'legacy_map','[]')) loop
    insert into public.legacy_entity_map(legacy_namespace,legacy_id,entity_id)
    values (item->>'legacy_namespace',item->>'legacy_id',(item->>'entity_id')::uuid) on conflict do nothing;
    select entity_id into mapped from public.legacy_entity_map
      where legacy_namespace=item->>'legacy_namespace' and legacy_id=item->>'legacy_id';
    if mapped <> (item->>'entity_id')::uuid then raise exception 'Legacy mapping collision' using errcode='23505'; end if;
  end loop;
  return jsonb_build_object('status','ok','relationships_processed',n);
end $$;
revoke all on function public.tei_ingest_bundle(jsonb) from public, anon, authenticated;
grant execute on function public.tei_ingest_bundle(jsonb) to service_role;
revoke all on all functions in schema tei_private from public, anon, authenticated;
grant execute on all functions in schema tei_private to service_role;
