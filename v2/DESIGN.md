# T.E.I. v2 Architecture

## Runtime source strategy
- Company basic registration: live MOEA/GCIS API.
- Directors/supervisors: live MOEA/GCIS API via Supabase Edge Function `directors-api`.
- Large open-data datasets (165 anti-fraud, administrative penalties): keep originals in Supabase Storage; query/match selectively at runtime or via bounded indexes.
- PCC procurement: use official query/API integration; do not ingest the full PCC download archive into PostgreSQL.
- Judicial records: official Judicial Yuan public/API/search integration; never infer guilt from name matches.

## Database principle
PostgreSQL is a query/index layer, not an archive. Avoid storing full raw payloads per evidence row. Raw source files stay in Storage.

## Evidence principle
Every result is source-backed and displays source, record identifier, retrieval time, and original URL where available. Risk colors are investigation signals, not guilt labels.

## UI requirements
- Red: explicit criminal/judicial signals.
- Orange: administrative penalty / fraud-warning signals.
- Yellow: public-record match requiring review.
- Plain-language explanation alongside original government/court wording.
- Make clear that names can collide and that a source hit is not a legal conclusion.
