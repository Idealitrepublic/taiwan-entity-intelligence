create table if not exists public.source_files (
  id uuid primary key default gen_random_uuid(),
  dataset text not null,
  object_path text not null unique,
  file_name text not null,
  format text,
  size_bytes bigint,
  sha256 text,
  source_url text,
  downloaded_at timestamptz,
  indexed_at timestamptz,
  status text not null default 'uploaded' check (status in ('uploaded','indexed','failed','archived')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_source_files_dataset on public.source_files(dataset);
create index if not exists idx_source_files_status on public.source_files(status);

create table if not exists public.evidence (
  id uuid primary key default gen_random_uuid(),
  entity_type text not null,
  entity_key text not null,
  source_type text not null,
  source_ref text not null,
  title text,
  event_date date,
  url text,
  summary text,
  risk_tags text[] not null default '{}',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(entity_type, entity_key, source_type, source_ref)
);

create index if not exists idx_evidence_entity on public.evidence(entity_type, entity_key);
create index if not exists idx_evidence_source on public.evidence(source_type);
create index if not exists idx_evidence_date on public.evidence(event_date desc);

alter table public.source_files enable row level security;
alter table public.evidence enable row level security;

grant select on public.source_files to anon, authenticated;
grant select on public.evidence to anon, authenticated;

drop policy if exists "source_files_public_read" on public.source_files;
create policy "source_files_public_read" on public.source_files for select to anon, authenticated using (true);

drop policy if exists "evidence_public_read" on public.evidence;
create policy "evidence_public_read" on public.evidence for select to anon, authenticated using (true);

insert into storage.buckets (id, name, public)
values ('tei-raw', 'tei-raw', false)
on conflict (id) do nothing;;
