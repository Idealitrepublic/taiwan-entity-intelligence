# VALIDATION Phase 1 — Real User Pilot plan

Status: ready for participant scheduling; **no participant sessions have run**.
Scope: four people, eight core task attempts, on an immutable Vercel Preview
backed by `tei-development`. Production, ingestion, schema, and product behavior
are out of scope. The moderator must record the exact Preview deployment URL,
commit, browser, session date, and Development fixture IDs before each session.

## Participants and consent

Recruit four people who did not build T.E.I.; do not invent or publish names.
Use only pseudonyms in this repository. Ask permission before screen recording;
store any recording, contact details, and private notes outside Git with a
retention owner and deletion date. A participant may stop at any time. Distinct
Development-only accounts are required for authenticated tasks; never use a
Production login or another participant's Workspace. Do not invite users or
create accounts before the operator has approved the session list.

| Slot | Intended role | Core tasks | Question they should be able to answer |
|---|---|---|---|
| P01 | Legislative office assistant | T1, T3 | What can the published term and declaration actually establish? |
| P02 | Investigative journalist | T2, T6 | Can a company-to-politician link and a separate company lookup be traced to originals? |
| P03 | Civic-data researcher | T2, T4 | Can the same link be independently reproduced and saved with provenance? |
| P04 | Newsroom or legislative research assistant | T4, T5 | Can an investigation be resumed, exported, and monitored without historical false alerts? |

Use a 5-minute orientation without demonstrating task solutions, then 12–15
minutes per task and a 5-minute debrief. Ask users to think aloud; the moderator
does not name a button or search term after the task starts unless recording an
assistance event. At least one session should use a narrow laptop viewport and
one should use a phone-size viewport. Run the same scripts in Traditional
Chinese; record whether bilingual labels help or hinder.

## Preview fixture and task scripts

The following are **Development-only published examples verified by read-only
Preview calls on 2026-09-25**. Recheck before every session: publication can
change, and a missing fixture is a preflight failure, not a participant failure.
The donation and declaration are single reviewed samples; they do not establish
general political-data coverage. Never imply wrongdoing or a conflict of
interest from a displayed association.

| ID | Moderator prompt and steps (do not reveal the expected answer) | Completion evidence | Timebox |
|---|---|---|---:|
| T1 | “Find 王鴻薇. What term/party or committee information is shown? Open one original source.” Search → Politician Entity → term/relationship → Evidence. | Correct Entity distinguished from namesakes; term claim and original URL recorded, or a clearly labeled data gap. | 12 min |
| T2 | “Does 都一處有限公司 have a published, source-backed link to 王鴻薇? Show the shortest path and prepare a shareable report.” Search → Company Entity → political contribution → Graph → Path Finder (max 3 hops) → edge Evidence → Entity/Politician Report. | One-hop path and contribution date/amount/type read accurately; Evidence and original source reachable; report downloaded without a legal inference. | 15 min |
| T3 | “Find 黃珊珊’s available annual asset declaration. What type and year can you verify? Is a year-over-year change supported?” Search → Politician → asset record → Evidence. | Published 2026 vehicle line/source located; participant correctly says one observed year cannot support a trend. | 12 min |
| T4 | “Save the fact you would revisit, add a note, then export the investigation.” Sign in to a personal Development account → Workspace → save Entity/Relationship/Evidence or source and Note → Workspace Report. | Owner-only item survives refresh; report is readable/downloadable and includes source and retrieval provenance; no other user's item appears. | 15 min |
| T5 | “Follow the Entity you just investigated and check whether the Dashboard has a new alert.” Watchlist → sync/check Dashboard → read/unread if an eligible **new** event exists. | Subscription saved; no pre-watch historical event misrepresented as new. Read/unread is separately marked `not_run` if no eligible event exists; do not ingest synthetic records just for this Pilot. | 12 min |
| T6 | “Check a different valid company by name and 統編 23060248. What do the company, procurement, penalty, and judgment views actually show?” Global/company search → legacy company investigation → source links. | Search/fallback distinction, available facts and unavailable/partial coverage stated correctly; zero judgments is not described as proof of none. | 15 min |

Before T2, confirm the published Company–Politician contribution and its
Evidence are still visible in Preview. Before T3, confirm the one asset line and
source URL. Before T4/T5, confirm a separate Development account can sign in
and that Workspace/Watchlist requests without a session are rejected. Do not
preload private Workspace data. Tasks T4/T5 are not ready for a person until
their Development account and consent are confirmed.

## Measurement and acceptance

These are **small-sample, provisional usability gates**, not population
estimates or proof of national data coverage. Review every failed attempt and
verbatim feedback before deciding what to change.

| Measure | Operational definition | Provisional gate |
|---|---|---|
| Core task success | Correct answer **with source or explicit coverage limitation**, no moderator hint; denominator = eight planned task attempts. Fixture outage is `not_run/preflight`, never silently removed. | At least 6/8 unassisted; all attempted results shown individually. |
| Time to verified answer | Seconds from reading the prompt to correct answer plus source link or downloaded report; report raw elapsed, including retries. | Median of completed T1–T3 attempts ≤ 8 minutes; diagnostic only until baseline exists. |
| Provenance trust guardrail | Positive facts used in answers/reports expose Evidence, source URL, and retrieval date, or are explicitly flagged missing. | 100% of cited Pilot facts checked; any missing provenance is a blocking defect for that fact. |
| Privacy/identity guardrail | Wrong same-name merge, other-user Workspace/Watchlist access, or unsupported illegality/conflict claim. | Zero observed; any occurrence stops Pilot and triggers triage. |
| Reliability guardrail | Application 5xx, failed download, broken source URL, UI blocker, or API timeout observed during a task. | No unresolved critical/high issue; record every error and reproduction. |

If a task succeeds only after a hint, mark `assisted`, not unassisted. If a
source is absent because the fixed-sample benchmark lacks coverage, mark
`data_gap` and score success only when the user correctly identifies that
limitation; do not turn unknown into zero. For T5, the no-new-event baseline is
scorable, but read/unread is an optional subtask until a legitimate new event
exists. Do not count `not_run` as success. With only four participants, report
counts and individual task times, not confidence intervals or “user adoption.”

## Per-task validation table (copy rows for each session)

Use one row per person/task. Times use ISO 8601 with offset; `elapsed_s` is
`ended_at - started_at`. Outcome: `pass`, `assisted`, `partial`, `fail`, or
`not_run`. Error class: `product`, `data_gap`, `upstream`, `account`, or `none`.
Keep private quotes/screenshots outside Git; put only a short redacted summary
and an issue reference here.

| Session / role | Task | Preview commit / URL | Started at | Ended at | Elapsed s | Outcome | Source/Evidence checked? | Error class + reproduction | Data gap / coverage label | UX blocker + severity | Feedback summary / issue |
|---|---|---|---|---|---:|---|---|---|---|---|---|
| P01 / assistant | T1 | pending | — | — | — | not_run | — | — | — | — | — |
| P01 / assistant | T3 | pending | — | — | — | not_run | — | — | — | — | — |
| P02 / journalist | T2 | pending | — | — | — | not_run | — | — | — | — | — |
| P02 / journalist | T6 | pending | — | — | — | not_run | — | — | — | — | — |
| P03 / researcher | T2 | pending | — | — | — | not_run | — | — | — | — | — |
| P03 / researcher | T4 | pending | — | — | — | not_run | — | — | — | — | — |
| P04 / assistant | T4 | pending | — | — | — | not_run | — | — | — | — | — |
| P04 / assistant | T5 | pending | — | — | — | not_run | — | — | — | — | — | — |

After each task ask: (1) “How confident are you in this finding?” (1–5),
(2) “Which source would you cite?” (3) “What was confusing or missing?” Record
confidence and source correctness in the issue note; do not equate confidence
with factual correctness. Capture request ID and UTC time for a reproducible
failure, not a bearer token, private note body, or password.

## Environment preflight and stop rule

- Baseline code: OPS commit `07f7af1`; latest checked Preview was `READY`.
  Public read-only smoke on 2026-09-25 confirmed Entity, Politician, Graph,
  one-hop Path Finder, contribution, asset, and Entity Report APIs. Preview's
  authenticated config pointed to `tei-development`; a published Politician
  returned the same Entity ID through Development REST and Preview search.
  Unauthenticated Workspace/Watchlist requests were rejected.
- Before each session, record the **immutable** Preview URL/commit and recheck
  that its public and authenticated reads target Development, not Production.
  Verify the two positive political fixtures, original links, and one test
  account per participant. Use only Development test accounts and personal
  browser profiles; clear session storage after the session.
- Stop a session on cross-user data exposure, wrong-identity merge,
  unsupported harmful conclusion, unexpected Production target, or a critical
  runtime failure. Preserve request ID and the minimal reproduction. Do not
  “repair” data, alter Production, or change features while conducting the
  Pilot; triage later on a separate branch.

At this handoff the plan and blank table are ready; participant recruitment,
consent, account setup, and real-user results are intentionally pending.
