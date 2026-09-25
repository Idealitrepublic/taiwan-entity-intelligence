# OPS Phase 1 — implementation contract

DATA Phase 6 reached High=0 on `0bc5fd2`. This design is now implemented on a
separate OPS branch without changing Entity/Relationship schema or Production.
The operator commands, thresholds, failure simulations, and remaining external
backup/WAF prerequisites are in [the runbook](OPS_PHASE_1_RUNBOOK.md).

| Concern | Proposed signal | Proposed action/guardrail |
|---|---|---|
| Ingestion monitoring | Per-source run ID, environment, snapshot/window ID, started/ended time, batch cursor, attempted/ingested/pending/upstream-unavailable, sanitized error type, duration | Show Development health first; alert on stalled cursor, rising pending rate or source-specific timeout, not on an expected overnight source closure |
| Data health | Coverage denominator/scope, last successful publication, Evidence completeness, duplicate IDs, age of latest report and source record | Keep unknown separate from zero; block release on High or stale report; inspect Medium/Unknown manually |
| Backup | Encrypted, access-restricted Development DB schema+data backup and matching local snapshot/state/Evidence manifest before ingestion or migration | Verify restore in an isolated target and retention before any Production adoption; never place credentials or raw personal data in Git/logs |
| Alerting | Severity, owner, run link, first/last seen, repeat count and recovery confirmation | Dashboard first; deduplicate repeated source errors; no email/external push without later approval |
| Rate limits | Per-source concurrency, bounded batch size, timeout/retry budget, `Retry-After`, service hours | Stop and checkpoint on 429/transport errors; do not retry permanent source-document errors indefinitely |
| Operational recovery | Resume cursor, idempotent source-record/evidence keys, failed-JID queue, verified upstream-unavailable recheck | Test restore/resume on Development; never auto-promote a partial index or infer national recall |

Acceptance requires a Development status run, stale/failure/restore alert
simulations, a verified encrypted Development database+sync backup, isolated
restore rehearsal, full DB checks/build, and Preview runtime verification.
No Production WAF publication, secrets, database write, or deployment is
authorized by this phase.
