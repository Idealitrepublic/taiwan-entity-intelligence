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
