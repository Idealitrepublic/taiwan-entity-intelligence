-- Withdraw public access while retaining the original rows and references.
-- Restrictive policies are combined with all existing permissive policies.
create policy withheld_election_source_files on public.source_files
as restrictive for select to anon, authenticated
using (dataset <> 'cec-2026-local-election-registration');

create policy withheld_election_source_records on public.source_records
as restrictive for select to anon, authenticated
using (dataset <> 'cec-2026-local-election-registration');

create policy withheld_asset_declarations on public.asset_declarations
as restrictive for select to anon, authenticated
using (false);

create policy withheld_declaration_entities on public.entities
as restrictive for select to anon, authenticated
using (entity_type <> 'AssetDeclaration' and source <> 'cec-2026-local-election-registration');

create policy withheld_declaration_relationships on public.relationships
as restrictive for select to anon, authenticated
using (relationship_type not in ('ASSET_OWNERSHIP', 'BUSINESS_INVESTMENT'));

create policy withheld_declaration_evidence on public.evidence_records
as restrictive for select to anon, authenticated
using (source_name not in (
  'cec-2026-local-election-registration',
  '監察院廉政專刊財產申報資料',
  '財產申報公司識別覆核 / Asset issuer identity review',
  '財產申報公司識別核准 / Asset issuer resolution approval'
));

create policy withheld_declaration_alerts on public.watchlist_events
as restrictive for all to authenticated
using (source_kind <> 'ASSET_DECLARATION')
with check (source_kind <> 'ASSET_DECLARATION');
