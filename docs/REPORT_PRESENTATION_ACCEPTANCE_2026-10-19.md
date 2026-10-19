# Development report presentation acceptance — 2026-10-19

Scope: Development/Preview report presentation only. The JSON report projection,
Workspace ownership checks, publication filters, Entity/Relationship/Evidence
model, and Production are unchanged.

The layout takes the *pattern* of a compact investigation summary, grouped
findings, provenance register, and explicit coverage caveats from international
public-record investigation tools (such as [OpenCorporates](https://api.opencorporates.com/documentation/API-Reference)
and [OCCRP Aleph](https://docs.aleph.occrp.org/users/getting-started/homepage/)),
not their branding or data. HTML and PDF now share one display-only projection:

1. Investigation title, methodology, generated time, three summary counts.
2. Saved items (Workspace only), Entity profiles, relationships, contracts,
   judgments, penalties, assets, graph scope, and sources, grouped by topic.
3. Each relationship includes its type, endpoints, date/amount when present,
   primary Evidence, source URL and retrieval time. Other source facts remain
   available in the unchanged JSON response.
4. Empty topics appear once at the end instead of repeating a full empty card.
   Truncation and unavailable saved references are flagged.

Local verification: 19 focused report/PDF tests passed; full repository tests,
lint and build passed. The generated sample PDF was rendered to an image and
inspected for landscape layout, Chinese glyphs, readable table columns, source
link and footer. Long Chinese/English strings and URLs remain covered by the
PDF regression tests. The sample is synthetic; a real signed-in Workspace PDF
and printout remain **unverified** until a Development test session is available.

## Three-step gate status

1. **Owner/RLS and private export — PARTIAL.** The Development database was
   queried read-only on 2026-10-19: `investigation_workspaces`,
   `workspace_items`, `watchlist_entries`, and `watchlist_events` all have RLS
   enabled and owner policies. The checked-in migrations express owner-ID
   predicates for SELECT/INSERT/UPDATE/DELETE where those operations are
   granted. Thirty-three focused Workspace/Watchlist/Report/PDF tests pass.
   This is not a real P05-versus-P06 authenticated cross-account attempt;
   an actual private Workspace download/print from the new Preview is also
   pending. Do not close P0 on these indirect checks alone.
2. **Representative data and traceability — PARTIAL.** The current read-only
   Development count is 462 published Companies, 121 Politicians, one Contract,
   and one Penalty. A joined exact-ID → published relationship → active
   Evidence query returned three representative records:

   | Company / exact 統編 | Published relationship | Provenance in Development |
   | --- | --- | --- |
   | 大魯閣實業股份有限公司 / 04690983 | Government contract | 政府電子採購網; original award URL; retrieved 2026-10-18 |
   | 大魯閣實業股份有限公司 / 04690983 | Labor penalty | MOL/penalties; data.gov.tw dataset 109896; retrieved 2026-10-06 |
   | 都一處有限公司 / 29072066 | Political contribution to 王鴻薇 | 監察院政治獻金公開查閱平臺; original download URL; retrieved 2026-09-23 |

   The Company IDs also have published Registry Evidence. 中華電信 / 96979933
   has published Registry Evidence retrieved 2026-10-18 but no published
   relationship in this sample query. These checks validate stored linkage and
   provenance fields, **not** that every original URL was reopened or that
   national source coverage is complete. The dated 2026-10-19 coverage baseline
   reports 1,028 evidence-backed published edges but very few procurement,
   labor or political edges and no verified company-judgment edge. Name-only
   labor and judicial rows must remain unmerged.
3. **Real-user Pilot — NOT RUN.** The task scripts and response forms already
   exist, but no four-person participant session has been conducted. Preview
   identity, consent, real task time/error feedback, and cross-account
   observation remain acceptance gates. Synthetic tests are not user outcomes.

The report redesign and read-only checks do not authorize a Production change.
