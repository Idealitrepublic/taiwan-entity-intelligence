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

## DATA Phase 4 — Cross-source entity resolution

Phase 4 introduces no new provider. It compares normalized observations from the
official sources above and other existing evidence-backed adapters.

- Exact Company and Politician identifiers have priority; conflicting or
  non-unique identifiers remain unresolved.
- Context signals—Company, role, overlapping dates, and independent source—must
  be traceable to immutable Evidence. Names are comparison signals, not keys.
- Candidates are private, service-role-only, bounded to 200 per ingestion call,
  and remain pending until reviewed. `MEDIUM`, `LOW`, and `UNRESOLVED` cannot be
  accepted or create formal Relationships.
- Quality checks use labeled representative pairs and report precision/recall at
  the `EXACT`/`HIGH` threshold. Rollback drops the additive ingestion function,
  constraints, indexes, and columns; it does not alter canonical Entities.

## DATA Phase 5 — Judiciary coverage

Primary provider: [Judicial Yuan JList/JDoc API specification](https://opendata.judicial.gov.tw/api/Newses/39/file).
JList exposes a seven-day change window, not a historical search. JDoc retrieves
one identified document. The public [court judgment page](https://judgment.judicial.gov.tw/FJUD/printData.aspx?id=KLDM%2C111%2C%E8%A8%B4%2C328%2C20230428%2C1)
is the source URL used to cross-check known cases.

- Ingestion requires `JUDICIAL_USER` and `JUDICIAL_PASSWORD` in the manual sync
  job. Missing credentials or invalid API responses fail the run; an empty
  seven-day window is reported distinctly from a verified zero match.
- JID is the deduplication key. Document content hashes preserve corrections as
  separate Evidence versions; a later removal suppresses the index entry.
- Each record retains the official JID, normalized judgment date, source URL,
  retrieval time, content hash, and raw JDoc provenance. File-only documents
  without extracted text remain unindexed and are counted.
- Company-name occurrences are observational search matches, not an Entity
  identity decision or legal finding. Person names remain unresolved without
  stronger identifiers.
- The checked-in verified case set covers two older judgments mentioning
  御首服務事業有限公司 and one recent judgment mentioning 中華郵政股份有限公司.
  Run `python scripts/judicial_coverage.py --verify-official` to repeat the
  known-case comparison. Sample recall is not historical population recall.

## DATA Phase 6 — Cross-source quality benchmark

Run `python scripts/data_health.py --json reports/data_health.json --markdown docs/DATA_HEALTH.md`.
This read-only benchmark uses three fixed valid company identifiers and three
official known-case judicial JIDs. It measures coverage, freshness, errors,
duplicates and provenance across nine source families. Its sample coverage is
not population recall. Published-data presence for politician, contribution and
asset rows is separate from draft adapter test coverage; private resolution
candidates are intentionally unobservable to the anonymous role. Unindexed
`source_records.dataset` population counts are not used after timed-out queries.

The current repository has normalizers for political master, contributions and
asset declarations, but no scheduled job that fetches their official files,
performs reviewed identifier mapping, calls the draft-only ingestion functions,
and publishes verified records. Adapter fixture coverage is not live coverage.
The Integrity Gazette currently offers full electronic books only for recently
published issues; older issue listings alone cannot establish historical line
coverage. The absence of a reliable official candidate-to-`lgno` crosswalk
prevents automatic Company→Politician contribution edges from name-only files.
