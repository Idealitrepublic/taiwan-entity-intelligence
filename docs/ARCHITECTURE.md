# T.E.I. architecture and Phase 0 repository audit

Status: audited 2026-09-16 on branch `chore/local-dev-setup`, based on `main` commit `688f4c7`.

## System context

T.E.I. turns Taiwanese public records into an investigation workspace. The canonical request path is:

```text
Browser (`web/index.html`)
  -> Python WSGI (`app.py`, `app:app`)
     -> Entity API (`src/entities/api.py`)
        -> Supabase Data API/RPC (`src/entities/repository.py`)
     -> Company investigation (`src/cloud_company.py`)
        -> MOEA registry/directors APIs
        -> Supabase legacy evidence tables
        -> procurement, penalties, judicial and fraud/domain adapters
  -> JSON response
  -> browser panels and SVG graph
```

The deployed service is Python, not Next.js. `package.json` exists only to provide repeatable development checks and the PGlite schema test.

## Runtime and deployment

- Vercel framework: Python; WSGI entry point `app:app`.
- Local runtime: Python 3.12+, Node 22+; local port 3000.
- Vercel project setting observed during Phase 0: Node 24.x.
- Production is Git-integrated from `Idealitrepublic/taiwan-entity-intelligence`, branch `main`.
- Supabase is accessed over HTTP with a public read credential for browser/API reads. Service-role access is restricted to ingestion/backfill paths.

## Application boundaries

| Boundary | Canonical implementation | Responsibility |
|---|---|---|
| Web entry | `web/index.html` | bilingual search and investigation workspace |
| WSGI routing | `app.py` | page/static delivery, status, company, procurement, Entity API dispatch |
| Entity read API | `src/entities/api.py` | validation and stable `/api/v1` response envelope |
| Entity repository | `src/entities/repository.py` | RLS-aware REST/RPC reads with anon credentials |
| Company aggregation | `src/cloud_company.py` | live registry plus evidence-source aggregation |
| Graph expansion | `graph_entity_neighbors` RPC | bounded, cursor-based one-hop expansion |
| Ingestion | scripts and Supabase Edge Functions | privileged source sync and persistence |

## Verified Phase 0 baseline

- `npm run dev`: starts on `127.0.0.1:3000`.
- `npm run build`: validates 36 Python modules, WSGI entry point, UI, and required assets.
- Supabase status: connected; local status reported 611 source files, 3 companies, 34 people, 37 entity evidence rows, and 270,011 source records.
- Search: `全家便利` returns the published company entity.
- Company investigation: `23060248` returns 15 people and 48 evidence items.
- Procurement: 99 records; penalties: 32 records.
- Graph API: 13 nodes and 12 edges on the first bounded page.
- Browser: home, live database status, company overview, source counts, graph controls, and detail panels render.
- Judicial boundary returns a healthy source status and official search URL, but known local case `82876417` returned zero canonical WSGI records; see debt item A1.

## Phase 0 technical debt

### A1 — Canonical and legacy runtime divergence (high)

`app.py`, `api/index.py`, `src/server.py`, and `src/v2server.py` overlap in routing and response construction. The known judicial demo behavior exists outside the canonical WSGI path, so tests can pass against a non-production implementation while `app:app` behaves differently. Consolidate around `app.py` plus shared services before adding features.

### A2 — Preview isolation is not proven (critical)

The repository contains a fixed Supabase public project fallback. A Vercel Preview can therefore read the same Supabase project as Production unless Preview variables explicitly override it. Before data writes, provision or designate a Preview Supabase target and add an automated assertion that Preview never receives a Production service-role key.

### A3 — Main-branch workflows can mutate shared data (critical)

`seed-test-entities.yml` calls a deployed Supabase Edge Function on pushes to `main`; `sync-public-evidence.yml` writes generated status back to `main`. These are operational workflows, not isolated tests. Separate read-only verification from ingestion, require manual/approved write jobs, and target an explicit non-production environment first.

### A4 — Toolchain versions drift (high)

Workflows mix Python 3.11/3.12 and Node 20/22, while `pyproject.toml` requires Python 3.12+ and Vercel is configured for Node 24.x. Supabase client libraries dropped Node 20 support in 2026. Pin one supported matrix (Python 3.12 and Node 24, or documented Node 22) across local, CI, and Vercel.

### A5 — Frontend ownership is unclear (medium)

UI behavior is split across a large inline script in `web/index.html`, `web/app.js`, and `web/tei-enhancements.js`; root `app.js` is also checked. This increases drift and makes browser tests ambiguous. Inventory which files are served by `app:app`, remove dead duplicates after proof, and extract modules without changing behavior.

### A6 — Search safety depends on refresh correctness (high)

Public search projection tables are RLS-protected and refreshed by triggers, which is good. Their public policies check entity existence but not `publication_status`, and the final search RPC relies on projection freshness. Add publication predicates as defense in depth and test withdraw/republish races.

### A7 — Search performance is conditional (medium)

Contains search uses trigram indexing only when `gin_trgm_ops` exists. Without it, `%term%` degrades to scans. Verify `pg_trgm` and query plans on realistic data; keep exact/prefix lookup as the primary path.

### A8 — Data lifecycle is unspecified (medium)

Most core foreign keys do not define `ON DELETE` behavior. That protects evidence from accidental cascade but leaves withdrawal, correction, retention, and cleanup semantics implicit. Document lifecycle rules before any destructive maintenance.

### A9 — Test layers are fragmented (medium)

Unit, PGlite, local HTTP, live government-source, deployed Supabase, and Production-facing smoke checks live in separate workflows with inconsistent gates. Create one read-only acceptance matrix and make Preview the required integration target.

## Security and data observations

- Core public tables have RLS and explicit grants; this is compatible with Supabase's 2026 move away from automatic Data API exposure.
- Public read code does not select a service-role key for Entity API calls.
- Private `SECURITY DEFINER` refresh helpers set an empty search path and revoke public execution; public graph/search RPCs use `SECURITY INVOKER`.
- Relationship queries are batched and cursor-bounded, avoiding N+1 expansion and deep offset pagination.
- No database mutation was performed during this audit.

## Target architecture direction

Keep one canonical API and make the domain model the integration seam:

```text
Source adapters -> immutable Evidence -> resolved Entity -> evidence-backed Relationship
                                              -> bounded Graph/query projections
```

Source-specific payloads remain provenance; published Entity and Relationship records are curated projections, never unsupported inferences.
