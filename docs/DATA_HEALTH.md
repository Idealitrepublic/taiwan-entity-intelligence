# Data Health — DATA Phase 6

Generated: 2026-09-22T19:12:48.583777+00:00

This is a read-only, fixed-sample benchmark, **not national coverage**.
Unknown values are not zero. Political rows test public publication presence, not adapter fixtures.

| Source | Scope | Coverage | Freshness h | Errors | Duplicate | Provenance | Severity |
|---|---|---:|---:|---:|---:|---:|---|
| company_registration | 3 fixed valid-company identifiers; live MOEA | 1.0 | 0.0 | 0 | 0.0 | 1.0 | OK |
| directors | same 3 identifiers; presence only | 1.0 | 0.0 | 0 | 0.0 | 1.0 | OK |
| procurement | same 3 identifiers; mirror response, not award recall | 1.0 | unknown | 0 | 0.0 | 0.0 | Medium |
| labor_penalties | indexed company-name reads; national recall unknown | unknown | 349.1 | 0 | 0.0 | 0.0 | Medium |
| judiciary | 3 official known-case JIDs; not historical recall | 1.0 | 166.4 | 1 | 0.0 | 0.0043 | High |
| politicians | public published-data presence floor (>=1); not population coverage | 0.0 | unknown | 0 | unknown | unknown | High |
| political_contributions | public published-data presence floor (>=1); not population coverage | 0.0 | unknown | 0 | unknown | unknown | High |
| asset_declarations | public published-data presence floor (>=1); not population coverage | 0.0 | unknown | 0 | unknown | unknown | High |
| entity_resolution | private resolution_candidates excluded by RLS | unknown | unknown | 0 | unknown | unknown | Unknown |

## Findings and disposition

- **High — publicly visible political data absent:** public presence probes returned zero, so draft ingestion has not yet become verified public coverage. Do not publish or mutate the shared Production database from this audit; review official source batches, RLS and publication separately. This release gate remains open.
- **High — judicial sync failure:** the checked-in status has an HTTP error although older `last_sync` exists. This report counts the error and never treats the timestamp as proof of a clean latest attempt. The sync now preserves the last usable index on failure; historical judiciary coverage remains a documented gap.
- **Medium — procurement/penalty provenance:** live mirror and legacy source records may lack per-row retrieval time, original record URL or provenance. Missing fields remain visible as unknown/partial; they are not fabricated.
- **Unknown — private resolution candidates:** anonymous read access is intentionally denied. Precision/recall from labeled tests does not establish live population quality.

## Reproduce and rollback

Run `python scripts/data_health.py --json reports/data_health.json --markdown docs/DATA_HEALTH.md`. Only GET requests are issued; no schema/data migration is included. Rollback removes the generated report and benchmark code; Production is unchanged.
