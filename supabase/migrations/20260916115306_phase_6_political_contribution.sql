-- Phase 6 keeps contributions as evidence-backed Company -> Politician edges.
-- Publication is allowed only when the donor company was resolved by exact 統編.
create function tei_private.validate_political_contribution() returns trigger
language plpgsql set search_path = '' as $$
declare source_record public.entities; target_record public.entities;
  proof public.evidence_records; matched_uniform text;
begin
  if new.relationship_type <> 'POLITICAL_CONTRIBUTION_TO' or new.status <> 'published' then
    return null;
  end if;
  select * into source_record from public.entities where id = new.source_entity_id for share;
  select * into target_record from public.entities where id = new.target_entity_id for share;
  select * into proof from public.evidence_records where id = new.primary_evidence_id for share;
  matched_uniform := proof.source_locator->>'uniform_number';
  if source_record.entity_type <> 'Company' or target_record.entity_type <> 'Politician' then
    raise exception 'Published political contribution must link Company to Politician'
      using errcode = '23514';
  end if;
  if new.amount is null or new.amount <= 0 or new.currency <> 'TWD'
     or new.start_date is null or new.date_precision <> 'day'
     or new.source_role is null or btrim(new.source_role) = '' then
    raise exception 'Published political contribution requires amount, date and contribution type'
      using errcode = '23514';
  end if;
  if proof.status <> 'active' or proof.publication_status <> 'published'
     or proof.source_record_id is null or btrim(proof.source_record_id) = ''
     or proof.source_locator->>'match_method' <> 'exact_uniform_number'
     or matched_uniform !~ '^[0-9]{8}$'
     or not exists (
       select 1 from public.entity_identifiers identifier
       where identifier.entity_id = new.source_entity_id
         and identifier.namespace = 'tw:uniform_number'
         and identifier.value = matched_uniform
         and identifier.confidence = 'EXACT'
     ) then
    raise exception 'Published political contribution requires exact uniform-number Evidence'
      using errcode = '23514';
  end if;
  return null;
end $$;

create constraint trigger political_contributions_valid
after insert or update on public.relationships
deferrable initially deferred for each row
execute function tei_private.validate_political_contribution();

create function public.political_contributions_for_entity(
  focus_entity_id uuid,
  result_limit integer default 25,
  after_relationship_id uuid default null
) returns table (
  focus_entity jsonb,
  relationship jsonb,
  company_entity jsonb,
  politician_entity jsonb,
  primary_evidence jsonb
)
language plpgsql
stable
security invoker
set search_path = ''
as $$
begin
  if result_limit is null or result_limit < 1 or result_limit > 25 then
    raise exception 'Political contribution result limit must be between 1 and 25'
      using errcode = '22023';
  end if;
  return query
  select jsonb_build_object(
           'id', focus.id, 'entity_type', focus.entity_type,
           'canonical_name', focus.canonical_name, 'display_name', focus.display_name,
           'identity_status', focus.identity_status
         ),
         case when contribution.relationship_id is null then null else jsonb_build_object(
           'id', contribution.relationship_id,
           'source_entity_id', contribution.company_id,
           'target_entity_id', contribution.politician_id,
           'relationship_type', 'POLITICAL_CONTRIBUTION_TO',
           'primary_evidence_id', contribution.evidence_id,
           'start_date', contribution.contribution_date,
           'end_date', null,
           'date_precision', 'day',
           'observed_at', contribution.observed_at,
           'amount', contribution.amount,
           'currency', contribution.currency,
           'percentage', null,
           'quantity', null,
           'quantity_unit', null,
           'source_role', contribution.contribution_type,
           'confidence', contribution.confidence,
           'status', contribution.relationship_status
         ) end,
         case when contribution.relationship_id is null then null else jsonb_build_object(
           'id', contribution.company_id, 'entity_type', 'Company',
           'canonical_name', contribution.company_canonical_name,
           'display_name', contribution.company_display_name,
           'identity_status', contribution.company_identity_status
         ) end,
         case when contribution.relationship_id is null then null else jsonb_build_object(
           'id', contribution.politician_id, 'entity_type', 'Politician',
           'canonical_name', contribution.politician_canonical_name,
           'display_name', contribution.politician_display_name,
           'identity_status', contribution.politician_identity_status
         ) end,
         case when contribution.relationship_id is null then null else jsonb_build_object(
           'id', contribution.evidence_id,
           'source_name', contribution.evidence_source_name,
           'source_record_id', contribution.evidence_source_record_id,
           'source_class', contribution.evidence_source_class,
           'source_url', contribution.evidence_source_url,
           'source_locator', contribution.evidence_source_locator,
           'title', contribution.evidence_title,
           'summary', contribution.evidence_summary,
           'observed_at', contribution.evidence_observed_at,
           'retrieved_at', contribution.evidence_retrieved_at,
           'content_hash', contribution.evidence_content_hash,
           'status', contribution.evidence_status
         ) end
    from public.entities focus
    left join lateral (
      select r.id relationship_id, r.observed_at, r.amount, r.currency,
             r.start_date contribution_date, r.source_role contribution_type,
             r.confidence, r.status relationship_status,
             company.id company_id, company.canonical_name company_canonical_name,
             company.display_name company_display_name,
             company.identity_status company_identity_status,
             politician.id politician_id,
             politician.canonical_name politician_canonical_name,
             politician.display_name politician_display_name,
             politician.identity_status politician_identity_status,
             evidence.id evidence_id, evidence.source_name evidence_source_name,
             evidence.source_record_id evidence_source_record_id,
             evidence.source_class evidence_source_class,
             evidence.source_url evidence_source_url,
             evidence.source_locator evidence_source_locator,
             evidence.title evidence_title, evidence.summary evidence_summary,
             evidence.observed_at evidence_observed_at,
             evidence.retrieved_at evidence_retrieved_at,
             evidence.content_hash evidence_content_hash,
             evidence.status evidence_status
        from public.relationships r
        join public.entities company on company.id = r.source_entity_id
        join public.entities politician on politician.id = r.target_entity_id
        join public.evidence_records evidence on evidence.id = r.primary_evidence_id
       where (r.source_entity_id = focus.id or r.target_entity_id = focus.id)
         and r.relationship_type = 'POLITICAL_CONTRIBUTION_TO'
         and r.status = 'published'
         and r.amount > 0 and r.currency = 'TWD'
         and r.start_date is not null and r.date_precision = 'day'
         and btrim(r.source_role) <> ''
         and company.entity_type = 'Company' and company.publication_status = 'published'
         and politician.entity_type = 'Politician' and politician.publication_status = 'published'
         and evidence.status = 'active' and evidence.publication_status = 'published'
         and evidence.source_locator->>'match_method' = 'exact_uniform_number'
         and (after_relationship_id is null or r.id > after_relationship_id)
       order by r.id
       limit result_limit + 1
    ) contribution on true
   where focus.id = focus_entity_id
     and focus.entity_type in ('Company','Politician')
     and focus.publication_status = 'published'
   order by contribution.relationship_id nulls first;
end $$;

comment on function public.political_contributions_for_entity(uuid,integer,uuid) is
  'Bounded bidirectional Company/Politician contribution projection; published edges require exact uniform-number evidence.';
revoke all on function public.political_contributions_for_entity(uuid,integer,uuid) from public;
grant execute on function public.political_contributions_for_entity(uuid,integer,uuid)
  to anon, authenticated, service_role;
