# T.E.I. v2

This directory documents the v2 runtime architecture.

## Source routing
- Company registration: MOEA/GCIS live open API.
- Directors/supervisors: Supabase Edge Function `directors-api`, backed by MOEA/GCIS live API.
- 165 anti-fraud and administrative penalties: source files remain in Supabase Storage; PostgreSQL is reserved for bounded indexes and metadata.
- PCC procurement: official API/query integration only; no full-archive PostgreSQL ingestion.
- Judicial decisions: official Judicial Yuan public search/API; evidence is observational and never treated as an automatic guilt finding.

## Storage rule
Do not use PostgreSQL as a raw-data archive. Raw government files belong in Storage. Store only normalized fields required for search, relationships, filtering, and evidence metadata.
