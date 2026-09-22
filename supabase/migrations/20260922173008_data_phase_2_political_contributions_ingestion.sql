-- DATA Phase 2: identifier-only political-contribution ingestion.
-- No new public table is needed: contributions remain canonical Relationships
-- backed by immutable Evidence. This wrapper accepts only bounded draft bundles.
create function public.tei_ingest_political_contribution_bundle(bundle jsonb) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare item jsonb; locator jsonb;
begin
  if jsonb_typeof(bundle) <> 'object' or octet_length(bundle::text) > 1048576 then
    raise exception 'Invalid or oversized political contribution bundle' using errcode='22023';
  end if;
  if jsonb_array_length(coalesce(bundle->'relationships','[]')) > 200
     or jsonb_array_length(coalesce(bundle->'evidence','[]')) > 400 then
    raise exception 'Political contribution bundle exceeds row limits' using errcode='22023';
  end if;
  if jsonb_array_length(coalesce(bundle->'entities','[]')) <> 0
     or jsonb_array_length(coalesce(bundle->'identifiers','[]')) <> 0 then
    raise exception 'Political contribution ingestion cannot create or resolve entities'
      using errcode='22023';
  end if;
  for item in select value from jsonb_array_elements(coalesce(bundle->'relationships','[]')) loop
    if item->>'relationship_type' <> 'POLITICAL_CONTRIBUTION_TO'
       or coalesce(item->>'status','draft') <> 'draft'
       or item->>'confidence' <> 'EXACT' then
      raise exception 'Political contribution ingestion accepts exact draft edges only'
        using errcode='22023';
    end if;
  end loop;
  for item in select value from jsonb_array_elements(coalesce(bundle->'evidence','[]')) loop
    locator := item->'source_locator';
    if coalesce(item->>'publication_status','draft') <> 'draft'
       or nullif(btrim(item->>'source_record_id'),'') is null
       or nullif(btrim(item->>'source_url'),'') is null
       or locator->>'match_method' <> 'exact_uniform_number'
       or locator->>'uniform_number' !~ '^[0-9]{8}$'
       or locator->>'politician_match_method' <> 'exact_official_identifier'
       or nullif(btrim(locator->>'politician_identifier_namespace'),'') is null
       or nullif(btrim(locator->>'politician_identifier_value'),'') is null
       or nullif(btrim(locator->>'contribution_year'),'') is null then
      raise exception 'Political contribution Evidence lacks exact identity or provenance'
        using errcode='22023';
    end if;
  end loop;
  return public.tei_ingest_bundle(bundle);
end $$;

revoke all on function public.tei_ingest_political_contribution_bundle(jsonb)
  from public, anon, authenticated;
grant execute on function public.tei_ingest_political_contribution_bundle(jsonb) to service_role;

create or replace function tei_private.validate_political_contribution() returns trigger
language plpgsql set search_path = '' as $$
declare source_record public.entities; target_record public.entities;
  proof public.evidence_records; matched_uniform text;
  politician_namespace text; politician_value text;
begin
  if new.relationship_type <> 'POLITICAL_CONTRIBUTION_TO' or new.status <> 'published' then
    return null;
  end if;
  select * into source_record from public.entities where id = new.source_entity_id for share;
  select * into target_record from public.entities where id = new.target_entity_id for share;
  select * into proof from public.evidence_records where id = new.primary_evidence_id for share;
  matched_uniform := proof.source_locator->>'uniform_number';
  politician_namespace := proof.source_locator->>'politician_identifier_namespace';
  politician_value := proof.source_locator->>'politician_identifier_value';
  if source_record.entity_type <> 'Company' or target_record.entity_type <> 'Politician' then
    raise exception 'Published political contribution must link Company to Politician'
      using errcode='23514';
  end if;
  if new.amount is null or new.amount <= 0 or new.currency <> 'TWD'
     or new.start_date is null or new.date_precision <> 'day'
     or new.source_role is null or btrim(new.source_role) = '' then
    raise exception 'Published political contribution requires amount, date and contribution type'
      using errcode='23514';
  end if;
  if proof.status <> 'active' or proof.publication_status <> 'published'
     or proof.source_record_id is null or btrim(proof.source_record_id) = ''
     or proof.source_url is null or btrim(proof.source_url) = ''
     or proof.retrieved_at is null
     or proof.source_locator->>'match_method' <> 'exact_uniform_number'
     or matched_uniform !~ '^[0-9]{8}$'
     or proof.source_locator->>'politician_match_method' <> 'exact_official_identifier'
     or nullif(btrim(proof.source_locator->>'contribution_year'),'') is null
     or not exists (
       select 1 from public.entity_identifiers identifier
       where identifier.entity_id = new.source_entity_id
         and identifier.namespace = 'tw:uniform_number'
         and identifier.value = matched_uniform
         and identifier.confidence = 'EXACT')
     or not exists (
       select 1 from public.entity_identifiers identifier
       where identifier.entity_id = new.target_entity_id
         and identifier.namespace = politician_namespace
         and identifier.value = politician_value
         and identifier.confidence = 'EXACT') then
    raise exception 'Published political contribution requires exact identifiers and Evidence'
      using errcode='23514';
  end if;
  return null;
end $$;
