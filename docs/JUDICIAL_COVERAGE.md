# DATA Phase 5 judiciary coverage and data quality

Benchmark date: 2026-09-23. Grain: one official judgment JID; a company match
means its full name occurs in the indexed document, not that it is a party or
liable. Reproduce with `python scripts/judicial_coverage.py --verify-official`.

| Check | Before | After | Meaning |
|---|---:|---:|---|
| Indexed records / unique JIDs | 699 / 699 | 701 / 701 | Two historical official cases restored |
| Known verified cases found | 1/3 | 3/3 | Sample recall, not nationwide recall |
| Verified official URLs and names | 3/3 | 3/3 | Court pages contain expected names |
| Historical pre-2025 entries | 3 | 5 | Historical coverage remains sparse |
| Duplicate JIDs | 0 | 0 | One index row per judgment |

The three checked cases are KLDM 111訴328 (2023), KLDV 112訴364 (2023),
and TPDM 115審簡1644 (2026). The first two mention 御首服務事業有限公司
and 吳虹葳; the third mentions 中華郵政股份有限公司. The two historical cases
previously returned zero in the canonical company route despite official pages.
The 3/3 result includes two manually verified seed records; it is a regression
benchmark, not an unbiased recall estimate.
Official case identifiers, URLs, and retrieval provenance are in
`data/judicial_verified_cases.json`.

High severity residual coverage gap: the checked-in JList index was last built
2026-09-15 and contains only a small recent window. The official JList is a
seven-day change feed; without a separate historical archive and an active
credentialed refresh, nationwide or historical recall cannot be claimed. The
read API now reports unmatched results as `partial`, avoiding a false assertion
that no judgment exists. Full historical backfill requires a source dataset and
reviewed ingestion plan, not a fabricated result.
The manual sync currently uploads a CI artifact; it does not automatically
publish that artifact into Vercel. A reviewed index refresh and Preview release
is still needed to keep the served index current.

The official text can mention a company or person in many roles. Exact name
occurrence is only a search signal. No same-name person merge, formal
Relationship, or legal inference is made. JDoc file-only records without text
are counted as unindexable until an extraction source is available. There is
no Phase 5 DB schema change, so existing RLS/relationship checks remain the
relevant database gate.
