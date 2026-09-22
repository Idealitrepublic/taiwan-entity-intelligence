# Data Health — DATA Phase 6

Generated: 2026-09-22T19:38:20.024357+00:00

This is a read-only, fixed-sample benchmark, **not national coverage**.
Unknown values are not zero. Politician coverage uses official `lgno` overlap; contribution and asset denominators remain unknown. Adapter fixtures are excluded.

| Source | Scope | Observed | Expected | Coverage | Freshness h | Errors | Duplicate | Provenance | Severity |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| company_registration | 3 fixed valid-company identifiers; live MOEA | 3 | 3 | 1.0 | 0.0 | 0 | 0.0 | 1.0 | OK |
| directors | same 3 identifiers; presence only | 3 | 3 | 1.0 | 0.0 | 0 | 0.0 | 1.0 | OK |
| procurement | same 3 identifiers; mirror response, not award recall | 3 | 3 | 1.0 | unknown | 0 | 0.0 | 0.0 | Medium |
| labor_penalties | indexed company-name reads; national recall unknown | 211 | unknown | unknown | 349.6 | 0 | 0.0 | 0.0 | Medium |
| judiciary | 3 official known-case JIDs; not historical recall | 3 | 3 | 1.0 | 166.8 | 1 | 0.0 | 0.0043 | High |
| politicians | official term-11 committee lgno matched to published politician_terms; not all legislators | 0 | 121 | 0.0 | unknown | 0 | unknown | unknown | High |
| political_contributions | public published-data sample; source denominator not yet established | 0 | unknown | unknown | unknown | 0 | unknown | unknown | High |
| asset_declarations | public published-data sample; source denominator not yet established | 0 | unknown | unknown | unknown | 0 | unknown | unknown | High |
| entity_resolution | private resolution_candidates excluded by RLS | unknown | unknown | unknown | unknown | 0 | unknown | unknown | Unknown |

## Findings and disposition

- **High — publicly visible political data absent:** public presence probes returned zero, so draft ingestion has not yet become verified public coverage. Do not publish or mutate the shared Production database from this audit; review official source batches, RLS and publication separately. This release gate remains open.
- **High — judicial sync failure:** the checked-in status has an HTTP error although older `last_sync` exists. This report counts the error and never treats the timestamp as proof of a clean latest attempt. The sync now preserves the last usable index on failure; historical judiciary coverage remains a documented gap.
- **Medium — procurement/penalty provenance:** live mirror and legacy source records may lack per-row retrieval time, original record URL or provenance. Missing fields remain visible as unknown/partial; they are not fabricated.
- **Unknown — private resolution candidates:** anonymous read access is intentionally denied. Precision/recall from labeled tests does not establish live population quality.
- **Source-to-ingestion gap:** official [Legislative Yuan member data](https://data.ly.gov.tw/getds.action?id=16), [Control Yuan contribution ZIP files](https://data.gov.tw/dataset/168061), and [Integrity Gazette](https://sunshine.cy.gov.tw/News.aspx?PageSize=200&n=17&page=1&sms=8861) exist, but no scheduled political ingestion or reviewed publication job is configured. Contribution files do not directly supply the Legislative Yuan `lgno`; name-only matching remains prohibited. Gazette documents require evidence-preserving extraction and historical full-text availability is limited.

## Privileged, read-only database cross-check

Audited: 2026-09-22T19:20:00Z against rztdbdurkjfrirsrrhtu; this is a separate snapshot, not refreshed by the public benchmark.
All publication states were counted using `scripts/data_health_remote.sql`:

- `politician_entities`: 0 rows across all states.
- `politician_terms`: 0 rows across all states.
- `political_contributions`: 0 rows across all states.
- `asset_declarations`: 0 rows across all states.

DATA Phase 1–4 migrations absent from that database: 20260922170414, 20260922173008, 20260922174447, 20260922182447.
The master/contribution ingestion entrypoints are absent; the older asset entrypoint exists. Anon RLS is publication-filtered but cannot explain zero rows across all states.
Preview has no Supabase override in Vercel environment variables and falls back to this same public project. Therefore Preview cannot gain independent data without an isolated database.

## Latest official judiciary sync

[GitHub Actions run](https://github.com/Idealitrepublic/taiwan-entity-intelligence/actions/runs/35774296486): failed; 15 documents read before failure. Cause: official JDoc returned a server-side null-object error for one listed JID. No Production data was written.
The connector now accepts both five- and six-part official JIDs and retains successful documents while recording individual JDoc failures. A failed window cannot replace the last usable index; source-side gaps remain High until a clean verified run.

## Reproduce and rollback

Run `python scripts/data_health.py --json reports/data_health.json --markdown docs/DATA_HEALTH.md`. For all-state database counts, rerun read-only `scripts/data_health_remote.sql` and refresh `reports/data_health_db_audit.json` before regeneration. No schema/data migration is included. Rollback removes the benchmark code and generated artifacts; Production is unchanged.
