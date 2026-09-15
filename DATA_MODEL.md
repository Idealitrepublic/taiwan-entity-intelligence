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

Publication requires `EXACT` or `HIGH` confidence. `relationship_evidence` adds supporting, contextual, or refuting evidence. `relationship_types` defines allowed endpoint types and directionality, though endpoint compatibility still needs application/ingestion enforcement.

### Resolution

`resolution_candidates` stores reviewable possible identity matches with evidence and decision state. It must never silently merge same-name people. `legacy_entity_map` provides deterministic migration continuity from old records.

## Read projections and APIs

- `search_entities`: bounded to 20 published results; exact identifier, exact name, prefix, then contains ranking.
- `graph_entity_neighbors`: one-hop, keyset-cursor expansion; maximum 25 records per RPC call.
- Public APIs expose only published entities, active/published evidence, and published relationships.
- Browser expansion is bounded to three hops and 60 nodes.

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

- Define deletion versus withdrawal/retention semantics for every core table.
- Enforce relationship endpoint compatibility declared in `relationship_types`.
- Define source correction and retraction propagation to dependent relationships.
- Define entity merge/split audit records and reversible resolution decisions.
- Decide whether penalties, contracts, and judgments remain entities, evidence, or both under explicit modeling rules.
