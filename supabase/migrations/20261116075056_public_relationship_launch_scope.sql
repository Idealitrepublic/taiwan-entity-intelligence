-- Keep source archives for internal review and constrain every public reader.
-- Restrictive policies apply to PostgREST as well as SECURITY INVOKER graph RPCs.
create policy launch_graph_entities on public.entities
as restrictive for select to anon, authenticated using (
  entity_type in ('Company', 'Person', 'Politician', 'GovernmentOfficial',
    'GovernmentAgency', 'PoliticalParty', 'CivilOrganization', 'Contract', 'LegislativeBill')
  and identity_status in ('EXACT', 'SOURCE_SCOPED')
  and (entity_type <> 'Company' or identity_status = 'EXACT')
);

create policy launch_graph_evidence on public.evidence_records
as restrictive for select to anon, authenticated using (
  source_class in ('Official Registry', 'Government Open Data', 'Primary Source')
  and source_url ~ '^https://([a-z0-9-]+\.)*(gov\.tw|ly\.gov\.tw)(/|\?|$)'
  and source_locator <> '{}'::jsonb
  and source_name not in ('MOL/penalties', '監察院政治獻金公開查閱平臺',
    '申報對象官方登記識別 / Official counterparty register')
  and source_name not like '內政部｜%遊說%'
  and (source_name <> '政府電子採購網' or (
    source_locator->>'review_method' = 'official_row_compared_with_exact_bidder_id_and_award_role'
    and source_locator->>'winner' = 'true'
    and source_locator->>'bidder_uniform_number' ~ '^[0-9]{8}$'
  ))
);

create policy launch_graph_relationships on public.relationships
as restrictive for select to anon, authenticated using (
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
      )
  )
);

create policy launch_graph_source_files on public.source_files
as restrictive for select to anon, authenticated using (
  dataset = 'moea_officers' and status = 'indexed'
  and source_url ~ '^https://([a-z0-9-]+\.)*gov\.tw(/|\?|$)'
);

create policy launch_graph_source_records on public.source_records
as restrictive for select to anon, authenticated using (
  dataset = 'moea_officers' and uniform_number ~ '^[0-9]{8}$' and exists (
    select 1 from public.source_files f where f.id = source_file_id and f.dataset = 'moea_officers'
  )
);

create policy launch_graph_legacy_evidence on public.evidence
as restrictive for select to anon, authenticated using (false);

create policy launch_graph_alerts on public.watchlist_events
as restrictive for select to authenticated using (
  source_kind = 'RELATIONSHIP' and exists (
    select 1 from public.relationships r where r.id = relationship_id
  )
);

-- The app can reject reads when pointed at an older database.
create function public.public_graph_scope_version() returns table (version integer)
language sql stable security invoker set search_path = ''
as $$ select 1 $$;
revoke all on function public.public_graph_scope_version() from public;
grant execute on function public.public_graph_scope_version() to anon, authenticated;
