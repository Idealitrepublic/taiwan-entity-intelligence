# T.E.I. Public Evidence Sync

The repository now owns the ingestion workflow. No local terminal is required for scheduled execution.

## What is synchronized

### Judicial
- Judicial Yuan judgment change feed (`JList`) and judgment documents (`JDoc`)
- Uses the official 7-day change list, keyed by `jid`
- Re-fetching the same `jid` replaces the previous evidence record
- Removed judgments are marked `removed`

### 165 anti-fraud
- `176455` — 165 blocked scam domains
- `38262` — 165 scam-rumor clarification
- `160055` — 165 fake-investment / gambling sites
- Records are content-addressed so repeated rows do not create duplicates

### Government penalties
- The sync discovers public data.gov.tw datasets whose titles contain penalty keywords such as `裁罰`, `裁處`, `罰鍰`, `行政處分`, and `處分名單`.
- Statistical-only datasets are excluded when their titles indicate aggregate counts/amounts.
- This is an automated discovery layer, not a legal claim that every government penalty dataset in Taiwan has been captured. New datasets can be discovered automatically as they appear in the catalog.

## GitHub Actions

Workflow: `.github/workflows/sync-public-evidence.yml`

- Scheduled: 01:30 Taiwan time (UTC 17:30), inside the Judicial Yuan API service window.
- Manual: GitHub → Actions → **Sync Taiwan public evidence** → **Run workflow**.
- Evidence is uploaded as a 30-day artifact.
- A compact `data/public_sync_status.json` is committed so the product can display the last sync status.

## Required GitHub Secrets

Add these once under **Settings → Secrets and variables → Actions → New repository secret**:

- `JUDICIAL_USER`
- `JUDICIAL_PASSWORD`

These are the credentials issued by the Judicial Yuan Open Data Platform. Do not commit them to the repository.

## Evidence contract

Every source is normalized to the same Evidence record:

`source → source_record_id → entity → fact → relationship → target → source date → retrieval time → provenance URL → confidence → status → raw payload`

A public-record match is evidence, not an accusation. T.E.I. should never convert the presence of a person/company in a court record, penalty dataset, or fraud dataset into a conclusion of wrongdoing without explicit, source-backed context.
