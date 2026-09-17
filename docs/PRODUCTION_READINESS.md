# Production Readiness Audit

Audit date: 2026-09-17  
Baseline: `6082747`  
Scope: security, RLS, environment boundaries, provenance, entity resolution,
errors, performance, UX, metadata, rate limiting, observability, recovery,
migrations, and release flow.

Production was not changed. Findings below are based on repository inspection,
the migration integration suite, and read-only Vercel CLI inspection.

## Findings

| ID | Severity | Finding | Resolution / release condition |
|---|---|---|---|
| C-01 | Critical | Public company readers preferred `SUPABASE_SERVICE_ROLE_KEY`, bypassing RLS if the variable existed. | Fixed: every public path now selects only anon/publishable credentials. Service-role remains restricted to explicit backfill/ingest tooling. |
| C-02 | Critical | Pushes/schedules on `main` could invoke shared-data seeding or commit generated source state, indirectly triggering Production deployment. | Fixed: both workflows are manual-only, require typed confirmation, have read-only repository permission, and never push. |
| H-01 | High | Authenticated Workspace/Watchlist used the checked-in shared Supabase fallback, so environment ownership was implicit. | Fixed fail-closed: authenticated features require paired `TEI_PRIVATE_SUPABASE_URL` and `TEI_PRIVATE_SUPABASE_ANON_KEY`; Preview must point to an isolated project. |
| H-02 | High | Canonical request failures had no structured incident record; legacy handlers could return exception details. | Fixed: redacted JSON request logs include request ID, route, status, duration and error type; responses expose no exception text. |
| H-03 | High | Application endpoints had no burst guard. | Fixed in app with bounded per-instance 60-second limits and `429`/`Retry-After`. Before Production, add a platform WAF rule for globally consistent enforcement. |
| H-04 | High | Current Vercel project has no environment variables, so authenticated features cannot be safely enabled and environment ownership is unverifiable. | Safely contained by H-01. **Open release gate:** create isolated Preview/Production Supabase projects and add each pair only to its matching Vercel environment. |
| H-05 | High | Manual promotion/deployment protection and required acceptance checks cannot be proven from repository state. | **Open release gate:** configure Vercel Production deployment protection/manual promotion after Preview acceptance. Not changed because this audit forbids Production mutation. |
| M-01 | Medium | Vercel Firewall reports automatic DDoS protection but no custom active/draft WAF rule. | Add route-aware platform limits after measuring Preview traffic; app burst guard is defense in depth, not distributed enforcement. |
| M-02 | Medium | Backup/PITR retention and a restore drill cannot be verified without Supabase management access. | Confirm plan retention, PITR status, and perform a documented restore rehearsal before launch. Public-source data is reproducible; owner workspaces are not. |
| M-03 | Medium | Runtime logs exist after H-02, but no drain, alert threshold, or incident owner is evidenced. | Configure alerts for 5xx/429/latency and a retention destination before launch. Never log tokens or request bodies. |
| M-04 | Medium | The document has a title and responsive/accessibility affordances, but lacks description, canonical, Open Graph, robots and structured metadata. | Add approved public-domain metadata after the Production hostname is final. |
| M-05 | Medium | The UI is a large inline HTML/CSS/JS bundle; this increases regression and caching risk. | Split only after launch criteria are met; preserve current behavior with browser tests. |
| M-06 | Medium | Live database migration parity was not proven by a migration ledger query; the 140-check suite validates migrations in PGlite. | Apply additive migrations to isolated Preview, compare ledger/checksum, run smoke tests, then schedule separately for Production with backup and rollback steps. |
| L-01 | Low | Multiple legacy Vercel handlers overlap the canonical WSGI entrypoint. | Remove in a later maintenance phase after route telemetry proves they are unused. |
| L-02 | Low | Legacy source adapters contain dense formatting and broad best-effort exception handling. | Refactor later with contract tests; no behavior change in this audit. |

## Controls confirmed

- RLS is enabled for the Phase 1–11 public and owner-scoped tables. Owner policies
  bind Workspace and Watchlist rows to `auth.uid()`; public reads require published,
  active entities/evidence. Grants and RPC execution are explicitly tested.
- Relationship traversal is bounded to three hops and server-side row/entity limits;
  search, timelines, reports, evidence, and workspaces also have explicit caps.
- Evidence keeps source name, source record ID, source URL/locator, observation and
  retrieval timestamps, and content hash. Publication/withdrawal constraints hide
  draft or retracted records and their dependent relationships.
- Company resolution uses exact uniform number for political contributions and asset
  links. Name-only matches are not forcibly merged; aliases and normalized search
  terms remain retrieval aids rather than identity proof.
- Public failures return generic messages; private routes forward only the user's JWT
  and rely on database RLS. Request bodies are size-bounded.
- The current deployment is a Python WSGI application, not Next.js. `npm run build`
  validates the deployable Python bundle and browser JavaScript.

## Production release gates

1. Create separate Preview and Production Supabase projects; never share authenticated
   write targets. Configure the two `TEI_PRIVATE_*` variables per Vercel environment.
2. Apply and verify migrations in Preview, run targeted tests, DB checks, full build,
   Preview smoke/runtime checks, and record acceptance.
3. Confirm backup retention/PITR and a restore rehearsal immediately before the
   Production migration window.
4. Configure Vercel WAF rate rules, 5xx/latency alerts, log retention, and deployment
   protection. Require manual Production promotion after acceptance.
5. Promote the accepted immutable deployment only on explicit user authorization;
   run read-only health checks and keep the previous deployment available for rollback.

## Authoritative references

- Supabase Data API security: https://supabase.com/docs/guides/database/hardening-data-api
- Supabase Production checklist: https://supabase.com/docs/guides/deployment/going-into-prod
- Supabase backups: https://supabase.com/docs/guides/platform/backups
- Vercel environment variables: https://vercel.com/docs/environment-variables
- Vercel Firewall: https://vercel.com/docs/vercel-firewall
- Vercel Observability: https://vercel.com/docs/observability
- Vercel deployments: https://vercel.com/docs/deployments
