-- MOF tax registrations are source observations, not proof of NGO legal form.
-- Do not create Entity or Relationship rows from names or tax IDs alone.
create table public.nonprofit_tax_observations (
  snapshot_sha256 text not null check (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  csv_row integer not null check (csv_row >= 2),
  uniform_number_raw text not null,
  identifier_valid boolean not null,
  unit_name text not null,
  office_county text,
  last_change_raw text,
  last_change_reason text,
  reason_description text,
  source_url text not null default 'https://data.gov.tw/dataset/34147',
  retrieved_at timestamptz not null,
  publication_status text not null default 'draft'
    check (publication_status in ('draft', 'published', 'withdrawn')),
  primary key (snapshot_sha256, csv_row)
);

create index nonprofit_tax_observations_id_idx
  on public.nonprofit_tax_observations (uniform_number_raw)
  where identifier_valid and publication_status = 'published';

alter table public.nonprofit_tax_observations enable row level security;
revoke all on public.nonprofit_tax_observations from anon, authenticated;
grant select on public.nonprofit_tax_observations to anon, authenticated;
grant all on public.nonprofit_tax_observations to service_role;
create policy nonprofit_tax_observations_public_read
  on public.nonprofit_tax_observations for select to anon, authenticated
  using (publication_status = 'published');
