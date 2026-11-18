-- Withdraw lobbying publication while preserving source rows and private references.
create policy withheld_lobby_entities on public.entities
as restrictive for select to anon, authenticated
using (entity_type <> 'LobbyingRecord');

create policy withheld_lobby_evidence on public.evidence_records
as restrictive for select to anon, authenticated
using (
  source_name not like '內政部｜%遊說%'
);

create policy withheld_lobby_alerts on public.watchlist_events
as restrictive for select to authenticated
using (exists (
  select 1 from public.entities entity where entity.id = watchlist_events.entity_id
));
