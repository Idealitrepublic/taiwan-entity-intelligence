-- Phase 9 adds private, owner-scoped investigation workspaces. These tables
-- are never public: every operation requires an authenticated Supabase user.
create table public.investigation_workspaces (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name text not null check (length(btrim(name)) between 1 and 120),
  description text check (description is null or length(description) <= 2000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, owner_user_id)
);

create table public.workspace_items (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  owner_user_id uuid not null default auth.uid(),
  created_by_user_id uuid not null default auth.uid(),
  item_type text not null check (item_type in (
    'ENTITY','RELATIONSHIP','EVIDENCE','GRAPH','SOURCE','NOTE')),
  entity_id uuid references public.entities(id),
  relationship_id uuid references public.relationships(id),
  evidence_id uuid references public.evidence_records(id),
  graph_root_entity_id uuid references public.entities(id),
  source_url text,
  title text check (title is null or length(btrim(title)) between 1 and 500),
  note_text text check (note_text is null or length(btrim(note_text)) between 1 and 10000),
  metadata jsonb not null default '{}'::jsonb
    check (jsonb_typeof(metadata) = 'object' and octet_length(metadata::text) <= 8192),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint workspace_items_workspace_owner_fkey
    foreign key (workspace_id, owner_user_id)
    references public.investigation_workspaces(id, owner_user_id) on delete cascade,
  check (created_by_user_id = owner_user_id),
  check (source_url is null or (length(source_url) <= 2048
    and source_url ~ '^https?://[^[:space:]/?#]+([/?#][^[:space:]]*)?$')),
  check (
    (item_type = 'ENTITY' and entity_id is not null and relationship_id is null
      and evidence_id is null and graph_root_entity_id is null and source_url is null
      and note_text is null)
    or (item_type = 'RELATIONSHIP' and relationship_id is not null and entity_id is null
      and evidence_id is null and graph_root_entity_id is null and source_url is null
      and note_text is null)
    or (item_type = 'EVIDENCE' and evidence_id is not null and entity_id is null
      and relationship_id is null and graph_root_entity_id is null and source_url is null
      and note_text is null)
    or (item_type = 'GRAPH' and graph_root_entity_id is not null and entity_id is null
      and relationship_id is null and evidence_id is null and source_url is null
      and note_text is null)
    or (item_type = 'SOURCE' and source_url is not null and entity_id is null
      and relationship_id is null and evidence_id is null and graph_root_entity_id is null
      and note_text is null)
    or (item_type = 'NOTE' and note_text is not null and entity_id is null
      and relationship_id is null and evidence_id is null and graph_root_entity_id is null
      and source_url is null)
  )
);

create index investigation_workspaces_owner_updated_idx
  on public.investigation_workspaces (owner_user_id, updated_at desc, id);
create index workspace_items_workspace_created_idx
  on public.workspace_items (workspace_id, created_at desc, id);
create index workspace_items_owner_type_idx
  on public.workspace_items (owner_user_id, item_type, id);

create trigger investigation_workspaces_touch_updated_at before update
on public.investigation_workspaces for each row
execute function tei_private.touch_updated_at();
create trigger workspace_items_touch_updated_at before update
on public.workspace_items for each row
execute function tei_private.touch_updated_at();

alter table public.investigation_workspaces enable row level security;
alter table public.workspace_items enable row level security;

revoke all on table public.investigation_workspaces from anon, authenticated;
revoke all on table public.workspace_items from anon, authenticated;
grant select, insert, update, delete on table public.investigation_workspaces to authenticated;
grant select, insert, update, delete on table public.workspace_items to authenticated;

create policy investigation_workspaces_owner_select
on public.investigation_workspaces for select to authenticated
using ((select auth.uid()) = owner_user_id);
create policy investigation_workspaces_owner_insert
on public.investigation_workspaces for insert to authenticated
with check ((select auth.uid()) = owner_user_id);
create policy investigation_workspaces_owner_update
on public.investigation_workspaces for update to authenticated
using ((select auth.uid()) = owner_user_id)
with check ((select auth.uid()) = owner_user_id);
create policy investigation_workspaces_owner_delete
on public.investigation_workspaces for delete to authenticated
using ((select auth.uid()) = owner_user_id);

create policy workspace_items_owner_select
on public.workspace_items for select to authenticated
using ((select auth.uid()) = owner_user_id);
create policy workspace_items_owner_insert
on public.workspace_items for insert to authenticated
with check (
  (select auth.uid()) = owner_user_id
  and (select auth.uid()) = created_by_user_id
);
create policy workspace_items_owner_update
on public.workspace_items for update to authenticated
using ((select auth.uid()) = owner_user_id)
with check (
  (select auth.uid()) = owner_user_id
  and (select auth.uid()) = created_by_user_id
);
create policy workspace_items_owner_delete
on public.workspace_items for delete to authenticated
using ((select auth.uid()) = owner_user_id);
