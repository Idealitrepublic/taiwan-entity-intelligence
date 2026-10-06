# Product Consolidation

Status: P0 in progress (2026-10-06). Development and Preview only. The unrelated Pilot preparation working-tree changes are preserved.

The follow-up [P0 root cause audit](P0_ROOT_CAUSE_AUDIT.md) distinguishes empty
legacy counters, missing exact-identifier labor materialization, and the P01
report generated before its first Source bookmark. It records actual canonical
counts, owner/RLS/FK checks, the official labor provenance chain, repairs,
71 targeted tests and 160 DB checks. P0 acceptance remains open.

## P0.1 — Labor penalty regression

- Root causes: `tei-development` had zero `source_records` and `source_files` rows. The Labor Standards Act fallback URL resolved to an unrelated five-column file, while the data.gov.tw metadata parser ignored the nested `result` and current `resourceDownloadUrl` field.
- The existing MOL datasets 109896, 109897, and 110908 were downloaded from official resources and indexed in `tei-development` only. They contained 80,143 raw rows and 80,122 distinct indexed rows. Three external-source snapshot records identify the official URLs and hashes; no Storage object is claimed.
- Development quality check: 80,122 distinct IDs, zero missing source URL/source-file/raw provenance, and all 80,122 readable under the `anon` RLS role. Exact company-name candidates: FamilyMart 2, TSMC 5, President Chain Store 2. These are name matches, not identity merges; records with branch/operator names are deliberately not forced onto a company Entity.
- Existing Preview, without a code deploy, changed from zero to two FamilyMart labor records after the Development import. The company search, profile count, legacy graph category, penalty pane, official disposition number, date, and dataset-level source link were visible. The official dataset does not promise a permanent single-record URL, and the UI labels the link accordingly.
- Code changes repair official metadata discovery, preserve indexed Evidence source/retrieval/provenance fields, and label the legacy graph connection as an exact-name candidate. The importer is restricted to the named Development project and is idempotent.

## P0.2 — Graph at narrower widths

- The old three-column minimum exceeded 1024px. The layout now stacks the Graph and sidebars below 1120px while keeping Graph controls above its SVG. `Fit` computes the visible node bounds, centers them, and adjusts zoom.
- Local browser checks at 1440, 1280, 1024, and 768px found a visible Graph/SVG/sidebar and no document horizontal overflow. At 768px the company graph rendered six nodes, buttons remained within the Graph, Zoom changed to 110%, and Fit brought the graph to 90%.

## P0.3 — Report readability

- The HTML report now uses a landscape A4 print page, bounded two-column field rows, wrapping for long URLs and identifiers, natural Chinese line breaking, and page-break rules that may split large sections instead of clipping them.
- Targeted rendering tests cover long Chinese, unbroken English and URL values plus required CSS. A live print/PDF visual check remains pending; the local browser blocked direct `file:` navigation to the generated test artifact, so readability is not yet accepted.

## Verification gate and remaining work

- Targeted P0 tests: 23 passing at the last run; source/index/read checks above passed. Preview deployment [25def31](https://github.com/Idealitrepublic/taiwan-entity-intelligence/commit/25def3165db9540adeb64336290751faefae82cf) is READY at https://taiwan-entity-intelligence-kwr8xtrok-coldlight871029-9944.vercel.app/ (Preview target, not Production). Its workspace configuration points to `tei-development`.
- Preview read-only API checks: status reports 80,122 `source_records`; company 23060248 returns two labor penalties, two legacy Graph edges, and two Evidence records with source and retrieval metadata. Global Search for 全家便利商店 returns a live-fallback company result (HTTP 200). These checks do not substitute for the full authenticated browser journey.
- P0 is not accepted until a person opens/downloads a populated report in the new Preview and verifies landscape print/PDF, URL wrapping, and page breaks. The current browser session is signed in as a different pilot test account than the earlier P01 notes, so authenticated testing must use the intended Development test account.
- P1 high-density Graph clustering and mobile flow: not started.
- P2 terminology consolidation and Path Finder wording: not started.
- No Production migration, data write, environment edit, or deployment occurred.
