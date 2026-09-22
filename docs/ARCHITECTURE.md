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

## Phase 1 model hardening

Phase 1 keeps the deployed WSGI and browser boundaries unchanged. `src/entities/contracts.py` is now the single allowlist for public Entity, Relationship, and Evidence fields and the version-1 response envelope. The repository continues to use anonymous, RLS-aware reads; no public write route or service-role fallback was added.

Migration `20260915171831_phase_1_public_model_hardening.sql` repeats publication-state checks inside the public search, relationship, and evidence-link policies. This removes the search projection refresh process as a single safety boundary. The existing deferred relationship constraint remains authoritative for endpoint types, published endpoints, confidence, and active/published primary evidence; existing withdrawal triggers retract dependent published relationships.

There is no Phase 1 UI layout or interaction change. Existing search, company, procurement, penalty, judgment, and Graph flows retain their response shapes. The migration is intentionally not applied to Production by this branch; database acceptance requires a non-production Supabase target, while the Preview may perform only public read checks against the currently configured store.

Debt A6 is resolved in the migration and automated PGlite tests, but remains unapplied to the shared database until an accepted database deployment. A2, A3, A4, A5, A7, A8, and A9 remain open. The known judicial zero-record gap remains A1/Phase 4 work and is not part of this phase.

## Phase 2 global entity search

The existing read path remains `web/index.html -> /api/v1/search -> search_entities`. Phase 2 does not add another search service or alter the version-1 response. Input is normalized with Unicode NFKC in the browser, API validation, search projection refresh, and RPC query. This makes full-width company numbers and compatibility characters deterministic while retaining the eight-digit direct company-investigation path.

Migration `20260915173315_phase_2_global_entity_search.sql` keeps `search_entities(text,text,integer)` stable, explicitly filters published entities, and refreshes canonical names, display names, aliases, and the allowlisted company-number projection. Search remains bounded to 20 records and supports every declared Entity type; the UI now exposes every type as an optional filter. Multi-type PGlite fixtures cover Company, Person, Politician, GovernmentOfficial, and GovernmentAgency without seeding or modifying Production.

## Phase 3 Graph 2.0

Graph 2.0 keeps the existing `/api/v1/graph/{entity_id}` envelope and the one-hop `graph_entity_neighbors` RPC. The browser composes those bounded pages into an Entity→Relationship→Entity view: every edge retains its direction, relationship type, and active primary Evidence record. Expansion remains lazy and uses one RPC call per clicked node, with keyset cursors for additional pages rather than offsets or per-edge lookups.

The Entity graph now exposes a selectable one-, two-, or three-hop ceiling, relationship-type filtering, labeled nodes, evidence inspection, expansion animation, and direct node repositioning. It preserves the legacy eight-digit company graph and its pan/zoom/collapse behavior. Browser state is capped at 60 nodes; changing hop or relationship filters rebuilds the bounded view from the root so stale out-of-scope edges cannot remain visible.

No Phase 3 schema change is required: endpoint compatibility, publication state, active primary Evidence, RLS, grants, source/target indexes, and cursor ordering are already enforced by the Phase 1–2 migrations and the existing graph RPC. Phase 3 adds PGlite regression coverage for filter and cursor behavior. Production migrations and the known judicial zero-record issue remain outside this phase.

## Phase 4 Relationship Path Finder

The read path is `web/index.html -> /api/v1/paths -> find_entity_relationship_path`. The browser lets an investigator select two published Entity records from search results or graph nodes, then requests their shortest evidence-backed path. Every returned segment keeps the underlying relationship direction while also declaring whether the A-to-B traversal follows or reverses that direction.

The database performs one `SECURITY INVOKER`, RLS-aware recursive query. It rejects identical endpoints, enforces `max_depth` from one to three, prevents entity cycles with a visited UUID array, and examines at most 50 ordered relationships per expanded entity. Only published Entities and Relationships with active, published primary Evidence participate. The response reports these limits so a zero result is not presented as proof that no relationship exists outside the bounded search.

For backward compatibility while the additive migration awaits acceptance, the repository detects only the RPC-missing response and falls back to Graph 2.0 pages. That fallback uses breadth-first search, 12 relationships per entity, at most 30 expanded entities, cycle prevention, and an explicit `truncated` flag. Other database failures still surface as unavailable rather than silently falling back.

No public table or write path is added. The existing source/target relationship indexes remain the access paths; the API preserves the version-1 envelope and all Graph 2.0 endpoints. Each segment includes relationship type, available dates and amounts, primary Evidence, source record ID, and original source URL. The migration remains unapplied to Production until Preview acceptance.

## Phase 5 Politician Entity

The legislator profile path is `web/index.html -> /api/v1/politicians/{entity_id} -> politician_terms + bounded Relationships`. The canonical identity remains a `Politician` Entity. An additive, evidence-backed term table records term number, constituency, party Entity, and term dates; committee and bill activity reuse the existing Relationship and Evidence model.

The public repository performs bounded reads: at most 20 term rows and 25 first-page legislative relationships. It classifies `MEMBER_OF`, `LEGISLATOR_OF`, `COMMITTEE_MEMBER`, `PROPOSED_BILL`, and `CO_SPONSORED_BILL` in one embedded Relationship read without per-edge queries. If the new table is absent, the same endpoint returns existing evidence-backed Relationships with an explicit schema-availability flag, retaining Preview compatibility before database acceptance.

The browser adds a shareable `/politician/{uuid}` route and renders name, party, constituency, term, committee, proposal/co-sponsorship, Evidence, and original source links. Search, Graph 2.0, path finding, and the eight-digit company flow keep their existing contracts. The migration is not applied to Production in this phase.

## Phase 6 Political Contribution

The ingestion boundary is `src/political_contributions.py -> tei_ingest_bundle`. It accepts only already-resolved Company and Politician records, normalizes the donor identifier with Unicode NFKC, and requires exactly eight digits. Missing identifiers, name-only donors, unmatched companies/politicians, invalid amounts, and invalid dates are reported as skipped; no fuzzy identity merge is attempted and output remains draft.

Each accepted row becomes one directed `Company -> POLITICAL_CONTRIBUTION_TO -> Politician` Relationship. Amount/currency, contribution date/day precision, and contribution type use core Relationship fields. Immutable Evidence stores the official source record ID, an allowlisted locator containing `match_method=exact_uniform_number`, and the original Control Yuan URL. The migration adds a deferred publication constraint that verifies the Evidence locator against the Company's private exact uniform-number identifier.

The read path is `web/index.html -> /api/v1/entities/{uuid}/political-contributions -> political_contributions_for_entity`. One bounded, keyset-cursor RPC projects both endpoints, the Relationship, and primary Evidence for either the Company or Politician page. It is `SECURITY INVOKER`, explicitly filters publication state, exposes no private identifier table, and grants only execution to read roles. When the additive RPC is absent, the repository uses a bounded existing-schema projection and still rejects non-exact Evidence locators.

The indexed Entity company page and Politician page render the same bidirectional card contract. The legacy eight-digit company investigation first requires an `identifier_exact` global-search result before requesting contributions; contribution lookup failure does not break existing company results. Production schema and data remain unchanged until explicit acceptance.

## DATA Phase 6 — Cross-source health

The read-only `scripts/data_health.py` benchmark and `src/data_health.py` metric
definitions sample public MOEA, PCC mirror, Supabase and the judicial index.
They add no database migration. Private resolution quality is unobservable to
public RLS; failed or empty judicial syncs cannot replace the last usable index.

## Phase 7 Asset Declaration

The ingestion boundary is `src/asset_declarations.py -> tei_ingest_asset_declaration_bundle`. Source rows become immutable Evidence plus a typed `asset_declarations` projection. All thirteen required categories share the same contract while retaining nullable amount/currency, quantity/unit, source company name, and original source location.

Company resolution is intentionally narrower than display: only an exact, normalized eight-digit source company number can resolve a published Company identifier. Name-only records remain useful declarations but keep `company_entity_id` and `relationship_id` null. Eligible securities create `ASSET_OWNERSHIP`; business investments create `BUSINESS_INVESTMENT`; other categories do not imply a company relationship.

The read path is `web/index.html -> /api/v1/politicians/{uuid}/asset-declarations -> asset_declarations`. It is limited to 25 keyset-cursor rows and supports declaration-year and asset-type filters. One embedded read returns the linked Company, Relationship, and primary Evidence without N+1 queries. Missing additive schema yields an explicit empty compatibility response so existing politician, Graph, search, and legacy company views continue to work.

The migration adds RLS, explicit read grants, service-role-only ingestion, indexed politician/year/type and company access paths, and a deferred publication validator. The validator repeats exact-company-number resolution and requires every derived Relationship to match endpoints, type, Evidence, values, and source role. Evidence or Entity withdrawal retracts affected published declarations. Production remains unchanged until acceptance.

## Phase 8 Asset Timeline

The read path is `web/index.html -> /api/v1/politicians/{uuid}/asset-timeline -> asset_declarations`. It reuses the Phase 7 RLS policy and `(politician_id, declaration_year, id)` index; no new table, migration, write path, or Production change is required. The repository performs one embedded read capped at 501 probe rows, returns at most 500, and limits output to the latest 2–20 requested declaration years.

`src/asset_timeline.py` is the deterministic comparison boundary. It groups amounts by currency and quantities by unit, so unlike measures are never combined. Adjacent years match only exact NFKC-normalized asset identity and exact resolved Company IDs. Missing dimensions, mixed movement, or differing units are reported as `CHANGED`, not coerced into an increase or decrease. A line absent in the next declaration is labeled `NO_LONGER_DECLARED`, never sold or disposed.

The politician page renders per-year type summaries, amount/quantity changes, and both current and prior Evidence/source links. Its disclaimer explicitly limits the display to objective declaration differences and rejects inferences about illegality, conflicts of interest, acquisition, or disposal. Missing Phase 7 schema remains an explicit empty compatibility response.

## Phase 9 Investigation Workspace

The private write path is `web/index.html -> /api/v1/workspaces -> Supabase Data API`. The browser signs in directly through Supabase Auth with the public publishable key and keeps the short-lived session in `sessionStorage`. The WSGI API forwards the user's bearer token with the publishable key; it never reads or falls back to a service-role secret. Existing public Entity APIs remain read-only and reject non-GET methods.

`investigation_workspaces` and `workspace_items` are additive owner-scoped tables. Anonymous access is revoked. Authenticated CRUD is constrained by separate RLS policies using `(select auth.uid())`, indexed owner columns, a composite workspace/owner foreign key, and immutable single-user attribution. Entity, Relationship, Evidence, and Graph references use typed foreign keys; Source and Note values have protocol and size constraints. Workspace deletion cascades only within private workspace data.

The UI supports create, rename/edit, delete, and selection of workspaces; saving the current canonical Entity, selected Graph edge and Evidence, bounded Graph state, an HTTP(S) source, or a Note; Note editing; and item deletion. It deliberately adds no member sharing, Watchlist, Alert, or Report Export behavior. If the additive schema is absent, the workspace returns an explicit unavailable state without affecting search, company, politician, Graph, or evidence features. The migration remains unapplied to Production until acceptance.

## DATA Phase 2 political-contribution ingestion

The official Control Yuan file is normalized before graph projection. Unicode,
ROC/Gregorian dates, currency formatting, field aliases, and source identity are
handled deterministically. Company resolution uses only exact uniform numbers;
Politician resolution uses only an explicit official identifier crosswalk. Names
are retained for audit display and are never used to merge an Entity.

The adapter emits draft `Company -> POLITICAL_CONTRIBUTION_TO -> Politician`
Relationships and immutable Evidence, plus acceptance, coverage, skip, duplicate,
and conflict metrics. Dependency-complete batches stay below the core ingestion
limits. `tei_ingest_political_contribution_bundle` is service-role-only,
`SECURITY INVOKER`, cannot create Entities, and validates exact identifiers and
provenance before calling the canonical ingestion function. Publication repeats
both identifier checks in a deferred database constraint. The existing public
read API and UI are unchanged. Rollback removes the additive RPC/validator and
draft batch; published facts require a reviewed superseding record.

## DATA Phase 3 asset-declaration ingestion

`src/asset_declarations.py` normalizes Control Yuan gazette/document rows into
draft `asset_declarations`, immutable Evidence, and optional ownership/investment
Relationships. Official Politician identifiers and Company uniform numbers are
the only Entity-resolution keys. Names remain provenance text. Unicode, ROC year,
numeric units, thirteen categories, duplicate records, and correction versions
are handled deterministically.

The additive schema uses a stable line key, ordered version, optional supersedes
link, and one-published-version partial unique index. The service-role-only,
`SECURITY INVOKER` ingestion RPC rejects Entity creation, non-draft data,
unbounded batches, and missing Evidence identity/provenance. Publication repeats
the exact Politician/Company identifier checks and requires an older superseded
version to be withdrawn. Existing APIs remain backward compatible because the
new columns are nullable for pre-Phase-3 rows.

Rollback reverts the additive migration and removes only unaccepted draft data.
After publication, corrections withdraw the old version and insert a new Evidence
version; they never rewrite source history. No Production migration is run here.

## Phase 10 Watchlist and Alert

The private path remains browser session JWT → WSGI API → Supabase Data API/RPC. `src/watchlists.py` forwards the user's bearer token with the public key and never uses a service-role credential. Watchlist and alert routes are independent of every public Entity read endpoint, so missing additive schema returns an explicit unavailable state without changing search, company, politician, Graph, asset, or Workspace contracts.

`watchlist_entries` supports published Company, Person, and Politician Entities only. The browser triggers a bounded `SECURITY INVOKER` sync; it scans at most 25 subscriptions and considers at most 500 new event candidates. Evidence retrieval time must be on or after the watch start, which establishes an objective baseline instead of labeling all historical records as new. Unique source keys make repeated syncs idempotent.

Procurement, judgment, penalty, officer/director, and political-contribution alerts are projected from published Relationships with their active published primary Evidence. Asset alerts are projected from published asset declarations with the same Evidence requirement. The Dashboard provides all/read/unread filtering, individual read toggles, and mark-all-read. It deliberately adds no scheduler, Email, webhook, external push, or Production database mutation; the checked-in migration remains gated for acceptance.

## Phase 11 Report Export

The read path is `web/index.html -> /api/v1/reports/{scope}/{id} -> src/reports.py -> existing repositories`. Entity and Politician scopes reuse public, published projections. Workspace scope requires the browser's bearer token; the report service passes it to `WorkspaceRepository`, so the existing owner-only RLS boundary remains authoritative and no service-role credential is used.

Reports are generated on demand and are not stored. The shared contract includes Entity Profile, Key Relationships, Political Relationships, Government Contracts, Judgments, Penalties, Asset Records, Relationship Graph, and Sources. Evidence is normalized without losing its canonical fields and explicitly carries `source`, `source_url`, and `retrieved_at`. HTML is escaped, printable, and downloaded client-side as a Blob so private Workspace credentials never enter URLs.

Reads remain bounded to 25 graph relationships/assets per Entity and five distinct Workspace roots; truncation flags are part of the report. This phase adds no schema, migration, write path, AI inference, legal conclusion, or Production change. Existing search, company, politician, graph, asset, Workspace, and Watchlist routes retain their contracts.

## v2 DATA Phase 1 — Political Master Data

The ingestion boundary is `src/political_master.py ->
tei_ingest_political_master_bundle`. It consumes official Legislative Yuan
datasets 16 and 14, emits draft Entity/Relationship/Evidence records, and adds
draft `politician_terms` in the same transaction. Existing politician reads and
the version-1 API remain unchanged; `legislator_number` is an additive term field.

Politicians are consolidated only by official `lgno`. A dataset-internal exact
term/name join may discover one unique `lgno`, but a name never merges people
across terms or sources. Missing/ambiguous identifiers create source-scoped rows;
identifier/name conflicts and unmatched committee rows are reported and skipped.
Party and committee labels remain source-scoped Entities. Committee membership
keeps term/session/co-chair context in an evidence-backed Relationship.

`build_political_master_batches` partitions a refresh into dependency-complete
batches below the core limits of 200 Entities/Relationships/terms, 400 Evidence
records, and 1 MB. A committee batch repeats only the referenced Entity rows;
idempotent source IDs make retries safe.

The migration adds source identity and `lgno` indexes plus a service-role-only,
`SECURITY INVOKER` ingestion RPC. It accepts at most 200 term rows, rejects
non-draft input, and refuses to overwrite a published term without review. RLS
and existing grants remain authoritative; no browser or anonymous write path is
added. Preview validation uses PGlite and read-only deployment because the shared
Supabase project must not be mutated.

Rollback before acceptance is `git revert` of the additive migration and adapter.
If applied to a non-production database, drop the ingestion RPC, the two new
indexes, and the three additive term columns after exporting any draft rows.
Source-data rollback retracts the affected Evidence/Relationships by source batch;
it never deletes or rewrites unrelated Entity history.

## v2 DATA Phase 4 — Entity Resolution / Confidence Engine

`src/entities/resolution.py` is a deterministic candidate generator between
source observations and canonical Entities. It preserves the legacy exact-ID
helpers while adding normalized, explainable signals. Shared, unique official
identifiers yield `EXACT`; Company, role, overlapping dates, and independent
source corroboration may yield `HIGH` or `MEDIUM`. A same-name pair alone remains
`LOW`, and type/identifier conflicts remain `UNRESOLVED`.

The engine only emits pending candidates. It never updates an Entity or creates a
Relationship. The private `resolution_candidates` table stores score, signals,
matching Evidence IDs, engine version, and reviewed decision metadata. Database
validation restricts acceptance to `EXACT`/`HIGH`, repeats the no-name-only rule,
and makes matching inputs immutable after insertion. The bounded ingestion RPC is
service-role-only; public and authenticated clients receive no new write access.

Quality is measured from labeled pairs at the Relationship-eligible threshold.
Rollback removes the additive RPC, trigger, constraints, indexes, and candidate
metadata columns. Canonical Entities, Evidence, and Relationships are untouched;
accepted production decisions would require a separate audited reversal before
schema rollback. Production remains unchanged during this phase.

## v2 DATA Phase 5 — Judiciary coverage repair

The manual sync path is official JList (seven-day changes) → JDoc per JID →
versioned Evidence JSONL → deduplicated company-name index. The canonical
company route reads that index plus a small, official-document-verified
historical case set. It exposes source URL, JID, date, retrieval time, and
provenance while marking unmatched results as partial coverage.

JList schema errors and JDoc authentication failures stop the sync. Official
removal messages create a new Evidence version and suppress the last active
index entry. A file-only document without text remains Evidence but cannot
enter the company-name index until text extraction is available. Person mentions
remain unlinked. The older `src/server.py` demo still is not the canonical path.

No database migration, RLS change, or Production data write occurs here.
Rollback removes the verified-case projection and reverts the connector/index
changes; immutable source Evidence in an accepted ingestion is retained for
audit rather than overwritten.
