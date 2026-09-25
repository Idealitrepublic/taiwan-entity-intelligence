# OPS Phase 1 — Development operations runbook

Scope: Development and Vercel Preview only. The Python WSGI application and
Entity/Relationship/Evidence model are unchanged. This is not authorization to
alter Production or start the politician/assistant pilot.

## Operator health and alerting

Run after each Development ingestion or with a local scheduler:

```sh
.venv/bin/python scripts/ops_health.py --check
```

This reads the saved sync status/checkpoint and `reports/data_health.json`,
without calling source APIs or Supabase. Local owner-only artifacts
`data/ops_health.json`, `data/ops_alerts.json`, and `data/ops_health.md` form the
operator dashboard. They are Git-ignored. Set `TEI_OPS_OWNER` to the accountable
operator's role/name locally; no contact address is required. Alert codes are
deduplicated, retaining first/last seen, repeat count and resolution time. No
email, push, public dashboard or new user-facing feature is added.

High alerts: Data Health age >24 h, a High source metric, invalid checkpoint,
incomplete cursor idle >2 h, pending JDoc retries, failed/partial sync outside
expected service closure, no successful publication >36 h, or >=5% 5xx in at
least 20 supplied request logs. Medium: independently verified JDoc source
gaps, >=10% 429, or p95 latency >5 s. Unknown denominators stay unknown, not
zero. A normal 06:00–00:00 Asia/Taipei judicial API closure is not a fresh
failure, but does not waive the 36-hour successful-publication target.

For optional runtime telemetry, export **sanitized** Vercel request-complete
JSON lines to a local ignored file and pass `--runtime-logs <file>`. Only event,
status and duration are parsed. Never export authorization headers, request
bodies, credentials or user notes. Vercel Runtime Logs remain the first
incident view; a paid log drain/retention integration and named on-call rota
are not silently enabled by this branch.

Each source sync now writes a random run ID, environment, source, start/end,
duration, window ID and batch index to its saved status. Source errors retain
type and dataset, not exception text or tokens. Judicial batching, retry
budget, `Retry-After`, checkpoint and permanent-source-error recheck remain as
in DATA Phase 6. A partial window cannot replace the last usable index.

## Development backup and restore

Supabase Free projects do not receive the automatic daily backups available
to paid plans; [Supabase recommends CLI logical dumps and off-site copies](https://supabase.com/docs/guides/platform/backups).
Before ingestion or migration, prepare owner-only local settings **outside
Git**: `TEI_DEV_DATABASE_URL` for `tei-development` only,
`TEI_BACKUP_AGE_RECIPIENT` (public age recipient), and
`TEI_BACKUP_AGE_IDENTITY` (absolute path to a 0600 private age identity).
Install `pg_dump`, `pg_restore` and `age` from trusted package sources. Do not
paste the database URL, password or identity into chat, logs, docs or Git.

Create a dedicated 0700 directory **outside this repository and home root**,
then run:

```sh
.venv/bin/python scripts/ops_backup.py --output-dir /absolute/private/backup-directory
```

The tool rejects a Production/mismatched database URL and broad or permissive
destinations. It streams a full logical database archive and the matching
snapshot/state/Evidence/status/index/report bundle directly to age; plaintext
is never stored on disk. Both encrypted archives are decrypted in a pipe and
validated with `pg_restore --list` / `tar -tf` before an atomic backup directory
is published. The manifest stores SHA-256 hashes and project ref, never keys.
Copy the verified encrypted directory to an access-restricted off-site target
and record its retention period. This step requires an operator-selected
destination; it is never automatic.

For an isolated restore drill, use a disposable **local** PostgreSQL database
on an owner-only Unix socket (or a separately approved Development-only
target). Verify the target is neither tei-development nor Production. Decrypt
the database archive through a pipe to `pg_restore --no-owner --no-privileges`;
never use `--clean` on tei-development or Production. A plain PostgreSQL
instance does not provide Supabase-managed extensions such as `pg_net`, so
restore the application schemas `auth`, `public`, `supabase_migrations`, and
`tei_private` after provisioning their local-only prerequisites. Restore the
sync bundle into a fresh temporary directory and compare every manifest hash.
Compare migration versions, table definitions, row counts, RLS/policies, and
indexes against the Development source; simulate public reads under `anon`.
This application-scope drill does not prove full Supabase platform recovery,
extension portability, or original ACL/ownership restoration.

### Acceptance record — 2026-09-25 UTC

- Source: verified `tei-development` project; target: disposable local
  PostgreSQL 18 over an owner-only Unix socket. Production was not connected
  or modified. The encrypted `pg_dump` and matching six-file sync bundle were
  published outside Git; age decryption, archive listing, bundle hashes, and
  encrypted-file SHA-256 checks passed. No plaintext archive was saved.
- A full platform restore attempt stopped at missing local `pg_net`. The
  application-scope restore then succeeded for `auth`, `public`,
  `supabase_migrations`, and `tei_private` without `--clean`.
- Source versus restore: 29/29 public tables and exact row counts, 268/268
  columns, 115/115 indexes, 80/80 RLS policies, and all 25 migration versions
  matched. RLS was enabled on all 29 public tables. Key restored counts:
  `entities` 140, `relationships` 1,030, `evidence_records` 1,527,
  `asset_declarations` 1. The six sync files were decrypted into a disposable
  directory and matched their recorded SHA-256 hashes.
- Local `anon` role, after local-only SELECT grants necessitated by
  `--no-privileges`, read 138 published entities, 1,026 relationships, and one
  asset declaration, while Workspace returned zero rows. This validates RLS
  behavior but does not assert Supabase's original grants were restored.
- Remaining recovery limits: Supabase-managed extensions/platform services
  and original ACL/ownership were not rehearsed on plain PostgreSQL; retain
  this as a known Medium operational risk. Off-site retention still requires
  a separate operator-selected destination and policy.

## Rate limits, WAF and incident recovery

The app retains its local fixed-window guard with `429` and `Retry-After`; this
is per-instance defense, not distributed enforcement. A read-only Vercel
Firewall overview on 2026-09-25 found one active `/api/` rule at 600/min/IP
with `log` on threshold, no draft, and automatic platform protection enabled.
This is observation, **not distributed hard-limit enforcement**. Candidate
Preview-only rules: path `/api/` with environment `preview`, GET 300/min/IP and
writes 60/min/IP, initially `log` on threshold; review 429/latency for 24 h
before enforcement. WAF configuration is project-level, so no rule is staged
or published here while Production changes are forbidden. Avoid blanket IP
blocks, bypasses and Attack Mode. Production WAF remains as-is.

On ingestion failure: stop writes, preserve snapshot/state/Evidence together,
run `scripts/sync_judicial_window.py --check-only`, inspect the sanitized
error type and service window, resume only pending JIDs in bounded batches,
then refresh Data Health and run `scripts/ops_health.py --check`. If a source
document stays unavailable with the same official error and JList metadata,
keep its recheckable provenance as Medium. Do not promote a partial index,
clear a High by assertion, or infer national coverage. On runtime failure,
correlate request ID with Vercel logs, verify Preview, and keep the previous
deployment available; Production rollback needs a separate explicit release
decision.

## Acceptance matrix

| Scenario | Expected behavior |
|---|---|
| Complete 724-batch Development checkpoint | 0 High, source gap remains Medium |
| Stale report / cursor / sync | High and nonzero `--check` exit |
| Normal closed judicial service window | No new failure alert; 36 h age still applies |
| 5xx / 429 / p95 synthetic logs | Separate severity and stable deduplicated codes |
| Repeated then recovered alert | Repeat count increments; resolution timestamp recorded |
| Production or passwordless DB URL | Backup refuses before connecting |
| Encrypted Development backup / isolated restore | Passed for application schemas and six sync files on 2026-09-25; see acceptance record and stated platform limits |
