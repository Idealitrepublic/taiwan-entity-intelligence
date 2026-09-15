# T.E.I. roadmap

All phases use: **Local -> Test -> Git -> Vercel Preview -> Acceptance -> Production**.

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

- Enforce relationship endpoint type compatibility.
- Preserve mandatory active primary evidence for every published edge.
- Validate keyset pagination, filters, three-hop/60-node browser limits, and retraction behavior at scale.
- Add query-plan checks for source/target composite indexes and eliminate any remaining N+1 paths.

Exit gate: bounded graph expansion remains correct and performant on representative data.

## Phase 4 — Source adapter reliability

- Unify procurement, penalty, judicial, fraud/domain, and registry adapters behind consistent source-result contracts.
- Repair the canonical judicial known-case path and add deterministic fixtures.
- Separate source availability, zero matches, partial data, and hard failure in API/UI states.
- Record source licensing, refresh cadence, retrieval state, and replacement/removal behavior.

Exit gate: each source has read-only Preview acceptance tests and observable failure states.

## Phase 5 — Delivery and operations

- Standardize Python/Node versions across local, CI, and Vercel.
- Replace Production-facing CI smoke tests with Preview gates; make ingestion jobs explicit and approved.
- Add structured runtime logs, source freshness alerts, and rollback runbooks.
- Remove proven-dead duplicate runtime/UI files after behavior-parity tests.

Exit gate: an accepted Preview artifact is the only path to Production.

## Deferred product work

No unrelated UI/product features begin until Phases 1–3 establish trustworthy Entity, Relationship, Evidence, search, and Graph behavior. Saved investigations, reports, and AI assistance remain deferred.
