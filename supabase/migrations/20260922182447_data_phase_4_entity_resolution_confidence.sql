-- DATA Phase 4: traceable confidence scoring without automatic Entity merges.
alter table public.resolution_candidates
  add column score numeric(4,3) not null default 0
    check (score between 0 and 1 and score <> 'NaN'::numeric),
  add column signals jsonb not null default '{}'
    check (jsonb_typeof(signals) = 'object'),
  add column matching_evidence_ids uuid[] not null default '{}',
  add column engine_version text not null default 'legacy'
    check (btrim(engine_version) <> ''),
  add column decided_at timestamptz,
  add column decision_reason text;

update public.resolution_candidates set
  score = case confidence when 'EXACT' then 1 when 'HIGH' then 0.8
         when 'MEDIUM' then 0.5 when 'LOW' then 0.25 else 0 end,
  signals = jsonb_build_object('legacy_reason',reason),
  matching_evidence_ids = array[evidence_id],
  decided_at = case when status <> 'pending' then created_at else null end,
  decision_reason = case when status <> 'pending' then 'legacy decision' else null end;

alter table public.resolution_candidates add constraint resolution_evidence_complete
  check (evidence_id = any(matching_evidence_ids) and cardinality(matching_evidence_ids) between 1 and 20);
alter table public.resolution_candidates add constraint resolution_decision_complete
  check ((status = 'pending' and decided_at is null and decision_reason is null)
      or (status in ('accepted','rejected') and decided_at is not null
          and length(btrim(decision_reason)) between 1 and 1000));
alter table public.resolution_candidates add constraint resolution_acceptance_threshold
  check (status <> 'accepted' or confidence in ('EXACT','HIGH'));
alter table public.resolution_candidates add constraint resolution_score_band
  check ((confidence = 'EXACT' and score = 1)
      or (confidence = 'HIGH' and score >= 0.75 and score < 1)
      or (confidence = 'MEDIUM' and score >= 0.5 and score < 0.75)
      or (confidence = 'LOW' and score >= 0.25 and score < 0.5)
      or (confidence = 'UNRESOLVED' and score < 0.25));

create unique index resolution_candidates_engine_pair_idx
  on public.resolution_candidates(source_entity_id,candidate_entity_id,evidence_id,engine_version)
  nulls not distinct;
create index resolution_candidates_status_confidence_idx
  on public.resolution_candidates(status,confidence,id);

create function tei_private.validate_resolution_candidate() returns trigger
language plpgsql set search_path = '' as $$
declare source_type text; candidate_type text; evidence_count integer;
begin
  select entity_type into source_type from public.entities where id = new.source_entity_id;
  if new.candidate_entity_id is not null then
    select entity_type into candidate_type from public.entities where id = new.candidate_entity_id;
    if candidate_type is distinct from source_type then
      raise exception 'Resolution candidates must have the same Entity type'
        using errcode='23514';
    end if;
  end if;
  select count(*) into evidence_count from public.evidence_records
    where id = any(new.matching_evidence_ids);
  if evidence_count <> cardinality(new.matching_evidence_ids) then
    raise exception 'Resolution matching Evidence is incomplete' using errcode='23514';
  end if;
  if new.confidence = 'EXACT'
     and coalesce(jsonb_array_length(new.signals->'shared_exact_identifiers'),0) = 0 then
    raise exception 'EXACT resolution requires a shared official identifier'
      using errcode='23514';
  end if;
  if new.confidence in ('HIGH','MEDIUM')
     and new.signals->>'normalized_name_match' = 'true'
     and coalesce(jsonb_array_length(new.signals->'shared_company_ids'),0) = 0
     and coalesce(jsonb_array_length(new.signals->'shared_roles'),0) = 0
     and coalesce((new.signals->>'time_overlap')::boolean,false) = false then
    raise exception 'Names alone cannot create medium/high resolution confidence'
      using errcode='23514';
  end if;
  return new;
end $$;

create trigger resolution_candidate_valid
before insert or update on public.resolution_candidates
for each row execute function tei_private.validate_resolution_candidate();

create function tei_private.immutable_resolution_candidate() returns trigger
language plpgsql set search_path = '' as $$
begin
  if (to_jsonb(new) - array['status','decided_at','decision_reason'])
     is distinct from
     (to_jsonb(old) - array['status','decided_at','decision_reason']) then
    raise exception 'Resolution matching evidence is immutable; create a new candidate'
      using errcode='23514';
  end if;
  return new;
end $$;

create trigger resolution_candidate_immutable
before update on public.resolution_candidates
for each row execute function tei_private.immutable_resolution_candidate();

create function public.tei_ingest_resolution_candidates(bundle jsonb) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare item jsonb; existing public.resolution_candidates; processed integer := 0;
begin
  if jsonb_typeof(bundle) <> 'object' or octet_length(bundle::text) > 1048576
     or jsonb_array_length(coalesce(bundle->'resolution_candidates','[]')) > 200 then
    raise exception 'Invalid or oversized resolution candidate bundle' using errcode='22023';
  end if;
  if (bundle - 'resolution_candidates') <> '{}'::jsonb then
    raise exception 'Resolution ingestion accepts candidate records only' using errcode='22023';
  end if;
  for item in select value from jsonb_array_elements(coalesce(bundle->'resolution_candidates','[]')) loop
    if coalesce(item->>'status','pending') <> 'pending'
       or item->>'engine_version' <> 'tei-resolution-v1'
       or item->>'confidence' not in ('EXACT','HIGH','MEDIUM','LOW','UNRESOLVED') then
      raise exception 'Resolution ingestion accepts pending v1 candidates only'
        using errcode='22023';
    end if;
    select * into existing from public.resolution_candidates where id=(item->>'id')::uuid;
    if found and (
       existing.source_entity_id <> (item->>'source_entity_id')::uuid
       or existing.candidate_entity_id is distinct from (item->>'candidate_entity_id')::uuid
       or existing.confidence <> item->>'confidence'
       or existing.score <> (item->>'score')::numeric
       or existing.reason <> item->>'reason'
       or existing.signals <> item->'signals'
       or existing.evidence_id <> (item->>'evidence_id')::uuid
       or existing.matching_evidence_ids <> array(
         select jsonb_array_elements_text(item->'matching_evidence_ids')::uuid)
       or existing.engine_version <> item->>'engine_version') then
      raise exception 'Resolution candidate identity collision' using errcode='23505';
    end if;
    insert into public.resolution_candidates(
      id,source_entity_id,candidate_entity_id,confidence,score,reason,signals,
      evidence_id,matching_evidence_ids,engine_version,status)
    values ((item->>'id')::uuid,(item->>'source_entity_id')::uuid,
      (item->>'candidate_entity_id')::uuid,item->>'confidence',(item->>'score')::numeric,
      item->>'reason',item->'signals',(item->>'evidence_id')::uuid,
      array(select jsonb_array_elements_text(item->'matching_evidence_ids')::uuid),
      item->>'engine_version','pending') on conflict(id) do nothing;
    processed := processed + 1;
  end loop;
  return jsonb_build_object('status','ok','resolution_candidates_processed',processed);
end $$;

revoke all on function public.tei_ingest_resolution_candidates(jsonb)
  from public, anon, authenticated;
grant execute on function public.tei_ingest_resolution_candidates(jsonb) to service_role;
revoke all on function tei_private.validate_resolution_candidate()
  from public, anon, authenticated;
revoke all on function tei_private.immutable_resolution_candidate()
  from public, anon, authenticated;
grant execute on function tei_private.validate_resolution_candidate() to service_role;
grant execute on function tei_private.immutable_resolution_candidate() to service_role;
