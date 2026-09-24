# DATA Phase 6 — offline acceptance preparation

Recorded 2026-09-24. This is preparation, not Phase 6 acceptance. No Judicial
Yuan request, Development DB query, Production write, full build, push, or
deployment was performed for this record. The local browser ran with an
unreachable loopback Supabase URL and no authenticated workspace configuration.

## One-command post-sync gate

From the repository root, after all 724 fixed-snapshot batches and retries
finish, explicitly set the Development project's public URL and anon/publishable
key in the local shell. Do not use a service-role key. Then run:

```sh
.venv/bin/python scripts/accept_data_phase6.py --refresh-health
```

The command refuses to refresh Data Health while batches or retries remain.
After completion it refreshes the live, sample-scoped report and checks: every
batch attempted and completed; JList JIDs accounted for by ingested Evidence or
independently verified upstream-unavailable records; no pending ingestion;
Evidence ID uniqueness, source URL/name, retrieval time, content hash, raw
document and fact type; report freshness after the last attempt; all nine
source metrics present; no High severity; and agreement between report and
checkpoint counts. Its JSON output includes each source's coverage, freshness,
duplicate and provenance metric, plus `review_required` for unknown or
incomplete values. Exit 0 means this gate passed, **not national historical
judiciary coverage**. The existing DB checks and build remain separate later
gates and must only run after this one passes.

Post-sync result (2026-09-25 Asia/Taipei): 724/724 batches attempted and
completed; 15,362 JIDs ingested, 0 pending, 2,720 independently rechecked
upstream-unavailable. The completed-window Evidence has no duplicate IDs or
missing required provenance fields. The refreshed Development Data Health gate
reports High=0. Upstream-unavailable is a substantial Medium source-coverage
gap (15.04% of this fixed JList window), not successful JDoc retrieval or
national historical coverage. Its JIDs and error fingerprints remain recheckable.

## Cross-source representative sample and limits

| Source/grain | Saved evidence inspected | Identity/date/provenance assessment | Offline disposition |
|---|---|---|---|
| Politician, legislator-term | Development read-only audit dated 2026-09-23: 121 published terms and 121/121 fixed term-11 `lgno` overlap; no row-level local export | Official `lgno` is the intended key; term and office dates require row-level recheck | Count-level only; row authenticity and freshness not independently verified offline |
| Political contribution, filing row | Development audit: 1 published relationship; documented Control Yuan row `168061:taipei:incomes:886` | Donor uniform `29072066` and reviewed LY `lgno`/district crosswalk are documented, but source ZIP and published Evidence row are not cached locally | Provenance chain documented, not independently replayed offline; national denominator unknown |
| Asset declaration, Gazette line | Development audit: 1 published row; documented Gazette 319 vehicle line | Issue/page/date and reviewed `lgno` crosswalk are documented; no cached PDF or published row | Row-level original cannot be revalidated offline; national denominator unknown |
| Company registration and directors, uniform | Fixed benchmark IDs `23060248`, `22099131`, `96979933` each reported present for both on 2026-09-24 | Uniform number is the exact Company key; benchmark stores response presence, not the full source payload | 3/3 fixed-sample presence only, not registry coverage or row-level revalidation |
| Government procurement, award notice | Fixed benchmark 3/3 company lookups on 2026-09-24; no cached notices | OpenFun mirror uses uniform, but provenance rate is 0 and row URL/date cannot be checked offline | Medium: inspect official PCC notices and row provenance before trust |
| Labor penalty, source record | Fixed benchmark returned 0 indexed rows with unknown denominator | Legacy name matching is not a verified uniform-number Entity match; no local source row | Unknown: no representative real record could be independently checked offline |
| Judiciary, JDoc Evidence | 2,022 saved JIDs in `data/public_evidence.jsonl` | JID, judgment date, source URL, retrieval time, content hash, raw JDoc and Evidence IDs checked locally | Row-level saved provenance complete for processed JIDs; 15,882 JIDs remain unattempted |

These are **different grains and observation times**. A saved count or adapter
fixture cannot establish current official-source validity. In particular the
political and procurement/penalty source links need live or cached original
documents before claiming row-level cross-source verification.

## Resolution manual challenge set

The offline challenge cases cover: same person name only → LOW and no formal
Relationship; same Company name with conflicting uniforms → UNRESOLVED;
same politician name with distinct official `lgno` → UNRESOLVED; Company
rename with the same uniform → EXACT; shared official identifier appearing
on multiple candidates → UNRESOLVED; verified Company/role/overlapping time
and independent source → HIGH; partial context → MEDIUM; entity-type conflict
→ UNRESOLVED. All results are pending candidates, not automatic Entity merges.
The `EXACT/HIGH` publishability threshold is a *review eligibility* boundary,
not proof that two same-name people are identical. The five-case precision/
recall fixture is not live-resolution precision/recall. No private Development
candidate rows were exported for an actual human adjudication in this offline
pass.

## Local UI/API walk-through

Story: Global Search → Entity profile → Graph/Path → Evidence → Workspace →
Report. In isolated offline mode, the homepage rendered at localhost:3000,
including Search, path-depth selector, graph controls, evidence tabs, Workspace,
and Report-related UI. Search for `台積電` returned the explicit
`Search store unavailable` state because the Supabase endpoint was deliberately
set to unreachable loopback. The Workspace dialog reported `Auth unavailable`.
Accordingly the flow could not proceed to a real Entity, Graph, Path, Evidence,
Workspace save, or Report download without violating the offline boundary.
Targeted route/domain tests cover those APIs separately, but are not a live
browser journey. UX follow-up (Low): the Workspace login fields and Sign in
button remain visible under `Auth unavailable`, which may invite a futile
attempt; no UI refactor was made in this pass.

## Checkpoint, resume, and rollback

- Snapshot: ignored local `data/judicial_jlist_snapshot.json`, 18,082 unique
  JIDs and JList metadata; SHA-256 window ID must equal the checkpoint ID.
- Checkpoint: ignored `data/public_sync_state.json`; 25 JIDs/batch, 724 batches.
  `data/public_evidence.jsonl` contains immutable content-addressed Evidence.
  `data/public_sync_status.json` is a generated status artifact. Keep the
  snapshot, state, Evidence and status together when making a local backup.
- Read-only preflight: `.venv/bin/python scripts/sync_judicial_window.py --check-only`.
  This verifies hash, batch bounds/stats and completed-batch Evidence without
  credentials or API access. Do not run a fresh JList against this checkpoint.
- Resume only at 00:00–06:00 Asia/Taipei with safely loaded local judicial
  credentials: `.venv/bin/python scripts/sync_judicial_window.py`. Attempted
  batches are skipped; their pending JIDs are retried in bounded groups. A
  closed service window preserves progress. Verify `--check-only` again after
  interruption.
- Rollback is local-only and requires a pre-run copy of the four files above.
  Stop the runner first; restore the entire matching set, never just one file.
  Do not run `supabase db reset --linked`, truncate Evidence, rebase the JList
  window, or touch Production. Published Evidence corrections use supersession,
  not deletion. No rollback was performed for this offline check.

## Data Health interpretation

`docs/DATA_HEALTH.md` is generated from a fixed public sample plus separate
read-only Development audit. `jlist_processing_coverage` is only the fraction
of one frozen seven-day JList snapshot attempted; it is not recall of all
historical judgments. `ingestion_failure_rate` uses attempted, obtainable
documents; verified upstream-unavailable is counted separately and remains
recheckable. Freshness is report/index timestamp age, not guaranteed source
publication latency. Unknown denominators remain `unknown`, never zero.
`High=0` is necessary but not sufficient for Production: row-level provenance
gaps and unknown national denominators remain documented Medium/Unknown risks.
