# Civil-organization source coverage — Development, 2026-10-24

Scope: **source observations**, not unique legal organizations. No Production
database or environment change. Data remains source-scoped; no same-name merge.

| Official source | CSV rows | Development rows | Publication |
|---|---:|---:|---|
| [MOI national people's associations](https://data.gov.tw/dataset/13603) | 23,209 | 23,209 Entity + Evidence | Historical roster observation |
| [MOI national civil foundations](https://data.gov.tw/dataset/152434) | 17 | 17 Entity + Evidence | Source-scoped roster observation |
| [MOL directly supervised unions](https://data.gov.tw/dataset/6278) | 8 | 8 Entity + Evidence | Source-scoped roster observation |
| [MOL national union federations](https://data.gov.tw/dataset/6278) | 11 | 11 Entity + Evidence | Source-scoped roster observation |
| [MOL provincial union federations](https://data.gov.tw/dataset/6278) | 41 | 41 Entity + Evidence | Source-scoped roster observation |
| [MOL county/city union federations](https://data.gov.tw/dataset/6278) | 104 | 104 Entity + Evidence | Source-scoped roster observation |
| [MOL national industry union federations](https://data.gov.tw/dataset/6278) | 79 | 79 Entity + Evidence | Source-scoped roster observation |
| [MOF nonprofit tax-unit records](https://data.gov.tw/dataset/34147) | 99,788 | 99,788 tax source observations | **Not Entity/NGO-verified** |
| [Taipei City people's organizations](https://data.gov.tw/dataset/121714) | 4,176 | 4,176 Entity + Evidence | Local source-scoped observation |
| [Tainan City people's organizations](https://data.gov.tw/dataset/53472) | 3,505 | 3,505 Entity + Evidence | Local source-scoped observation; dissolution field retained |
| [MOI national civic foundations](https://data.gov.tw/dataset/173726) | 8 | 8 Entity + Evidence | Source-scoped permit roster observation |

Total: 31,158 published civil-organization roster observations with 31,158
Evidence links; 99,788 additional tax-source rows staged separately. The
observations may contain duplicates across rosters. There are zero inferred
cross-source organization relationships. The tax file has 99,787 syntactically
valid eight-digit IDs and one invalid ID retained with a flag; it contains
zero blank names and zero duplicate valid IDs in this snapshot. Tax identity
does not establish legal form. Development database size after ingestion was
313 MB, below the Supabase Free plan 500 MB database read-only threshold.
Tainan's dissolution field is `/` in 2,058 rows (a placeholder, **not** a
dissolution finding), blank in 825, a date-like string in 614, and another
nonblank value in 8. For non-placeholder values the profile shows the raw
field with a source-check warning; it does not infer a current legal status.

## Reproduction and safety

The downloaded CSV bytes are stored outside the Git repository in a private
local snapshot directory, mode `0700`; each file is `0600`. Their hashes and
row locators are retained in Evidence or the tax source table. Re-run the
ingestion commands only against `TEI_DEV_DATABASE_URL`, and verify that it
targets `tei-development`. Changed snapshots are blocked pending explicit
version/withdrawal review. Tax source observations are publicly readable only
when `publication_status='published'`; ingestion is not exposed to anon users.

Run `tests/test_civil_organizations.py`, `tests/entity_schema.test.mjs`, and
read-only SQL counts for source rows, Evidence links, duplicate identifiers,
missing provenance and RLS. A row absent from the source cannot be counted as
covered. A live search hit is not proof of current registration.

## Known gaps; not labeled complete

- Local-government associations are managed by county/city governments. Taipei
  and Tainan snapshots are now in Development; other local jurisdictions still
  require a source inventory and bulk-file validation. The Hsinchu City
  [official CSV](https://data.gov.tw/dataset/129137) was not imported because
  its HTTPS certificate chain failed validation; TLS checks were not bypassed.
- Foundations under other sectoral competent authorities, religious groups,
  charities and other nonprofit forms require separate official registries.
- The MOF tax file is only a candidate crosswalk. Even a matching name or tax
  ID must be checked against a registration record before an Entity merge or
  relationship is published.
- Current operational status, dissolutions, changed names and cross-snapshot
  continuity are unverified. The MOI historical roster is not a current-status
  service; source metadata refresh schedules are not evidence of individual
  row freshness.
