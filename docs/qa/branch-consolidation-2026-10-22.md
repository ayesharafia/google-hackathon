# Branch consolidation: 22 October 2026

The user explicitly requested investigation and consolidation of all branches
and PRs into `main`, followed by cleanup of the clutter. This authorizes repository
integration; it does not approve physical assumptions or customer accuracy.

## What the inventory found

Starting `main`: `73793c9e39f840864ebb885bd65b9b38706eaa07`.
There were 19 remote branches besides main, and six open PRs.
The [machine-readable inventory](branch-consolidation-2026-10-22.json) retains
their exact original heads and disposition.

| PR | Finding | Integration path |
|---|---|---|
| #1, #2, #3 | Heads are already ancestors of starting main | Close redundant draft PRs; retain their existing commits |
| #9 | One unique historical roadmap document; its platform parent was already included by PR #20 | Merge the historical proposal into #21, preserving its proposal status |
| #21 | New retained-study viewer/summary, organization inventory and artifact quota foundation | Reconcile with current geometry/access and integrate into main |
| #22 | New kickoff report, roadmap, draft DR-01 and synthetic diagnostic | Integrate into main; preserve pending scientist fields |

The old platform/roadmap/reliability chain ends at `f861e0a`. Its complete tree
is byte-identical to `d2e7862`, the existing squash merge of PR #20. After this
comparison, an explicit history-only merge links that chain without replacing
the later geometry, access or kit changes. Intermediate branch heads then remain
reachable from the consolidated history. The historical #9 proposal is added
with an ordinary merge and supplies only its previously missing document.

A verified local Git bundle of all pre-consolidation refs is retained under
`.backend/branch-consolidation-2026-10-22/pre-consolidation.bundle`. It is a local
recovery artifact, not project data or a new remote branch. Retired remote/local
branches may be deleted only after their heads are verified as ancestors of main.

## Conflict resolution and fixes

Three files conflicted: `web/js/workbench.js`, `web/workbench.html` and
`web/css/workbench.css`. Both branches' intent is retained:

- Original STL upload, units, draft save/reopen and geometry preview.
- Remembered browser sessions and explicitly configured public local access.
- Frozen study/revision views, selected cases, numeric inputs and source references.
- Retained-study summary, input navigation and saved inspection guidance.
- Organization/session changes clear stale project context; late responses are
  ignored. Local cookie requests and hosted identity requests use the same
  context checks. Hosted read-only roles cannot edit draft geometry.

The failed #22 CI run exposed four inherited lint findings in the geometry/access
commit: import ordering, an unused bearer string, duplicate Python handler names
for distinct geometry routes, and the exception type for a non-boolean setting.
The import is sorted, the unused string removed, the project handler renamed
without changing its route, and invalid setting types raise `TypeError`.
The existing Ruff command reproduced all four findings and passed after fixes.
JavaScript syntax and diff whitespace checks also passed.

No solver equation, model constant, physical tolerance, validation fixture or
physics acceptance is changed. The draft DR-01 remains awaiting scientist review.
Existing model/release gates retain their recorded status. The user's merge
instruction is recorded separately in `DECISIONS.md`.

## Verification and completion record

GitHub Actions runs against the integration heads provide the unit/reference,
PostgreSQL, worker, installed package/image, browser and sphere checks already
defined by the repository. Actual results and final cleanup are recorded below
after those runs finish. Full vendor-backend qualification remains a separate
workflow; no new aircraft validation is claimed by repository consolidation.
