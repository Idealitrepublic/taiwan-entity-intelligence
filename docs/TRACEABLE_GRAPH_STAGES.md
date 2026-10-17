# Traceable graph: stages and Development baseline

Scope: existing company, person, procurement, labor-penalty, and judicial sources only. No Production changes or new source ingestion. A source mention is not a verified Entity relationship.

## Stages

1. **Scope and provenance display — completed.** Show query scope, source locator, retrieval time, match rule, and candidate status on graph observations. Preserve interactive source links and Evidence.
2. **Coverage baseline and existing-source entry into graph — in progress.** Reconcile indexed, live-only, candidate, and published counts. Identify safely materializable records; do not publish name-only matches. Re-run `scripts/audit_graph_coverage_dev.py` against the explicit Development connection before claiming coverage.
3. **Company/person identity verification — accepted for the published Development scope.** Two published companies have exact eight-digit official IDs and active Official Registry Evidence; all 121 published politicians have Legislative Yuan IDs. Ordinary people have zero published canonical identities; director-name observations remain source-scoped and must not be merged by name. All 1,025 published politician-source edges match the official legislator number in their primary Evidence locator. No wider identity coverage is implied.
4. **Evidence review per edge — accepted for the published Development scope.** All 1,027 published edges have permitted endpoint roles, published endpoints, active published primary Evidence with a source URL and locator, non-future observation/retrieval times, and a primary support link. There are zero unsupported, duplicate, or low-confidence published edges. A labor-penalty spot check is recorded below. These checks do not validate source-only mentions as canonical links.
5. **Graph presentation and interaction acceptance — implementation and automated checks complete; Preview acceptance pending.** Added a mobile node/evidenced-link list so SVG-only interactions are not required on narrow screens, while keeping the full desktop diagram. Corrected the "other published companies" count and the people/politicians label. Desktop geometry at 1440/1280/1024/768 px and 390 px list interaction pass targeted browser tests; live Preview still needs checking.
6. **Development/Preview integration acceptance — pending final Preview check.** Test Search → Entity → Graph → Path Finder → Evidence against real Development data, including empty states and cross-source consistency, before any release decision.

## Reproducible baseline

Read-only Development audit on 2026-10-17 (`tei-development`, project ref `canqjiokrtcxkwblhmml`):

| Measure | Actual count | Interpretation |
| --- | ---: | --- |
| Published canonical companies / ordinary people / politicians | 2 / 0 / 121 | Not a count of all companies or people available from live APIs |
| Published contract / judgment / penalty entities | 0 / 0 / 1 | Contract and judicial observations are not yet canonical published edges |
| Published contract / judgment / penalty edges | 0 / 0 / 1 | Only one labor penalty has a published company relationship |
| All published edges with active primary Evidence and published endpoints | 1,027 / 1,027 | Traceability of *published* edges, not coverage of indexed sources |
| Active published Evidence records | 911 | Can support multiple edges; not a one-to-one coverage denominator |
| Indexed labor source rows / identifier-field candidates | 80,122 / 1 | Candidate still needs exact ID and official company-name verification |
| Judicial company-name index rows | 4,231 | Name mentions are candidates, not verified case-role links; snapshot generated 2026-09-24 |
| Procurement / directors | Unknown persisted denominator | Current graph uses bounded live lookups, not a complete indexed census |

The judicial ingestion window's 15,362 downloaded JDocs and 2,720 upstream-unavailable documents are source-health measures, not published company/judgment relationship counts. No national coverage percentage or recall can be calculated from the above. The two published companies are 大魯閣實業股份有限公司 (`04690983`) and 都一處有限公司 (`29072066`). For other firms, live source observations may be shown with explicit candidate/source-only labeling; they must not be presented as canonical links.

## Stage 2 decision gate

Before widening published graph coverage, prove an official identifier or equivalent documented role-specific source reference for each proposed company/person endpoint; verify the referenced source record and Evidence; re-run the read-only baseline and targeted regression tests. Name-only labor records and judicial mentions remain source observations. The audit script rejects non-Development database targets and performs no writes.

## Stages 3–4 verification detail

Re-run `scripts/audit_graph_integrity_dev.py` with a connection explicitly identifying `tei-development`. It rejects other project refs, uses a read-only transaction, reports aggregate counts only, and fails if published identities or edges lack the required proof. On 2026-10-17 it returned 2/2 company IDs, 2/2 registry-supported companies, 121/121 politician IDs, 1,025/1,025 politician edges with matching official IDs, and 0/1,027 invalid published edges. A separate read-only check found no duplicate published edge tuple.

The published labor example connects 大魯閣實業股份有限公司 (official uniform number `04690983`) to penalty record `府勞動字第1130101133號`. The source record retains its Ministry of Labor provenance and exact company ID; the `RELATED_TO_PENALTY` edge is `EXACT`, has active primary Evidence and a public source link, and is visible in the Entity Profile and graph. This is a verified record association, not an inference of a criminal offense. The published political contribution is backed by a reviewed official-identifier crosswalk; its source locator also preserves an earlier raw `UNRESOLVED` staging status, which is not the final crosswalk decision and should be clarified in a future provenance presentation pass.
