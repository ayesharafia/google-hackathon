# Job Activity & Recovery: executed checks

26 October 2026. Baseline `f8efdd34efe30558cfc9714706d4b51c2be0a81e`.
Owner approved the concrete hosted job-inspection/recovery design, targeted
unit/API/browser checks, full interface-law review and main publication.
One implementing Codex agent. No independent science acceptance claimed.

## Scope

The existing hosted job list now opens literal job/attempt evidence without
waiting for a terminal state. Manual detail/history refresh, bounded older-job
pagination, explicit permission/state-aware cancellation/retry and guarded
associated-study navigation reuse existing routes. No background monitor,
automatic retry, fabricated ETA, new API/dependency or queue/access/model change.
The existing job GET's accepted-result materialization remains unchanged.

## Final suite evidence

Receipts below are relative to `.physicore/evidence/`. Counts are distinct final
suite checks, not a sum of reruns.

| Suite | Result | Receipt |
|---|---|---|
| Job projection, state/identity/attempt validation, timestamps, report binding, pagination and async/recovery lifecycle; existing source/trim/pack/energy/comparison/readiness/binding units | 148 pass: 24 new, 124 existing | `JOBS-001-test-20261026115327051675.json` |
| Existing identity/job, release-recovery, worker-publication/accounting and reuse-pagination Python regressions | 27 pass | `JOBS-001-test-20261026114458203240.json` |
| New installed-Chrome hosted owner/viewer journey | 22 pass | `JOBS-001-test-20261026115330588292.json` |
| Existing source-explorer public-mode journey | 17 pass | `JOBS-001-test-20261026115137526753.json` |
| Existing Case Trim Evidence public-mode journey | 19 pass | `JOBS-001-test-20261026115137036372.json` |

Browser total: 58 checks across these three journeys, no page JavaScript errors.
Existing Starlette/httpx deprecation warning remains. Wheel/static receipt is
listed in the task's completion proof and verifies four exact web assets and
resource hashes, JavaScript/Python syntax, protected paths, document links,
147-entry law ledger, whitespace and screenshot hashes.

## Real fixture and controlled responses

`scripts/qa/job_activity_fixture.py` requires an explicit disposable flag, binds
loopback only and writes into a new `.backend` temp directory. It seeds a local
SQLite hosted-mode app with owner/viewer identities, a separate private project,
33 jobs and real retained study/PDF artifacts from an incomplete synthetic
design. The Jobs API records queued, running, failed, cancelled and accepted
states; two-attempt history has an actual explicit retry and recorded heartbeat.
No live worker daemon or production identity provider runs. This is software
evidence, not an aircraft validation or production-worker qualification.

The browser uses real cursor pagination, exact detail, cancel and retry routes.
It verifies one explicit retry request, real queued cancellation, accepted study
and report navigation, unchanged saved draft/unsaved text/retained study bytes,
viewer disabled actions and actual server 403 responses for viewer writes and
foreign-project reads. Keyboard Enter refresh restores focus; pointer controls
and exact-record disclosure respond. All 33 jobs have distinct visible short IDs.

Labelled intercepted responses separately exercise wrong identity, missing
attempt progress, denied detail and failed/overloaded recovery. Real delayed
detail responses exercise job/project changes. Logout clears private evidence
and an injected detached recovery action does nothing. These response fixtures
demonstrate UI behavior, not a provider outage or full failure campaign.

## Visual review and corrections

The complete [147-entry interface-law ledger](job-activity-design-law-2026-10-26.md)
is scoped to the new flow. Existing tonal engineering-sheet styling remains.
Native buttons, disclosures and tables provide genuine controls. The authored
choice is a linked job/attempt record with explicit recovery, not a decorative
timeline, card wall, icon pack or marketing effect.

Review found and fixed a state cell wrapping mid-word and low contrast on a
selected history button. State cells now stay whole; the selected button uses
dark ink and a browser assertion checks contrast at least 4.5:1. Short IDs make
otherwise similar rows distinguishable. Current-attempt-limit wording avoids
presenting the value as an additional retry allowance. Focus/context/detached
action guards were inspected and exercised.

1440px desktop, 390px phone and CSS `zoom: 2` captures check field/control gutters,
aligned wide facts, stacked narrow facts, whole timestamps and scrollable attempt
columns. Phone/enlarged captures intentionally show the table scrolled to its
last detail column. Exact-record content is scrollable, not discarded by its
maximum viewport height. Final captures were regenerated and inspected.

- [Desktop sheet](assets/job-activity/desktop.png) and [context](assets/job-activity/desktop-context.png)
- [Phone sheet](assets/job-activity/phone.png) and [context](assets/job-activity/phone-context.png)
- [Enlarged sheet](assets/job-activity/enlarged.png) and [context](assets/job-activity/enlarged-context.png)
- [Executed browser result](assets/job-activity/results.json)

## Retained failed attempt and reproduction

`JOBS-001-test-20261026114949161285.json` failed because the mutating browser
journey reused its already retried fixture: the expected failed job was queued,
so its retry button was correctly absent. No assertion was relaxed. Subsequent
runs started fresh fixture processes. A preflight now explains this requirement.
Earlier successful intermediate runs remain retained as historical evidence.

Start a fresh fixture for every mutating journey:

```sh
PHYSIMESH_BROWSER_DISPOSABLE=1 PYTHONPATH=src .venv/bin/python -u scripts/qa/job_activity_fixture.py --runtime .backend/job-activity-runtime.json
```

In another terminal, set `PHYSIMESH_BROWSER_DISPOSABLE=1` and the installed
Playwright module path, then run `node scripts/qa/job_activity_browser.mjs`.
Stop only the owned fixture PID from the runtime receipt afterward. The harness
requires loopback and disposable mode. The public regressions use a separate
disposable public-access app; the original shared service/tunnel is untouched.

## Limits

Native browser zoom, screen-reader output, real-user usability, PostgreSQL/cloud
providers, production worker supervision, long-running load, recovery/backup
campaigns and physical accuracy remain unqualified. CSS zoom is not native zoom.
This feature applies to authenticated hosted-mode jobs, not public local mode.
Broader production and scientific gates remain open. No deployment or original
runtime restart performed. [Usage guide](../technical/job-activity.md).
