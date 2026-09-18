# T.E.I. agent guide

## Scope and safety

- Preserve current behavior unless the task explicitly requests a product change.
- Never deploy with `vercel --prod`, promote a deployment, edit Production environment variables, or run a Production database migration without explicit approval.
- Treat the checked-in Supabase project as shared. Routine local and Preview work must use public read access; never expose or commit `SUPABASE_SERVICE_ROLE_KEY`.
- Keep `.env.local`, `.vercel/`, local datasets, databases, and credentials untracked.
- Preserve Git history. Work on a named branch and keep unrelated user changes intact.

## Canonical architecture

- Runtime: Python 3.12+ WSGI, entry point `app:app` in `app.py`.
- UI: dependency-free HTML/CSS/JavaScript in `web/`; this is not a Next.js application.
- Data: Supabase Postgres/Data API plus public government sources.
- Domain model: `Entity -> Relationship -> Evidence`; relationships require primary evidence before publication.
- Deployment: Vercel project `taiwan-entity-intelligence`, Git-integrated from `main`.

## Required workflow

1. Local: create/switch to a feature branch; configure `.env.local`; do not use Production-only credentials.
2. Test: run `npm run lint`, `npm run build`, `npm test`, then focused local API/browser checks.
3. Git: review `git diff`, commit the bounded change, and push the non-production branch.
4. Vercel Preview: verify the branch Preview and confirm it uses Preview-scoped configuration.
5. Acceptance: record evidence and obtain user approval.
6. Production: merge the accepted commit to `main`; do not bypass the gate with a direct Production deployment.

## Local commands

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
npm ci
cp .env.example .env.local
npm run lint
npm run build
npm test
npm run dev
```

The local server is `http://localhost:3000`. When the dev server starts, verify the rendered UI and the relevant API boundary rather than relying only on process startup.

## Change rules

- Make schema changes as new Supabase migration files; never rewrite applied migrations.
- Explicitly grant Data API access and enable RLS for every exposed table. Public policies must filter publication state as defense in depth.
- Keep service-role ingestion paths separate from public read paths.
- Prefer bounded queries, keyset cursors, batched graph reads, deterministic IDs, immutable source provenance, and explicit source timestamps.
- Update `docs/ARCHITECTURE.md`, `DATA_MODEL.md`, and `ROADMAP.md` when architectural decisions change.
