# T.E.I. v2 Data Source Architecture

## Source strategy

- Company basic registration: live Ministry of Economic Affairs / GCIS API where available.
- Directors and supervisors: live Ministry of Economic Affairs / GCIS API. Do not bulk-ingest the national directors/supervisors dataset into PostgreSQL.
- 165 anti-fraud: source files remain in Supabase Storage; application queries only bounded/needed records and normalizes compact evidence metadata.
- Government penalties: same Storage-first model; avoid storing complete raw payloads in PostgreSQL.
- PCC procurement: use official procurement/open-data query endpoints where available; do not scrape the entire PCC website into PostgreSQL.
- Judicial records: official Judicial Yuan open interfaces/search; credentials remain server-side when required.

## PostgreSQL rule

PostgreSQL is an index/relationship layer, not the raw-data warehouse. Store only compact normalized fields needed for search, joins, risk signals, and graph rendering. Original government files stay in private Supabase Storage.

## Directors API

Supabase Edge Function: `directors-api`

Project: `anntdcxttvffekslbrkj`

Upstream dataset: MOEA/GCIS company registration directors/supervisors API.

The function accepts `uniform_number`, `skip`, and `top`, validates an 8-digit uniform number, and proxies JSON from the official source. Responses are cached for one hour with stale-while-revalidate behavior.

## UI semantics

- Red risk markers must indicate an observed high-risk signal, not guilt.
- Orange indicates an attention signal such as an administrative penalty/fraud-related source hit.
- Yellow indicates a data match that is not itself evidence of wrongdoing.
- Every material claim should retain an official source link and source record identifier where available.
