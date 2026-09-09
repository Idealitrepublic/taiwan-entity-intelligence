# Phase 1: Entity / Relationship / Evidence

Status: implementation on `feature/entity-model`; review before merge and production migration.

## Scope before implementation

- Add stable UUID entity identities, namespaced identifiers, aliases, source mapping,
  evidence versions, typed temporal relationships and unresolved candidates.
- Add SQL migrations, Python contracts/adapters, bounded read API and dry-run backfill.
- Preserve every existing company endpoint and HTML interface.
- Do not implement global search, multi-hop graph, path finding or political ingestion.
- Do not reuse name-based person joins. A legacy director row becomes a source-scoped
  person observation, not a verified identity across companies.

## Planned files

`supabase/migrations/`, `src/entities/`, `src/relationships/`, `app.py`,
`scripts/backfill_entity_model.py`, `scripts/build_check.py`, `scripts/check_web_syntax.cjs`,
`tests/test_entity_model.py`, `tests/test_entity_api.py`, `tests/entity_schema.test.mjs`,
development commands, CI and this documentation.

## Database

Add tables only; no old tables altered or removed. UUID foreign keys, namespaced
identifier uniqueness, temporal / amount constraints, RLS and explicit grants.
Evidence is immutable apart from status / publication; relationships must keep a
supporting evidence record. Low confidence is never a published relationship.
Backfill is bounded, dry-run by default and records the original fetched timestamp.

## API / UI

Add `/api/v1/entities/{uuid}`, `/api/v1/relationships/{uuid}` and
`/api/v1/evidence/{uuid}`, plus bounded entity relationships. No name search yet.
New API is gated by `TEI_ENTITY_API_ENABLED=1`; old APIs retain exact contracts.
No frontend redesign. Public responses only include approved fields.

## Risks and acceptance

Same-name ambiguity; missing historical dates; generic source URLs; version/retraction
handling; legacy response compatibility; production/preview separation.
Test these in isolated PostgreSQL before considering production changes.

The project is Python, not Next.js. npm scripts wrap actual Python lint, application
bundle validation, Python tests, PostgreSQL WASM tests and the WSGI development server.
`npm run build` is a local source/bundle check; Vercel preview is the deployment build gate.
