-- Restrict public access while retaining original records and references.
create policy omit_case_source_files on public.source_files
as restrictive for select to anon, authenticated using (
  dataset not in ('penalties', 'judicial', 'labor_penalties')
);

create policy omit_case_source_records on public.source_records
as restrictive for select to anon, authenticated using (
  dataset not in ('penalties', 'judicial', 'labor_penalties')
);

create policy omit_case_legacy_evidence on public.evidence
as restrictive for select to anon, authenticated using (
  source_type not in ('judicial', 'administrative_penalty', 'labor_penalty', 'penalties')
);

create policy omit_case_entities on public.entities
as restrictive for select to anon, authenticated using (
  entity_type not in ('Judgment', 'Penalty')
);

create policy omit_case_evidence on public.evidence_records
as restrictive for select to anon, authenticated using (
  source_class <> 'Court Record' and source_name <> 'MOL/penalties'
);

create policy omit_case_relationships on public.relationships
as restrictive for select to anon, authenticated using (
  relationship_type not in ('RELATED_TO_JUDGMENT', 'RELATED_TO_PENALTY')
);

create policy omit_case_alerts on public.watchlist_events
as restrictive for select to authenticated using (
  event_type not in ('JUDGMENT', 'PENALTY')
);
