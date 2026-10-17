# Traceable graph: stages and Development baseline

Scope: existing company, person, procurement, labor-penalty, and judicial sources only. No Production changes or new source ingestion. A source mention is not a verified Entity relationship.

## Stages

1. **Scope and provenance display — completed.** Show query scope, source locator, retrieval time, match rule, and candidate status on graph observations. Preserve interactive source links and Evidence.
2. **Coverage baseline and existing-source entry into graph — in progress.** Reconcile indexed, live-only, candidate, and published counts. Identify safely materializable records; do not publish name-only matches. Re-run `scripts/audit_graph_coverage_dev.py` against the explicit Development connection before claiming coverage.
3. **Company/person identity verification — pending.** Confirm official company IDs, source-scoped people, role, company, and time. Promote only verified identities; retain unresolved cases as candidates.
4. **Evidence review per edge — pending.** Verify every published line's endpoint roles, source URL/locator, timestamp, and primary Evidence. Do not infer wrongdoing from a mention or penalty record.
5. **Graph presentation and interaction acceptance — pending.** Check clustering, edge labels, candidate distinction, expanded company nodes, 1–3-hop Path Finder, zoom/drag/fit, and responsive layout across representative densities.
6. **Development/Preview integration acceptance — pending.** Test Search → Entity → Graph → Path Finder → Evidence against real Development data, including empty states and cross-source consistency, before any release decision.

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
