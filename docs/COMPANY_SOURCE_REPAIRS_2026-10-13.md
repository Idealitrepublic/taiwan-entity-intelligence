# Company source projection repairs

Scope: the three P0 findings from the read-only 中華電信 audit. No database write, ingestion, schema change, new source, identity merge or Production change.

## Changes

- Labor: include strictly bounded company-name/representative-parenthesis variants from existing source records. Reject a conflicting company identifier; retain original rows and provenance. Missing identifiers remain explicitly unverified candidates in the profile, evidence match rule and graph metadata. Do not publish canonical Relationships from name candidates. Each source query remains capped at 100 rows.
- Procurement: use the queried identifier's bidder field path and explicit award role, not position or presence in bidder names. Exclude nonwinners and unresolved roles, deduplicate agency/job notices, and apply the latest correction before role filtering. Same-day conflicting roles are unresolved. Display only the identifier-linked awardee names. Correct the mirror link parameter to `unit_id`. Lookup still covers only the first page and is labelled limited.
- Judicial: derive the read-projection date from a valid eight-digit official JID, preserve the original source publication date and mark conflicts. This is identifier-derived, not independently verified against every judgment body. Immutable index/snapshot/checkpoint files are unchanged. Show index coverage, loaded-page limit and date basis. Benchmark recall now searches the complete local index rather than the newest 50 UI rows.

## Verification

- 84 targeted Python tests passed, including five new repair tests.
- Five new shipped-function UI assertions and 21 existing browser-function regression cases passed. These are not a substitute for real-browser acceptance.
- 160 isolated PostgreSQL schema/migration/RLS integration checks passed; no live DB mutation.
- Full lint, inline JavaScript parse and bundle build (50 modules) passed.
- Read-only live procurement lookup for 96979933: 100 notices fetched, 95 award notices, 75 unique identifier-confirmed winning jobs, 14 nonwinning jobs, zero unresolved jobs; first-page-only result, not nationwide history.
- Local judicial projection: 85 matches, 50 loaded, 50 loaded rows with publication/date mismatch retained as metadata. No inferred historical coverage.

## Acceptance boundary

Preview browser verification is recorded separately after deployment. This patch does not repair missing canonical company materialization or expand full procurement/judiciary history. Private cross-account acceptance still requires actual independent login. Product Consolidation remains OPEN; no P1/P2 or new-source phase started.
