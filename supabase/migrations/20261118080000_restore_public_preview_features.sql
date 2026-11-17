-- Preserve the separate restrictions on case, election and asset records.
create schema tei_source_checks;
revoke all on schema tei_source_checks from public;
grant usage on schema tei_source_checks to anon, authenticated;

create function tei_source_checks.has_legislator_identifier(politician uuid, official_number text)
returns boolean language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from public.entity_identifiers i
    join public.entities e on e.id = i.entity_id
    where i.entity_id = politician and i.namespace = 'tw:legislative_yuan:legislator_number'
      and i.value = official_number and i.confidence = 'EXACT'
      and e.entity_type = 'Politician' and e.publication_status = 'published'
  )
$$;
revoke all on function tei_source_checks.has_legislator_identifier(uuid,text) from public;
grant execute on function tei_source_checks.has_legislator_identifier(uuid,text) to anon, authenticated;

alter policy launch_graph_entities on public.entities using (
  entity_type in ('Company', 'Person', 'Politician', 'GovernmentOfficial',
    'GovernmentAgency', 'PoliticalParty', 'CivilOrganization', 'Contract',
    'LegislativeBill', 'LobbyingRecord')
  and identity_status in ('EXACT', 'SOURCE_SCOPED')
  and (entity_type <> 'Company' or identity_status = 'EXACT')
);

alter policy launch_graph_evidence on public.evidence_records using (
  source_class in ('Official Registry', 'Government Open Data', 'Primary Source')
  and source_url ~ '^https://([a-z0-9-]+\.)*gov\.tw(/|\?|$)'
  and source_locator <> '{}'::jsonb
  and source_name not in ('MOL/penalties', '申報對象官方登記識別 / Official counterparty register')
  and (source_name <> '監察院政治獻金公開查閱平臺' or (
    source_url ~ '^https://ardata\.cy\.gov\.tw(/|\?|$)'
    and source_locator->>'match_method' = 'exact_uniform_number'
    and source_locator->>'uniform_number' ~ '^[0-9]{8}$'
    and source_locator->>'politician_match_method' = 'exact_official_identifier'
    and source_locator->>'politician_identifier_namespace' = 'tw:legislative_yuan:legislator_number'
    and nullif(source_locator->>'politician_identifier_value', '') is not null
    and nullif(source_record_id, '') is not null
  ))
  and (source_name not like '內政部｜%遊說%' or source_url ~ '^https://ws\.moi\.gov\.tw/')
  and (source_name <> '政府電子採購網' or (
    source_locator->>'review_method' = 'official_row_compared_with_exact_bidder_id_and_award_role'
    and source_locator->>'winner' = 'true'
    and source_locator->>'bidder_uniform_number' ~ '^[0-9]{8}$'
  ))
);

alter policy launch_graph_relationships on public.relationships using (
  confidence in ('EXACT', 'HIGH')
  and exists (
    select 1 from public.evidence_records proof
    where proof.id = primary_evidence_id
      and (
        (relationship_type in ('DIRECTOR_OF', 'OFFICER_OF', 'EMPLOYED_BY')
          and proof.source_class = 'Official Registry')
        or (relationship_type in ('MEMBER_OF', 'LEGISLATOR_OF', 'COMMITTEE_MEMBER',
                 'PROPOSED_BILL', 'CO_SPONSORED_BILL')
          and proof.source_name = '立法院開放資料服務平台'
          and nullif(proof.source_locator->>'term', '') is not null
          and nullif(proof.source_locator->>'legislator_number', '') is not null)
        or (relationship_type = 'GOVERNMENT_POSITION'
          and proof.source_name = '行政院部會首長名錄（來源觀察）'
          and nullif(btrim(source_role), '') is not null)
        or (relationship_type = 'CONTRACT_WITH' and proof.source_name = '政府電子採購網'
          and exists (
            select 1 from public.entity_public_identifiers identifier
            where identifier.entity_id = source_entity_id and identifier.namespace = 'tw:uniform_number'
              and identifier.value = proof.source_locator->>'bidder_uniform_number'
          ))
        or (relationship_type = 'POLITICAL_CONTRIBUTION_TO'
          and proof.source_name = '監察院政治獻金公開查閱平臺'
          and exists (
            select 1 from public.entity_public_identifiers identifier
            where identifier.entity_id = source_entity_id and identifier.namespace = 'tw:uniform_number'
              and identifier.value = proof.source_locator->>'uniform_number'
          )
          and tei_source_checks.has_legislator_identifier(
            target_entity_id, proof.source_locator->>'politician_identifier_value'))
      )
  )
);

-- Expose an exact domain lookup from the official snapshot without granting
-- reads on the source archives or exposing the original raw payload.
create function tei_source_checks.domain_snapshot(snapshot_domain text) returns jsonb
language sql stable security definer set search_path = ''
as $$
  with snapshot as (
    select id, indexed_at, metadata, source_url
    from public.source_files
    where dataset = 'anti_fraud' and status = 'indexed'
      and source_url = 'https://data.gov.tw/dataset/176455'
      and char_length(snapshot_domain) <= 253
      and snapshot_domain ~ '^[a-z0-9-]+(\.[a-z0-9-]+)+$'
    order by indexed_at desc, id desc
    limit 1
  )
  select jsonb_build_object(
    'source_url', snapshot.source_url,
    'indexed_at', snapshot.indexed_at,
    'indexed_records', snapshot.metadata->'row_count',
    'records', coalesce((
      select jsonb_agg(hit.value order by hit.id)
      from (
        select record.id, jsonb_build_object(
          '網域', record.domain,
          '民國年月', record.raw->>'民國年月',
          '法律依據', record.raw->>'法律依據',
          '網站性質', record.raw->>'網站性質',
          '聲請單位', record.raw->>'聲請單位',
          'source_name', '165 警政署官方網域資料',
          'source_url', snapshot.source_url
        ) value
        from public.source_records record
        where record.dataset = 'anti_fraud'
          and record.source_file_id = snapshot.id and record.domain = snapshot_domain
        order by record.id
        limit 100
      ) hit
    ), '[]'::jsonb)
  )
  from snapshot
$$;
revoke all on function tei_source_checks.domain_snapshot(text) from public;
grant execute on function tei_source_checks.domain_snapshot(text) to anon, authenticated;

create function public.public_domain_snapshot(snapshot_domain text) returns jsonb
language sql stable security invoker set search_path = ''
as $$ select tei_source_checks.domain_snapshot(snapshot_domain) $$;
revoke all on function public.public_domain_snapshot(text) from public;
grant execute on function public.public_domain_snapshot(text) to anon, authenticated;
