# T.E.I. v2 data sources

## DATA Phase 1 — Political Master Data

Primary provider: Legislative Yuan Open Data Service (`data.ly.gov.tw`).

| Dataset | Official ID | Grain | Fields used | Refresh |
|---|---:|---|---|---|
| Historical legislators | 16 | one legislator-term row | term, name, party, constituency, committee text, onboard/leave dates | daily 03:05 |
| Committee membership | 14 | one legislator/term/session/committee row | `lgno`, term, session, committee, co-chair flag | daily 02:45 |
| Current legislators | 9 | one current legislator row | current-state completeness cross-check only | daily 04:10 |

Official metadata and API documentation:

- Dataset 16: <https://data.ly.gov.tw/getds.action?id=16>
- Dataset 14: <https://data.ly.gov.tw/getds.action?id=14>
- Dataset 9: <https://data.ly.gov.tw/getds.action?id=9>
- API guide: <https://data.ly.gov.tw/gniKK/developer.action>
- Official legislator-number list: <https://data.ly.gov.tw/legislator.pdf>
- Legislative Yuan member directory: <https://www.ly.gov.tw/Pages/List.aspx?nodeid=109>

### Identity and provenance rules

- `lgno` is the only Phase 1 cross-row politician identifier. Exact `lgno` creates
  `tw:legislative_yuan:legislator_number`; it is never inferred from a name.
- Dataset 16 has no documented `lgno`. It may be joined to dataset 14 only within
  the same term and exact normalized name, and only when that pair maps to one
  unique `lgno`. Ambiguous or absent mappings remain `SOURCE_SCOPED`.
- Names, English names, party labels, photos, addresses, telephone numbers, and
  biographies are not identity keys. Contact details are not ingested.
- Every accepted member and committee observation creates immutable Evidence with
  dataset ID, source record ID, retrieval time, and official source URL.
- All bundle output is `draft`; publication remains a separate reviewed action.

### Quality gates

- Required member fields: term, name, constituency, onboard date.
- Required committee fields: term, session, `lgno`, name, committee.
- Reject malformed dates, out-of-range term/session values, identifier/name
  conflicts, and committee rows that cannot resolve to an exact `lgno` Entity.
- Report member acceptance, exact-identifier coverage, committee join coverage,
  ambiguous identifiers, and unmatched committee rows on every build.
- Split refreshes into dependency-complete, idempotent RPC batches within the
  200-row core and 1 MB transaction limits.
- A zero-row source response is not accepted as a successful full refresh without
  an explicit source-health decision.

## DATA Phase 2 — Political Contributions

Primary provider: Control Yuan Political Contribution Public Access Platform.

- Official platform: <https://ardata.cy.gov.tw/>
- 11th Legislative Yuan election dataset: <https://data.gov.tw/dataset/168061>
- 10th Legislative Yuan election dataset: <https://data.gov.tw/dataset/129495>

The official files contain filing/row identity, candidate or party, election,
transaction date, income/expense category, donor/payee, ID or uniform number,
amount, donation method, and correction metadata. The adapter allowlists only
the contribution fields needed by T.E.I.; addresses, telephone numbers, and
personal national IDs are never retained in Evidence.

### Identity, provenance, and quality rules

- A Company match requires an exact normalized eight-digit `tw:uniform_number`.
- A Politician match requires one exact official identifier supplied by the
  source-to-master crosswalk. Candidate names are audit text, never match keys.
- Evidence retains filing/row ID, candidate and donor source labels, election
  year, source URL, retrieval time, and both exact matching methods.
- Every build reports accepted/skipped rows, exact-match coverage, duplicate
  source records, conflicting duplicates, and bounded batch count. Zero rows or
  any conflicting source-record identity requires review before publication.
- Output is draft-only and split into dependency-complete batches of at most 200
  Relationships, 400 Evidence records, and 1 MB. A whole batch can be removed
  while draft; published corrections use superseding Evidence, never mutation.

## DATA Phase 3 — Asset Declarations

Primary provider: Control Yuan Sunshine Acts portal and Integrity Gazette.

- Asset declaration portal: <https://sunshine.cy.gov.tw/>
- Integrity Gazette index: <https://sunshine.cy.gov.tw/News.aspx?PageSize=200&n=17&page=1&sms=8861>
- Public Officials Property Declaration Act: <https://www.cy.gov.tw/law/LawContent.aspx?id=FL010649>
- Official form instructions: <https://multimedia.cy.gov.tw/law/LawContent.aspx?id=FL010661>

The portal publishes declarations as gazette/document records rather than one
stable bulk API. Extraction must therefore retain the issue, filing ID, line
number, source URL, declaration date, retrieval time, and correction version.
Only the thirteen T.E.I. asset categories are allowlisted. Personal identity,
address, contact, spouse, and minor-child fields are excluded from ingestion.

### Identity, versioning, and quality rules

- Politicians resolve only through an exact official identifier crosswalk.
- Companies resolve only through an exact normalized eight-digit uniform number;
  a company name remains source text and never forces a merge.
- A deterministic declaration key identifies the same filing line across
  corrections. Versions are append-only; a later version references the older,
  withdrawn version, and only one version may be published for a key.
- Every run reports row acceptance, all-category coverage, exact Company match
  rate, unresolved Companies, duplicates, and conflicting source records.
- Draft-only batches contain at most 200 declaration lines/Relationships, 400
  Evidence records, and 1 MB. Zero-row loads and source-record conflicts require
  review. Rollback removes the draft batch; published corrections are superseded.
