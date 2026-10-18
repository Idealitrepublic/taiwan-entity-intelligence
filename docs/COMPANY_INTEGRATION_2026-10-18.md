# Development company integration — 2026-10-18

Scope: existing `tei-development` source data, **not** every registered company
in Taiwan. Production was not changed. A searchable live registry result is not
automatically a persisted Company Entity or a proved Relationship.

## Source-backed result

- The existing Control Yuan draft Evidence contains 487 distinct eight-digit
  donor identifiers. Each was checked against the official [MOEA/GCI company
  registry API](https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6)
  with an exact-ID filter. 457 resolved to a unique company registration and
  were integrated or confirmed idempotently. One was already among the six
  previously published companies; the resulting Development total is **462**.
- The other 30 IDs returned HTTP 200 with an empty body from the official
  company-registration endpoint. Most source labels denote shops, enterprises,
  associations or other non-company forms; at least one is an establishment
  whose number differs from its parent company. These remain source candidates,
  **not** canonical Company Entities. Do not substitute the parent's ID.
- Of the verified company IDs, three had conflicting donor labels, 15 had
  donor labels different from the current official company name, five had an
  official non-active status, and one had a non-company-form donor label.
  These differences do **not** create donation links: the published identity
  uses only the official ID, current name, status, source URL, retrieval time,
  and registry Evidence. Historical donor-name resolution remains a separate
  review task.
- The existing 80,122 labor source rows contain 51,223 distinct source names
  but only one row with an exact eight-digit ID. The 4,231 judicial company-name
  index rows are likewise name mentions. They remain source observations;
  no name-only canonical merge or penalty/judgment Relationship was added.

## Verification and limits

- Development integrity audit: 462/462 published Companies have exact company
  identifiers and active published MOEA registry Evidence; 1,028/1,028 existing
  published edges retain traceable primary Evidence; zero invalid or duplicate
  edges. The operation did not create new political contribution Relationships.
- Anonymous search resolves a newly integrated exact identifier. The
  database is approximately 95 MB after this batch. These are snapshot counts,
  not national company coverage or proof that every Company has procurement,
  labor, judicial, director, or political records.
- `scripts/materialize_registry_companies_dev.py` reads only the existing draft
  donor candidate IDs, verifies the Development DB target, queries the official
  registry by exact ID with bounded retries, and publishes batches of at most
  25 through the existing transactional ingestion function. Its ignored local
  checkpoint is `data/local/registry_company_integration.json`; reruns skip
  successfully integrated IDs and recheck unresolved candidates. The default
  run is read-only; `--apply` is Development-only. No service-role key is used
  by this script.
- Rollback requires a reviewed, targeted correction of the affected official
  identity versions after a Development backup. Never reset a linked DB or
  remove source Evidence to hide a mismatch. The checkpoint is operational
  state, not the sole record of what was published.

Remaining coverage work: acquire verifiable identifiers or official
role-specific source references for the labor/judicial name-only observations;
audit procurement/director persisted denominators. Until then, the platform
must label those facts as source-only/candidates rather than claim all companies
or all relationships have been integrated.
