-- Covers relationship_types parent-key updates/deletes and type-only filters.
create index if not exists relationships_type_idx
  on public.relationships (relationship_type);
