# T.E.I. data model

## Core invariant

Every published relationship must point to active primary evidence. Entity identity, relationship meaning, and source provenance remain separate concerns:

```text
Entity <- EntityEvidence -> Evidence
  |                           ^
  +-- Relationship ----------+
          |
          +-- RelationshipEvidence -> Evidence
```

## Core records

### Entity

`entities` is the stable internal identity. It stores type, canonical/display names, source-scoped identity, publication state, and timestamps. `entity_types` constrains the allowed taxonomy.

- `EXACT`: confirmed deterministic identity.
- `SOURCE_SCOPED`: identity is valid only within its source context.
- `UNRESOLVED`: evidence exists but consolidation is not approved.
- `draft`, `published`, `withdrawn`: publication lifecycle.

`entity_identifiers` contains exact identifiers and is deliberately not exposed to public clients. `entity_public_identifiers` is the safe projection currently limited to Taiwanese company numbers. `entity_aliases` and `entity_search_terms` support name lookup.

### Evidence

`evidence_records` is immutable source provenance identified by source name, source record ID, and SHA-256 content hash. It records:

- source class, URL/locator, title and summary;
- observed and retrieved timestamps;
- active/superseded/retracted source state;
- draft/published/withdrawn publication state.

`entity_sources` maps an entity to its source record. `entity_evidence` attaches evidence to a typed fact. Raw or sensitive identifiers must not be copied into public projections.

### Relationship

`relationships` connects two different entities using a constrained `relationship_type`. It carries time precision, quantities/amounts, source role, confidence, publication status, and a mandatory `primary_evidence_id`.

Publication requires `EXACT` or `HIGH` confidence. `relationship_evidence` adds supporting, contextual, or refuting evidence. `relationship_types` defines allowed endpoint types and directionality. A deferred database constraint enforces compatible endpoint types, published endpoints, and active/published primary evidence in the same transaction.

### Resolution

`resolution_candidates` stores reviewable possible identity matches with evidence and decision state. It must never silently merge same-name people. `legacy_entity_map` provides deterministic migration continuity from old records.

### Politician and legislative terms

A legislator is a canonical `Politician` Entity; the name is not a unique identity key. `politician_terms` stores one evidence-backed term observation with term number, constituency/type, dates, optional `PoliticalParty` Entity, and mandatory primary Evidence. Only published politicians, parties, and active published Evidence may appear in a published term.

Party membership, legislature, committee service, proposal, and co-sponsorship remain directed Relationships (`MEMBER_OF`, `LEGISLATOR_OF`, `COMMITTEE_MEMBER`, `PROPOSED_BILL`, `CO_SPONSORED_BILL`). Committees are `GovernmentAgency` Entities and bills are `LegislativeBill` Entities, so Graph and path queries remain reusable.

### Political contributions

A contribution is not a duplicate Entity. It is a directed `Company -> POLITICAL_CONTRIBUTION_TO -> Politician` Relationship with `amount`, `currency=TWD`, `start_date`, day precision, and `source_role` as the source contribution type. The primary Evidence preserves the source record ID, reproducible locator, immutable projection, and original source URL.

Company resolution is publishable only when the donor's normalized eight-digit uniform number exactly matches an `EXACT` `tw:uniform_number` identifier. Name-only, fuzzy, malformed, and unmatched records stay skipped/unresolved; adapters always emit draft rows for review. A deferred database constraint repeats this rule at publication time.

## Read projections and APIs

- `src/entities/contracts.py` is the canonical public field allowlist for Entity, Relationship, and Evidence. The API envelope remains `{"api_version":"1","data":...}` for backward compatibility.
- `search_entities`: NFKC-normalized and bounded to 20 published results across all Entity types; exact public company identifier, exact name/alias, prefix, then contains ranking.
- `graph_entity_neighbors`: one-hop, keyset-cursor expansion; maximum 25 records per RPC call.
- `find_entity_relationship_path`: bidirectional traversal over published relationships; shortest path within a caller-selected one-to-three-hop depth and a fixed 50-relationship expansion cap per entity.
- `/api/v1/politicians/{entity_id}`: bounded profile projection with at most 20 terms and 25 evidence-backed legislative relationships; it falls back to the existing Graph projection while the additive term table awaits deployment.
- `political_contributions_for_entity` and `/api/v1/entities/{entity_id}/political-contributions`: bidirectional Company/Politician projection, bounded to 25, cursor ordered, and restricted to published exact-uniform-number matches.
- Until that additive RPC is accepted, the read repository can use a 12-edge/30-entity Graph 2.0 breadth-first fallback and reports `truncated` when a high-degree page is incomplete.
- Public APIs expose only published entities, active/published evidence, and published relationships.
- Browser expansion is user-selectable from one to three hops and bounded to 60 nodes. Each click lazily requests one bounded neighbor page; relationship filters are sent to the RPC and filter changes rebuild from the root.
- Graph edges preserve `source_entity_id -> relationship_type -> target_entity_id` direction and expose the edge's active primary Evidence without duplicating it into Entity state.
- Path segments preserve the stored edge direction, identify forward/reverse traversal, and carry dates, amounts, primary Evidence, source record IDs, and source URLs in one bounded RPC response.

## Constraints and indexes

The migrations include primary keys, uniqueness, status checks, timestamp fields, relationship endpoint/evidence indexes, search prefix/trigram indexes, and relationship-type indexing. Foreign-key access paths are generally covered by explicit indexes, primary keys, or leftmost unique indexes.

Before scaling, verify with real query plans:

1. `pg_trgm` exists and contains-search uses the GIN index.
2. RLS policy predicates and publication filters use indexed columns.
3. Graph source/target queries continue to use composite indexes.
4. JSONB `source_locator` is indexed only when concrete containment queries justify it.

## RLS and privileges

- Enable RLS on every Data API-exposed table.
- Grant `anon`/`authenticated` only the exact read tables and RPCs required.
- Require explicit publication predicates in policies, not only in application code or refresh triggers.
- Keep ingestion/backfill on server-only service-role paths.
- Keep `SECURITY DEFINER` functions in the private schema, set `search_path = ''`, validate the caller where applicable, and revoke public execution.
- New migrations must include explicit `GRANT` statements because Supabase will enforce non-automatic Data API exposure for existing projects on 2026-10-30.

## Open model decisions

- Routine correction inserts a new immutable Evidence version; existing Evidence is marked superseded or retracted rather than edited.
- Entity withdrawal and primary-Evidence withdrawal/retraction automatically retract dependent published relationships. Republish requires an explicit relationship review; it is never automatic.
- Core foreign keys use restrictive deletion semantics. Routine hard deletion is unsupported; retention and exceptional cleanup policy still require an operations decision.
- Define entity merge/split audit records and reversible resolution decisions.
- Decide whether penalties, contracts, and judgments remain entities, evidence, or both under explicit modeling rules.
