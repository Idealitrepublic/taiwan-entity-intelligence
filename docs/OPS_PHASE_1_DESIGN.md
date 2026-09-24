# OPS Phase 1 — design only (not started)

This document is a proposal. It creates no schema, job, alert, environment
variable, deployment, backup or Production change. DATA Phase 6 must first
reach High=0 and be separately accepted.

| Concern | Proposed signal | Proposed action/guardrail |
|---|---|---|
| Ingestion monitoring | Per-source run ID, environment, snapshot/window ID, started/ended time, batch cursor, attempted/ingested/pending/upstream-unavailable, sanitized error type, duration | Show Development health first; alert on stalled cursor, rising pending rate or source-specific timeout, not on an expected overnight source closure |
| Data health | Coverage denominator/scope, last successful publication, Evidence completeness, duplicate IDs, age of latest report and source record | Keep unknown separate from zero; block release on High or stale report; inspect Medium/Unknown manually |
| Backup | Encrypted, access-restricted Development DB schema+data backup and matching local snapshot/state/Evidence manifest before ingestion or migration | Verify restore in an isolated target and retention before any Production adoption; never place credentials or raw personal data in Git/logs |
| Alerting | Severity, owner, run link, first/last seen, repeat count and recovery confirmation | Dashboard first; deduplicate repeated source errors; no email/external push without later approval |
| Rate limits | Per-source concurrency, bounded batch size, timeout/retry budget, `Retry-After`, service hours | Stop and checkpoint on 429/transport errors; do not retry permanent source-document errors indefinitely |
| Operational recovery | Resume cursor, idempotent source-record/evidence keys, failed-JID queue, verified upstream-unavailable recheck | Test restore/resume on Development; never auto-promote a partial index or infer national recall |

Suggested acceptance later: one Development dry run across a full source
window, reproducible health report, restore rehearsal, alert simulation and
documented on-call owner. None of these operations is authorized by this design.
