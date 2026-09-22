# T.E.I. roadmap

All phases use: **Local -> Test -> Git -> Vercel Preview -> Acceptance -> Production**.

## v2 DATA Phase 1 — Political Master Data

Status: implemented on `data-phase-1/political-master-data`; Preview acceptance
required. Production schema and data remain unchanged.

- Ingest official Legislative Yuan member and committee observations as draft,
  evidence-backed Entity/Relationship/term records.
- Resolve a politician across records only by exact official `lgno`; keep missing
  or ambiguous rows source-scoped and never merge people by name alone.
- Preserve term, party, constituency, onboard/leave dates, committee session,
  source record, source URL, retrieval time, and quality metrics.
- Exclude private contact fields and require separate review before publication.

Exit gate: adapter tests, PostgreSQL/RLS checks, build, and read-only Preview pass.
## DATA Phase 2 — Political Contributions Ingestion

- Normalize official Control Yuan contribution rows and preserve immutable source provenance.
- Resolve donor companies only by exact uniform number and politicians only by official ID.
- Report exact-match coverage, rejected rows, duplicates, and conflicts per run.
- Keep ingestion bounded, draft-only, and backward compatible with Phase 6 reads.

## DATA Phase 3 — Asset Declaration Ingestion

- Normalize official Integrity Gazette lines across all thirteen asset categories.
- Preserve annual append-only versions, immutable Evidence, source URL and retrieval time.
- Resolve Politicians and Companies only by exact verifiable identifiers.
- Report category coverage, acceptance, unresolved Companies, duplicates and conflicts.

Do not begin DATA Phase 4 until explicit approval.

## Phase 0 — Baseline and repository audit

Status: complete on local branch; not deployed.

- Reconstructed the Mac development environment and linked the local checkout metadata to the existing Vercel project.
- Verified npm dev/build, Python tests, PGlite schema checks, Supabase connectivity, published entity search, procurement, penalties, Graph API, and browser rendering.
- Documented the judicial canonical-path gap and repository technical debt in `docs/ARCHITECTURE.md`.
- Added repository operating rules and the canonical data model.

Exit gate: documentation reviewed; no Production mutation; branch diff is bounded and tests pass.

## Phase 1 — Entity and Evidence foundation

Status: model hardening implemented on `phase-1/entity-relationship-evidence`; Preview acceptance and Production migration remain gated.

Goal: make identity and provenance the stable base before expanding features.

- Consolidate canonical routing/service boundaries without response changes.
- Harden search projection RLS with publication predicates.
- Define entity merge/split, correction, withdrawal, and evidence retraction semantics.
- Verify explicit Data API grants before Supabase's 2026-10-30 enforcement date.
- Add Preview-isolation assertions and a non-production dataset fixture.
- Add contract tests proving public clients cannot read private identifiers or use service-role access.

This branch centralizes the version-1 public Entity/Relationship/Evidence contract, adds explicit publication predicates to public model policies, and covers withdraw/republish projection races. It does not change the UI or legacy company responses. Preview isolation is limited to read-only public access until a dedicated non-production Supabase target is provisioned; no Production migration is authorized.

Exit gate: Entity/Evidence invariants, RLS, retraction, and Preview isolation pass automated tests.

## Phase 2 — Global Entity Search

Status: implemented on `phase-2/global-entity-search`; Preview acceptance and Production migration remain gated.

- Search published companies, public company numbers, people, politicians/legislators, officials, agencies, and every declared Entity type through one bounded RPC.
- Normalize browser, API, projection, and RPC input with Unicode NFKC.
- Preserve the version-1 API response and the existing eight-digit company investigation flow.
- Verify type filters, aliases, same-name separation, publication RLS, and multi-type ranking with PGlite fixtures.

Exit gate: targeted tests, DB checks, full build, and read-only Preview verification pass without a Production mutation.

## Phase 3 — Relationship and Graph hardening

Status: implemented on `phase-3/graph-2`; Preview acceptance remains gated.

- Enforce relationship endpoint type compatibility.
- Preserve mandatory active primary evidence for every published edge.
- Validate keyset pagination, filters, three-hop/60-node browser limits, and retraction behavior at scale.
- Add query-plan checks for source/target composite indexes and eliminate any remaining N+1 paths.
- Render the canonical directed Entity→Relationship→Entity graph with node labels, lazy animated expansion, node dragging, selectable one-to-three-hop depth, relationship filtering, and edge-level Evidence inspection while retaining the legacy company graph.

Exit gate: bounded graph expansion remains correct and performant on representative data.

## Phase 4 — Relationship Path Finder

Status: implemented on `phase-4/relationship-path-finder`; Preview acceptance and Production migration remain gated.

- Find the shortest published Entity A → Entity B path within one to three hops.
- Keep traversal cycle-free and cap expansion at 50 relationships per entity.
- Return relationship direction/type, dates, amounts, primary Evidence, and original source details for every segment.
- Preserve the version-1 API envelope, Global Entity Search, Graph 2.0, and legacy company investigation behavior.
- Verify the RPC under anonymous RLS with deterministic PostgreSQL fixtures and deploy only to Vercel Preview.

Exit gate: targeted tests, bounded traversal DB checks, full build, and protected Preview runtime checks pass without a Production mutation.

## Phase 5 — Politician Entity

Status: implemented on `phase-5/politician-entity`; Preview acceptance and Production migration remain gated.

- Model legislators as canonical Politician Entities with evidence-backed terms, party, constituency, and dates.
- Represent legislature, committee, proposal, and co-sponsorship through existing Relationship/Evidence edges.
- Add a bounded read API and shareable legislator page while preserving company, search, Graph, and path contracts.
- Verify RLS, grants, endpoint types, term constraints, backward-compatible fallback, and source links.

Exit gate: targeted tests, PostgreSQL checks, full build, and protected Preview runtime checks pass without a Production mutation.

## Phase 6 — Political Contribution

Status: implemented on `phase-6/political-contribution`; Preview acceptance and Production migration remain gated.

- Project official contribution rows into Company-to-Politician Relationships with immutable Evidence.
- Resolve companies only by normalized exact eight-digit uniform number; never infer a company from its name.
- Preserve amount, date, contribution type, source record, Evidence, and original source URL.
- Add bounded bidirectional reads to company and politician pages while preserving legacy company behavior.
- Enforce publication invariants, RLS-aware reads, cursor limits, and draft-only adapter output.

Exit gate: targeted tests, PostgreSQL checks, full build, GitHub push, and protected Preview runtime checks pass without a Production mutation.

## Phase 7 — Asset Declaration

Status: implemented on `phase-7/asset-declaration`; Preview acceptance and Production migration remain gated.

- Store evidence-backed legislator declarations across all thirteen required asset categories.
- Preserve year, type, name, amount, quantity, source company text, Evidence, and original source.
- Resolve a Company only by an exact normalized eight-digit identifier; never by fuzzy company or person name.
- Create `ASSET_OWNERSHIP` or `BUSINESS_INVESTMENT` only for eligible, exactly resolved declarations.
- Add bounded politician-page reads with year/type filters and backward-compatible old-schema behavior.

Exit gate: targeted tests, PostgreSQL checks, full build, GitHub push, and protected Preview runtime checks pass without a Production mutation.

## Phase 8 — Asset Timeline

Status: implemented on `phase-8/asset-timeline`; Preview acceptance remains gated.

- Build a bounded annual sequence from published legislator asset declarations.
- Summarize every year by asset type, currency, and quantity unit without mixing unlike measures.
- Compare adjacent years as baseline, new, increased, decreased, continued, changed, or no longer declared.
- Preserve current/prior Evidence and source URLs, and make no illegality or conflict-of-interest inference.
- Keep the Phase 7 schema and APIs backward compatible; add no write path or Production migration.

Exit gate: targeted tests, PostgreSQL checks, full build, GitHub push, and protected Preview runtime checks pass without a Production mutation.

## Phase 9 — Investigation Workspace

Status: implemented on `phase-9/investigation-workspace`; Preview acceptance and Production migration remain gated.

- Add authenticated, owner-only Workspace create/read/update/delete.
- Save Entity, Relationship, Evidence, bounded Graph state, original Source, and Note items.
- Preserve explicit owner/creator attribution and enforce the boundary with grants, constraints, and RLS.
- Keep the first version single-user; do not add Watchlist, Alert, sharing, or Report Export.
- Preserve every existing public Entity, search, Graph, politician, contribution, and asset contract.

Exit gate: targeted tests, PostgreSQL owner-isolation checks, full build, GitHub push, and protected Preview runtime checks pass without a Production mutation.

## Phase 10 — Watchlist / Alert

Status: implemented on `phase-10/watchlist-alert`; Preview acceptance and Production migration remain gated.

- Track published Company, Person, and Politician Entities with owner-only RLS.
- Detect new procurement, judgment, penalty, officer/director, political-contribution, and asset-declaration records after the watch baseline.
- Require active published Evidence, preserve canonical source IDs, and deduplicate repeated scans.
- Provide bounded Dashboard notifications with all/read/unread filters and single/all read controls.
- Keep delivery in-app only; do not add Email, webhook, external push, Watchlist sharing, or report export.

Exit gate: targeted tests, PostgreSQL owner-isolation/detection checks, full build, GitHub push, and protected Preview runtime checks pass without a Production mutation.

## Phase 11 — Report Export

Status: implemented on `phase-11/report-export`; Preview acceptance remains gated.

- Export deterministic Entity, Politician, and owner-scoped Workspace investigation reports.
- Include profiles, key/political relationships, contracts, judgments, penalties, assets, graph, and sources.
- Preserve Evidence plus source, source URL, and retrieval time without automated findings or conclusions.
- Provide readable and downloadable HTML while retaining bounded reads, RLS, and existing API compatibility.
- Add no table, migration, AI analysis, or Production mutation.

Exit gate: targeted tests, existing PostgreSQL checks, full build, GitHub push, and protected Preview runtime checks pass.

## Phase 12 — Source adapter reliability

- Unify procurement, penalty, judicial, fraud/domain, and registry adapters behind consistent source-result contracts.
- Repair the canonical judicial known-case path and add deterministic fixtures.
- Separate source availability, zero matches, partial data, and hard failure in API/UI states.
- Record source licensing, refresh cadence, retrieval state, and replacement/removal behavior.

Exit gate: each source has read-only Preview acceptance tests and observable failure states.

## Phase 13 — Delivery and operations

- Standardize Python/Node versions across local, CI, and Vercel.
- Replace Production-facing CI smoke tests with Preview gates; make ingestion jobs explicit and approved.
- Add structured runtime logs, source freshness alerts, and rollback runbooks.
- Remove proven-dead duplicate runtime/UI files after behavior-parity tests.

Exit gate: an accepted Preview artifact is the only path to Production.

## Deferred product work

No unrelated UI/product features begin without an explicit phase. AI assistance remains deferred.
