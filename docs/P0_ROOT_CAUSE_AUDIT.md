# P0 data-chain root cause audit — 2026-10-06

Scope: `tei-development` (`canqjiokrtcxkwblhmml`), local WSGI and branch Preview.
No Production connection, write, migration, environment edit or deploy was made.
P1/P2 remain stopped. No synthetic records were loaded into Development.

## Findings and actual counts

The two symptoms do not have one proven deletion/RLS cause. There is a shared
architectural boundary between source-index/live-company views and canonical
published facts, plus a misleading legacy-only status counter.

| Store | Before repair | After repair | Public RLS after repair |
|---|---:|---:|---:|
| Legacy `companies` / `people` / `evidence` | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Canonical Company Entities | 1 | 2 | 2 |
| Canonical Person Entities | 0 | 0 | 0 |
| Canonical Politician Entities | 123 | 123 | 121 |
| All canonical Entities | 140 | 142 | 140 |
| `entity_evidence` links | 907 | 910 | 908 |
| `evidence_records` | 1,527 | 1,529 | 911 |
| Relationships | 1,030 | 1,031 | 1,027 |
| Canonical penalty Relationships | 0 | 1 | 1 |
| `source_files` / `source_records` | 3 / 80,122 | 3 / 80,122 | 3 / 80,122 |
| Workspaces / saved items | 6 / 1 | 6 / 1 | owner-scoped |

The Phase 1 migration explicitly leaves the legacy tables untouched. The
Database panel incorrectly presented their counts as all Companies/People/Entity
Evidence. Canonical Entity Evidence was never zero in this audit. The existing
status endpoint now keeps backward-compatible legacy keys and separately counts
RLS-visible canonical rows; the panel labels those counts as published records.
Person remains zero: live officer names are not silently converted to resolved
Person identities. The 121 public Politicians are reported separately from draft
rows and are included in the panel's explicitly labelled people/politicians count.

No broken Workspace references were found. Raw-index and private-item counts were
preserved. There is no evidence of deletion causing these symptoms; however,
without a historical item-deletion audit log, this is not proof that no user ever
deleted a bookmark.

## Pipeline trace

| Boundary | Finding / repair |
|---|---|
| `source_files → source_records` | Three official MOL CSV snapshots, 80,122 distinct raw rows, official URLs and hashes; retained unchanged. |
| normalization/materialization | Previous repair stopped at the raw source index. `uniform_number` was empty for every row and no canonical Penalty or penalty Relationship existed. Added an explicit identifier stage. |
| entity resolution | One official row contains a terminal tab-separated `04690983`. MOEA confirms the same uniform number and official company name. Name-only records and HTML numeric references are rejected for canonical publication. |
| companies/people | Canonical records are in `entities`; filling legacy tables to make counters nonzero would duplicate the model. No name-based Person materialization is performed. |
| Evidence / Relationships | Exact-identifier materialization creates immutable MOEA identity Evidence and MOL penalty Evidence, Company/Penalty fact links, and `RELATED_TO_PENALTY` with primary Evidence. |
| auth / RLS | All inspected tables have RLS. P01 owner-role read sees one owned Workspace and one SOURCE item; P02 Workspace is invisible. No policies or grants were broadened. This SQL check is not a browser sign-in test. |
| `workspace_items` | P01 has one SOURCE bookmark, correct owner/creator, and no ENTITY/GRAPH/RELATIONSHIP/EVIDENCE items. Foreign-key orphan count is zero. |
| published public reads | Entities/Evidence use `publication_status='published'`; Relationships use `status='published'`. These are correct public boundaries. SOURCE/NOTE bookmarks have no publication column and bypass no canonical publication rule. |
| report assembly/export | Sources already enter Sources directly. Fixed empty-Workspace export, omitted visible saved Note/Evidence content, missing endpoint profiles for relationship-only bookmarks, duplicate shared edges, and handling of withdrawn saved references. |

The downloaded P01 report generated at **2026-09-29 15:44:00.858798 UTC**.
Its currently saved SOURCE was created at **15:47:44.687058 UTC**, 3 minutes
43.828 seconds later. An all-empty report at the earlier time is therefore
consistent with an empty Workspace. Reassembling the actual current P01 rows
under its owner RLS returns one saved item and one rendered Source. Entity and
relationship sections properly remain empty until such items are saved; a URL
alone is not evidence for invented Entities or relationships.

## Official labor provenance sample

- Company: 大魯閣實業股份有限公司, official uniform number **04690983**.
- Official source row: `mol:64b2b93c4c7a53c5ee9d3511412b1c04bfbd8aa4397272e76f224f2e396f602b`.
- Snapshot: `45a7a9a1-ece6-5325-8b23-c6a7808f80aa`; the official raw company label
  includes that uniform number, rather than a number inferred from the name.
- Disposition: 新竹市 `府勞動字第1130101133號`, **2024-07-17**, **TWD 50,000**.
- Company Entity: `a3bcec97-5ef2-5bb3-ba8f-bde444835ec5`.
- Penalty Entity: `401a4fda-6378-5ed1-9935-24765e78d526`.
- Relationship: `dec90344-b7e9-53b5-ab60-e310128634a5`, `EXACT`, published.
- Primary Evidence: `4dfc6073-0b24-5482-b861-fe0455d3a8fd`.
- Source: <https://data.gov.tw/dataset/109896>; retrieved/indexed
  **2026-10-06T08:01:44.201920Z**. Evidence retains source-row and snapshot IDs,
  original company label, disposition/date/authority/law/amount and matching method.
- Local anonymous HTTP reads confirm the Search identifier result, Entity fact
  link, two Graph nodes/one edge, one-hop shortest path, primary Evidence, and
  Entity report with one Penalty and two Sources. The browser also displays the
  disposition, date, amount, Evidence and official source.

Only one explicit identifier row was found in this snapshot, and reapplying it
does not increase counts. **80,121 name-only/unresolved index rows remain source
observations, not published exact canonical relationships.** This is a measured
coverage limit, not a claim that all 80,122 penalties were resolved. Existing
legacy company-name candidate lookup remains available without legal-identity
merges. No new source was introduced.

## Reproducibility and rollback

- Read-only counts: `.venv/bin/python scripts/audit_p0_data_chain.py`.
- Identifier-stage dry run: `.venv/bin/python scripts/materialize_labor_penalties_dev.py`.
- Apply the verified existing rows only in Development: add `--apply`.
- For subsequent existing-source imports, the importer supports `--apply
  --materialize`; the raw import and canonical stage report success separately.
- Connection host/user must pass the existing strict Development guard. Database
  credentials use child-process PG environment variables, never command arguments.
- No schema migration or reset is needed. If this materialization is rejected,
  retract the named Relationship and withdraw the new Penalty/Evidence after
  inspecting references; retain the original raw rows and immutable provenance.
  Never delete Workspace bookmarks or broadly reset the database. A code rollback
  must retain the previous labor ingestion and Graph responsive fixes.

## Verification and remaining P0 gate

- 71 targeted tests passed: materialization, source regression, status counters,
  reports, Workspace, Watchlist, Search, Graph and Path Finder.
- 160 PGlite DB checks passed: migrations, idempotency, constraints, RLS and
  retraction. Development read-only checks separately verified real rows and owner
  boundaries. Neither count means a real P01 browser sign-in passed.
- Four actual browser viewport widths (1440/1280/1024/768) retained two Graph
  nodes, one edge, SVG, Fit and controls, with no horizontal document overflow.
  Shortest path and keyboard Edge Evidence inspection passed locally.
- Lint, web JavaScript syntax and the 49-module WSGI build passed. The browser
  downloaded the real Company report (28,024 bytes); its contents retain the
  disposition, TWD 50,000, dataset source and landscape CSS. The browser automation
  download-event hook timed out, but the newly downloaded file itself was verified.
- The existing old Preview also returns the materialized Company, Graph,
  one-hop Path and Evidence. On opening the private Workspace, its cached P05
  session received Authentication required and the UI returned to sign-in. No
  test Workspace/bookmark/watchlist was created, and P01 data were untouched.
- Actual P01 browser Auth → Workspace → Watchlist → Report on the repaired
  Preview remains pending: a current P01 sign-in is required. No password reset,
  token extraction, session copying, admin-auth bypass or ownership edit was used.
- Populated-report print/PDF visual acceptance remains pending. Layout regression
  checks alone do not prove long-content pagination. No substitute/fake data was
  used to fill empty domain sections.
- P0 stays open; P1/P2 and new-feature work remain stopped.
