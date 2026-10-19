# Development dual-account and verified coverage check — 2026-10-19

Scope: Development Supabase `canqjiokrtcxkwblhmml` and Preview deployment for commit `eb1c8de`. Production was not queried for private data or modified. No credentials, tokens, or private connection strings are recorded here.

## 1. Two-account private boundary

Both test accounts were confirmed in Development Auth, then used independently on the same Preview. Each created one private Workspace. The first account saved a published Company Entity, its Graph, a published labor-penalty Relationship, its primary Evidence, and one Watchlist entry. Its saved item and Watchlist owner matched its Auth user ID. The second account's UI showed only its own Workspace and no first-account saved items or Watchlist entries.

Authenticated Supabase REST checks, using each account's own token and the public anon key, returned:

| Test | Account 1 | Account 2 |
| --- | ---: | ---: |
| Own Workspaces | 1 | 1 |
| Other account's Workspaces | 0 | 0 |
| Visible saved items | 4 | 0 |
| Visible Watchlist entries | 1 | 0 |

An authenticated PATCH by account 2 against account 1's Workspace returned **0 affected rows**. Development RLS SELECT/INSERT/UPDATE/DELETE policies for Workspaces, saved items, and Watchlist are scoped to `auth.uid() = owner_user_id`; saved-item writes additionally require `created_by_user_id = auth.uid()`.

**Result:** Workspace/list and direct cross-account read/update boundary **PASS**. The private report **opened as a PDF blob** in a separate browser tab, but the browser's security policy barred automated inspection of that blob. Its visual layout, downloaded file bytes, and cross-account report endpoint therefore remain **PARTIAL**, not PASS. The report's local presentation/PDF tests passed; these are not a substitute for the private-browser checks.

## 2. Evidence-backed data coverage

Development currently has 462 published Company entities, one published Penalty entity and `RELATED_TO_PENALTY` relationship, one published Contract entity and `CONTRACT_WITH` relationship, and **no published Judgment entity or relationship**. There are 80,122 indexed labor source records, but only **one** has an explicit 8-digit company uniform number in the indexed field. The labor source's raw columns are agency, employer/person name, dates, law, disposition number, violation, amount, and note—not a general company-ID field. Eight-digit substrings in disposition numbers or notes are not company IDs and must not be used for automatic resolution.

The verified sample uses company ID `04690983` (大魯閣實業股份有限公司). The Preview showed its Company Entity, penalty relationship, exact confidence, disposition `府勞動字第1130101133號`, amount TWD 50,000, observation and retrieval timestamps, source record ID, and the original government dataset link. Its published procurement relationship has a separately verified official PCC source. One draft OpenFun procurement relationship has the **same source record as the published PCC-backed edge**; publishing it again would duplicate the same award.

The 15,362 JDoc items in the local judicial sync benchmark are **not** evidence of 15,362 published Development Judgment entities. They remain source/index coverage, with upstream-unavailable items and unresolved company identity; they must not be joined to Company by name alone.

**Result:** Existing exact-ID labor and PCC samples **PASS** provenance checks. Broad labor/judiciary Company linkage remains **PENDING**, not data loss: the available source records lack reliable identifiers for most rows. Safe next step is an official, dated identifier crosswalk or human-reviewed case-party verification that preserves source evidence and leaves unresolved matches unpublished.

## Verification

- Browser: authenticated Preview login, Workspace creation and list isolation, Entity/Graph/Relationship/Evidence saves, Watchlist save, report preview opening, published Company graph and edge provenance.
- Database: read-only Development counts, raw-source field check, owner/RLS policy inspection, cross-account REST SELECT and no-op UPDATE test.
- Targeted tests: `48 passed` across Workspace, report presentation/PDF, labor, procurement, and judiciary coverage tests. Full local regression: 289 Python tests, 173 schema/DB integration checks, 21 browser-function cases plus the remaining graph/UI cases; lint, web syntax, and Python bundle check passed. These local checks do not replace live private-PDF visual inspection.
- Preview: https://taiwan-entity-intelligence-bz1yrfp0h-coldlight871029-9944.vercel.app/ (`eb1c8de`, READY).

Do not claim nationwide coverage, completed private PDF visual QA, or complete judicial identity resolution from these checks. No Production changes were made.
