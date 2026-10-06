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

Implementation commit: `3f29c00a77086e9e08024195d1eb53fcc1c25a26`.
Preview: <https://taiwan-entity-intelligence-pvg9tnm2p-coldlight871029-9944.vercel.app/>.
Deployment `dpl_3UpBYxT5b2j59dWmHC1k4xWgNN1Q` is READY and has Preview target
(`target=null`). The workspace configuration explicitly points to Development.
Preview Search/Entity/Graph/Path/Evidence/Entity Report and status all returned
HTTP 200 with the expected canonical sample; unauthenticated P01 Workspace Report
returned HTTP 401. Deployment-scoped runtime logs contained no 5xx entries in the
30-minute verification window. This does not imply authenticated UI acceptance.

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
  A repaired Preview tab is left on the sign-in form with the P01 email filled;
  no password was supplied or read. The intended next step is to sign in there,
  select the existing P01 Workspace, save the real canonical Company/Relationship/
  Evidence/Graph, verify Watchlist and export again. Existing SOURCE remains intact.
- Populated-report print/PDF visual acceptance remains pending. Layout regression
  checks alone do not prove long-content pagination. No substitute/fake data was
  used to fill empty domain sections.
- P0 stays open; P1/P2 and new-feature work remain stopped.

## Independent Final Self-Audit — 2026-10-06, round 1

**Overall: PARTIAL. P0 OPEN. Product Consolidation NOT COMPLETE.**
This is a fresh browser/user-journey audit of implementation `3f29c00`, not a
promotion of the earlier unit-test/build results to UI acceptance. The user
explicitly authorized using the already signed-in **P05** account instead of P01
and subsequently chose to keep using P05 for now. P01's private data were not
edited. P1/P2 remain paused; findings in those scopes are recorded, not implemented.

Test target: the repaired Preview URL above, Development only. No code, schema,
RLS policy, Production configuration or public data was changed during this round.

| Requirement / boundary | Result | Actual verification / limitation |
|---|---|---|
| Authenticated P05 session | PASS | Workspace loaded owner-scoped rows and actual Create/bookmark/Watchlist requests succeeded. UI identifies `tei-pilot-p05@example.invalid`. This does not claim a fresh password login or refresh/expiry test. |
| Global Search / existing company-ID flow | PASS | Browser queried `04690983`: official registry company, one real labor penalty and existing officers/procurement flow remained visible. A name query `大魯閣` returned the published Company and separate live-registry results; selected the exact canonical result. |
| Company Overview / labor provenance | PASS | Canonical Profile displays the disposition, official penalty Evidence, MOEA identity Evidence and both official source URLs. Edge Evidence displays date 2024-07-17, TWD 50000, EXACT, original row ID and retrieved timestamp. |
| Desktop / narrowed Graph | PASS | Fresh checks verified actual inner widths 1440/1280/1024/768, two nodes/one edge, nonzero SVG, in-bounds Fit/Zoom controls and no document horizontal overflow. SVG widths 760/600/1009/753. Fit actually clicked at every size. |
| Mobile Graph / whole-product mobile acceptance | PARTIAL | Actual 390px public view has no horizontal overflow and retains Graph/controls, but node labels are very small and no simplified mobile mode exists. Later private-dialog resize requests measured 1440px, not 390px, so they are explicitly NOT accepted as mobile checks. Full mobile Search/Evidence/Workspace/Watchlist/Report flow remains unverified. Mobile redesign belongs to paused P1. |
| Path Finder Depth 1 / 2 / 3 | PASS (bounded sample) | Browser selected Company A and real Penalty B, ran all three limits, and independently observed the same correct one-hop shortest path with date/amount/Evidence/source. This does not prove a real two/three-hop intermediary scenario. |
| Relationship Range wording / tooltip / full bilingual terminology | PARTIAL | UI still exposes `max depth`, raw enum/source labels, English-only bookmark type buttons and technical Owner IDs. P2 wording/terminology work is not started; do not mark it PASS or silently begin it under a P0-only instruction. |
| Empty Workspace Report | PASS | Created a new P05 test Workspace and clicked View report before bookmarking. UI explicitly rejects export: Save an item before exporting; no misleading all-empty report is accepted. |
| Workspace owner / six bookmark types | PASS | P05 used a newly isolated Workspace and actually saved ENTITY, GRAPH, RELATIONSHIP, EVIDENCE, SOURCE and a factual NOTE. Six saved rows show identical owner/creator IDs; no pre-existing Workspace/item was deleted. |
| Populated Workspace Report assembly / download | PASS | Browser View report generated a titled report tab and Download produced a 43,712-byte HTML. User moved that same file to Desktop; static parsing confirms six saved items, one saved Evidence, two Profiles, one Key Relationship, one Penalty and three Sources. Graph contains the two real endpoints and one edge. Empty political/contracts/judgments/assets sections are correct for this sample, not filled with synthetic records. |
| Report preview visual / landscape print / pagination / tables | PARTIAL | Automation explicitly blocks the report's `blob:` URL. No alternate browser, file navigation or indirect workaround was used. User supplied the Desktop HTML, not a printed PDF. Content inspection and CSS cannot establish rendered wrapping, clipping or page breaks; the actual printed PDF and manual preview acceptance remain required. |
| Watchlist / Alerts | PASS (available-data subset) | P05 actually added the real Company, ran sync (one watched Entity, zero new notifications), selected read/unread filters and clicked read-all without an application error. Existing Evidence predates subscription, so zero notifications is correct. A genuine new alert's read↔unread transition remains unverified; no public fact or fake alert was created to force it. |
| Owner RLS / anonymous boundary | PASS (database level) | Fresh read-only SQL: P05 claims see own six items and zero P01 items; P01 claims see its original one item and zero P05 items. Anonymous table read is denied (SQLSTATE 42501). These are database-role checks, not a second browser login. |
| Cross-account browser attempt | PARTIAL | P05 Workspace selector shows only its own projects. User chose P05 only; a real second-account login and direct attempt to retrieve the new P05 Workspace/Report have not occurred. Do not replace this gate with admin/role impersonation. |
| Data retention / FK integrity | PASS (current-state check) | Company 2, Person 0, Politician 123, total Entity Evidence links 910, Evidence records 1529, Relationships 1031, raw source rows 80122 remain unchanged. Workspace items increase 1→7 only because of the six new P05 bookmarks. Broken bookmark references 0; original P01 SOURCE remains 1. Historical deletions are still not provable without an audit log. |
| Console / runtime | PASS (observed window) | Browser warning/error collection returned none for the checked page. Deployment-scoped Vercel error/fatal query for the 30-minute window ending 2026-10-06T12:47:57Z returned no entries. This is not a claim about all deployments or all historical HTTP responses. |
| Fresh targeted regression run | PASS | 47 tests rerun: reports, workspaces, watchlists, labor materialization/source regression, Graph v2 and relationship paths. No full build was rerun: only acceptance documentation changes, with runtime still `3f29c00`. Earlier 71 tests/160 DB/build are historical results, not this run's counts. |

### Retained real verification artifacts

- P05 acceptance Workspace: `552ce1b7-1550-49a3-b058-3db5af16b7fb`, named
  `P0 Self-Audit P05 2026-10-06`.
- Owner/creator: `c1c8b90f-7f39-4bba-a36a-14c69f685160` (P05).
- Six bookmarks and one watched Company are intentionally retained for inspection;
  they contain existing official records and the factual acceptance note only.
- User-provided downloaded HTML:
  `/Users/lengguangchen/Desktop/tei-workspace-552ce1b7-1550-49a3-b058-3db5af16b7fb.html`.
- The current-state read-only check and HTML parsing were rerun independently.
  An initial read-only query referred to the wrong table name, and a combined
  query intentionally denied at its anonymous-read step; neither performed writes.
  Corrected owner-role checks were separately verified. An unavailable optional
  HTML parser was replaced with Python's standard-library parser without installing
  dependencies. These diagnostic failures are not application-data regressions.

### Remaining acceptance gates (no automatic phase advancement)

1. User prints the actual populated report to PDF and supplies that PDF for
   visual page-by-page review, plus confirms browser preview legibility. The
   current HTML does not substitute for a printed artifact.
2. A different test account actually signs in and attempts the P05 Workspace and
   its report; P05-only SQL checks do not complete the browser gate.
3. Full mobile flow and actual notification-state transitions remain PARTIAL.
   P1 mobile/high-density graph and P2 terminology/Relationship Range remain
   deferred; they cannot make Product Consolidation COMPLETE while paused.

Do not repair an authentication/tool handoff by copying tokens, resetting passwords,
weakening RLS or manufacturing source records. Continue only within authorized P0
regressions; all unverified requirements retain PARTIAL until fresh evidence exists.

## P0 follow-up — actual PDF download, 2026-10-06

The user's downloaded artifact was HTML, not PDF. The round-1 download PASS
above means successful **HTML delivery only**, not acceptance of a PDF download.
This newly identified P0 requirement failed at baseline and is repaired in the
existing report boundary; overall acceptance remains **PARTIAL / P0 OPEN**.

Root cause: both View and Download requested `format=html`; Download created a
`text/html` Blob with an `.html` filename. No PDF renderer existed. This was not
lost data, a publication/RLS issue, or a malformed PDF accidentally named HTML.

Bounded changes: preserve JSON and HTML previews; add actual `format=pdf`
rendering from the identical report projection, PDF binary WSGI transport and
attachment header. Download now checks MIME and `%PDF-` bytes, and saves `.pdf`.
ReportLab uses a checked-in, OFL-licensed Chinese font, landscape A4, full-width
field/value tables, long-string wrapping, row splitting and repeating headers.
URLs are references only; the renderer never fetches them. No schema, public
data, identity matching, ownership, RLS, Graph layout or Production change.

| Verification | Result | Evidence / boundary |
|---|---|---|
| Genuine PDF / Chinese embedding / landscape / source links | PASS (local) | Parsed PDF bytes, embedded TrueType font, A4 width > height, expected Chinese/source/date content and original URL annotations. |
| Long Chinese, unbroken English identifier, 539-character URL / pagination | PASS (local) | Full text retained across four pages; all four rendered pages inspected, no clipping, single-character column or table overflow. Known repeated headers/footer are removed only for the text continuity assertion. |
| Actual P05 content / PDF layout | PASS (local projection) | Read-only Development SQL under P05 RLS retrieved the existing six items; public anon Entity reads assembled two Profiles, one Relationship/Penalty, one saved Evidence, two Graph nodes/one edge and three Sources. All 26 PDF pages were rendered and visually inspected; character geometry stayed inside page margins. This is explicitly not a replacement for a logged-in HTTP download. |
| Authentication / same projection / binary response / HEAD | PASS (regression) | Tests reject unauthenticated Workspace PDF, use the existing service, verify PDF MIME/attachment/no-store/Content-Length, and zero HEAD body. |
| Targeted suite / DB / build | PASS | 52 targeted tests; 160 PGlite DB checks; Ruff/web syntax; 50-module WSGI build including an actual Chinese PDF render. Initial DB runner lacked `python` on PATH; corrected to the existing venv and reran successfully. |
| New Preview company PDF / actual UI download | PASS | Corrected Preview `796a4fc` READY; PDF endpoint returns HTTP 200/application-pdf/attachment, 16-page actual PDF with disposition/amount/source. Browser clicked Company Download and created a new valid `.pdf` in Downloads. All 16 Preview PDF pages rendered and visually inspected. Anonymous Workspace PDF request returns 401. |
| P05 Workspace PDF / actual owner-scoped download | PASS | User signed P05 into the new Preview. Its six existing bookmarks loaded; actual Download created a genuine 26-page `.pdf`, retaining Profiles, Relationship/Penalty, saved Evidence, Graph endpoints/edge and Sources. All 26 downloaded pages were rendered and inspected, with no out-of-margin characters. No token/session copying or RLS change was used. |
| Manual browser print / HTML preview visual | PARTIAL | PDF layout is directly verified, but actual browser print dialog/output and blocked `blob:` HTML preview were not inspected. No security/tool-access workaround was used; the old Desktop HTML is unchanged. |
| Mobile Workspace / download control | PASS (bounded check) | Actual viewport 390px, document width 375px, dialog width 337px, Download visible and in bounds. Button clicked without errors; no claim that every mobile page has passed. |

The temporary 26-page PDF is local QA output generated from a read-only owner
snapshot, not a new public record or an admin-authenticated HTTP export.
Duplicate provenance is preserved for compatibility; compact presentation and
full bilingual field consolidation remain paused P2 work. Cross-account browser
acceptance still needs another real account, which the user has deferred.

Deployment self-audit caught Vercel installing from `pyproject.toml`, not
`requirements.txt`. The first PDF Preview (`93f813f`) was therefore not accepted
as a working runtime. Added the same three pinned dependencies to pyproject and
a bundle-check assertion that both manifests agree; reran the build after this
configuration change. Only the corrected Preview is eligible for PDF acceptance.

Corrected runtime commit: `796a4fc5fede8fdfb4872d79ae0103cde3bc740c`.
Git push succeeded on the non-production `product-consolidation/p0-p2` branch.
Deployment `dpl_Br4bJNqujtEk55AuQXvfkRoj13U5`: READY, target Preview,
Python 3.12, build log completed without error; configuration read confirms the
Development private URL and a public credential only. No Production change.

Preview: https://taiwan-entity-intelligence-1xtdv6kh9-coldlight871029-9944.vercel.app/

Company UI download retained:
`/Users/lengguangchen/Downloads/tei-entity-a3bcec97-5ef2-5bb3-ba8f-bde444835ec5.pdf`.
Vercel error/fatal logs for this deployment, window ending
2026-10-06T13:11:04Z: none. The signed-in P05 browser also has no warning/error
logs in the captured window. A separate-account browser access attempt and
manual preview/print acceptance are still required; P0 remains OPEN, not Product
Consolidation COMPLETE. Unrelated Pilot working-tree changes were preserved and
not committed.

### P05 fresh end-to-end follow-up on corrected Preview

The user's newly signed-in tab (not the stale sign-in tab) was used to download
the private PDF. Retained artifact:
`/Users/lengguangchen/Downloads/tei-workspace-552ce1b7-1550-49a3-b058-3db5af16b7fb.pdf`.
PDF generation carries the actual owner-filtered items, not the earlier local
snapshot adapter. Full-page rendering confirms bilingual content, identifiers,
URLs, table boundaries, repeated headers and pagination on all 26 pages.

Then independently reran Search → canonical Company Profile → Graph → Path
depth 1/2/3 → Edge Evidence → existing owner Workspace → Watchlist sync. All
three Path limits produced the same correct one-hop sample with official source,
date and amount. Graph Fit at measured 1440/1280/1024/768px retained nonzero SVG
width 760/600/1009/753px and no horizontal document overflow. The Graph node and
Evidence controls were operated by keyboard; this does not prove every pointer
hit target. Watchlist retained one real Company and no fabricated notifications.

Read-only data recheck after downloads: raw rows 80122, canonical Companies 2,
People 0, Politicians 123, total Entity Evidence links 910, Evidence records 1529,
Relationships 1031, Workspace items 7, broken bookmark foreign keys 0. No data
changed in this follow-up, other than the normal owner-scoped Watchlist sync.

PDF download regression is resolved. Overall audit stays PARTIAL because a
different account's real browser attempt and manual preview/printing are pending;
whole-product mobile and paused P1/P2 terminology/layout work are not accepted.

## Final Phase A reopening — 2026-10-07

**P0 OPEN; Product Consolidation NOT COMPLETE.** Historical PDF downloads above
do not establish that a fresh Workspace export currently works.

- The user confirmed intentionally clearing P05's previous bookmarks. This is
  not evidence of data loss or a pipeline regression; no deleted items were
  restored. Fresh public totals remain: Company 2, Person 0, Politician 123,
  Entity Evidence links 910, Evidence 1,529, Relationships 1,031 and indexed
  source records 80,122. Legacy company/people/evidence counters remain zero;
  canonical and legacy tables are deliberately distinguished.
- P05 created `Final Phase A P05 2026-10-07` through the actual Development
  browser. Five real bookmarks reference the Company, its labor Relationship,
  Evidence, Graph and official MOL source. Read-only checks confirm the owner,
  intact foreign keys and the published exact-identifier labor chain, date
  2024-07-17, amount TWD 50,000 and source/retrieval provenance. No public data,
  schema, RLS, source-ingestion checkpoint or Production setting changed.
- Fresh Workspace Download on the previous Preview failed: the user saw no
  file or error; a 20-second browser download observation also expired, and
  the expected file was absent. Preview runtime nevertheless recorded the
  authenticated `format=pdf` request as HTTP 200 after 10,364.6 ms. This narrows
  the failure to browser delivery, not proof of a failed owner/RLS query.
  The precise browser suppression reason is not yet independently proven.
- The old code asynchronously clicked a detached anchor and provided no
  pending/success/error state or user-activated retry. The repair retains a
  genuine PDF download link in the active modal subtree, or the public report
  panel when no modal is open, with an explicit Save PDF retry and bounded URL
  cleanup. It validates MIME and PDF signature, bounds generation time,
  prevents duplicate requests and clears expired private authentication. It
  never embeds a token in a URL or navigates/closes the main application.
- Path repair keeps the existing shortest-path API and 1/2/3 semantics,
  presents Relationship Range, aborts obsolete selections/requests and exposes
  bounded-search/no-route states without asserting absence of relationships.
  A legacy company gets canonical Path actions only after a published exact
  uniform-number match, never from a same-name fallback.
- Graph lazy loading no longer automatically opens the root information
  overlay, which was observed obscuring a narrow-window edge pointer target.
  Stale graph responses cannot replace a newer graph. No clustering/layout
  redesign was started; existing responsive and labor ingestion repairs remain.

| Current gate | Result / actual method |
|---|---|
| Owner bookmark writes / labor provenance | PASS: actual P05 UI plus read-only Development SQL. |
| Different-account browser isolation | PARTIAL: user can currently use only P05. SQL authenticated-role checks reject P01's Workspace for P05, but are not a second-account login. |
| 1/2/3 shortest-path backend cases | PASS: real Development public RPC gives a 2-edge Company→Committee and 3-edge Company→Politician case, with shorter ranges returning no route. Fresh repaired UI remains pending. |
| Targeted code regression | PASS: 62 Python tests and 14 shipped-JavaScript function cases; these are not a full browser acceptance. |
| Fresh owner PDF file / full render / browser print | FAIL / pending repaired Preview: no fresh file yet. Do not reuse yesterday's artifact as proof. |
| Full self-audit / remaining Final Phases B–H | NOT TESTED / deferred until Phase A P0 passes. |

Browser `chrome://downloads` and direct Blob navigation were blocked by tool
policy; no alternate automation/security bypass was used. Local file checks and
normal browser downloads remain valid checks. Preview configuration extraction
through CLI failed before returning data; it was not treated as an empty env or
permission to connect a local server to Production. Runtime logs are scoped to
Preview only; a failed wider log query is not recorded as zero runtime errors.
