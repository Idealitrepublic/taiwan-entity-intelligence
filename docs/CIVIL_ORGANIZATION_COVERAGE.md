# Civil-organization source coverage — Development, 2026-10-25

**Scope:** official roster *observations*, not a deduplicated count of legally
registered or currently active organizations. No Production database, secrets,
or deployment were changed. A same-name row from another roster remains a
separate source-scoped Entity; no person or company relationship is inferred.

## Reconciled Development state

| Source group | Published Entity + Evidence rows | Notes |
|---|---:|---|
| Previously verified 16 official roster sources | 38,189 | Includes 23,209 historical MOI nationwide people's-association rows, three complete local-government rosters, unions and sectoral foundations |
| 68 newly profiled official CSV datasets | 13,583 | Exact dataset, download URL, headers, encoding, expected row count and scope are recorded in [`src/civil_roster_manifest.json`](../src/civil_roster_manifest.json) |
| [Keelung official ODS](https://data.gov.tw/dataset/165174) | 823 | Original ODS hash, sheet and row retained; personal/contact fields discarded |
| [Yilan official 2026-09-30 CSV](https://sntroot.e-land.gov.tw/cp.aspx?n=10437) | 1,619 | Local people's-organizations roster; source category retained |
| [Tainan social-welfare foundation JSON](https://data.gov.tw/dataset/102929) | 93 | Original JSON hash, item number, permit date/number and raw status retained |
| [Yunlin official 2026-07-13 XLSX](https://social.yunlin.gov.tw/News_Content.aspx?n=746&s=578203) | 1,881 | Official row number, original XLSX hash and sheet/row retained; five names carry a source `休會` prefix, so no current-active claim |
| [Hsinchu City official category pages](https://society.hccg.gov.tw/ch/home.jsp?id=161&parentpath=0,3,34) | 1,023 | All 12 listed categories; each category's page URL, update date, sequence and checked row count retained |
| **Total** | **57,211** | **89 official roster sources; 57,211 Evidence links** |

The separate [Finance Ministry nonprofit tax file](https://data.gov.tw/dataset/34147)
contains **99,788 tax-source observations**. Tax registration alone does not
establish legal form; these are **not** counted as CivilOrganization Entities.

New CSV sources comprise two general county rosters (984 rows), 11 community
association subset/historical rosters (3,015), 14 additional Taichung people-group
categories (4,172), 12 additional Kaohsiung categories (3,232), and 29 central,
local, religious, sectoral or government-funded foundation sources (2,180).
Cooperatives, award recipients, subsidies, aggregate statistics and committee
branch offices were not silently classified as civil organizations.

The read-only Development audit (`python3 scripts/audit_civil_rosters_dev.py`)
reconciled all 73 new source row counts: **0 mismatches, 0 missing/duplicate
Evidence links, 0 missing source URL / retrieved timestamp / snapshot hash**.
RLS is enabled on `entities`, `evidence_records` and `entity_evidence`. An
anonymous-role searches of a Yunlin and a Hsinchu roster name each returned
one published result; an anonymous-role count returned all **57,211** roster
entries. The read-only database audit found **57,211** Evidence links and
**411.9 MB** used, below the Supabase Free 500 MB
database limit, leaving limited headroom for additional imports and indexes.

## Reproduction and source integrity

The government [catalog export](https://data.gov.tw/datasets/export/csv?type=dataset&order=pubdate&qs=&uid=)
was downloaded on 2026-10-24, then each selected official file was downloaded
and profiled on 2026-10-25. The catalog export omitted at least Yilan's current
roster, which was obtained from the county's own official page. All source bytes
were kept outside Git with private permissions. Evidence stores the official
dataset/page URL, download URL, source scope, snapshot SHA-256, row locator and
retrieval time. ODS/JSON conversions additionally retain their **original**
file SHA-256 and source item location. The Hsinchu category snapshot contains
only names and source locations; the county's original HTML contact fields are
discarded. Contact addresses, phone numbers and
officers' names from roster rows are not copied into these Entity or Evidence
projections.

The parser rejects changed headers, invalid names/rows and source row-count
drift before a Development import. `scripts/ingest_official_civil_rosters_dev.py`
requires `TEI_DEV_DATABASE_URL` to identify `tei-development` and refuses an
unreviewed second snapshot for an existing source. It does not use or alter
Production credentials. For source refreshes, review additions, removals,
renames and status changes before publishing a new version.

## Limits

The [nationwide gap register](CIVIL_ORGANIZATION_NATIONWIDE_GAP_REGISTER.md)
tracks jurisdictions and authorities with live-only, withdrawn, TLS-failing,
403, stale or otherwise unavailable sources. **This is not a claim that all
Taiwanese organizations or every competent authority are covered.** Source
scope varies, many files are historical or only one category, and same-name
cross-source entities are not linked without a verifiable identifier. Search
hits are source observations, not a current registration certificate.
