-- Cover the new crosswalk foreign keys and make service-only policy explicit.
create index political_identity_crosswalks_company_idx
  on public.political_identity_crosswalks(company_entity_id)
  where company_entity_id is not null;
create index political_identity_crosswalks_source_evidence_idx
  on public.political_identity_crosswalks(source_evidence_id);
create index political_identity_crosswalks_master_evidence_idx
  on public.political_identity_crosswalks(master_evidence_id);
create policy service_access on public.political_identity_crosswalks
  for all to service_role using (true) with check (true);
