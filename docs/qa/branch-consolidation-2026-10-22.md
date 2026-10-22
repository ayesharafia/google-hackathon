# Branch consolidation: 22 October 2026

The user explicitly requested investigation and consolidation of all branches
and PRs into `main`, followed by cleanup of the clutter. This authorizes repository
integration; it does not approve physical assumptions or customer accuracy.

**Final direction:** the user subsequently clarified that all branches should be
kept and only main needs to be updated. The nine branch names removed before
that clarification were restored at their exact previous heads. All 19
non-main remote branches and all local branches are retained. Entry 010 in
`DECISIONS.md` supersedes the earlier branch-retirement instruction.

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
recovery artifact, not project data or a new remote branch. No further branch
deletion is authorized under the user's clarified direction.

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

Integration CI also exposed an intermittent Linux procfs race in the existing
worker failure drill: a child could be reaped between the existence check and
reading `/proc/<pid>/stat`, raising `ProcessLookupError`. The read now treats
only missing/reaped-process errors as child exit. The zombie check, timeout,
restart and stale-publication assertions remain unchanged. This fixes the
observation harness without changing the worker or relaxing an acceptance check.

No solver equation, model constant, physical tolerance, validation fixture or
physics acceptance is changed. The draft DR-01 remains awaiting scientist review.
Existing model/release gates retain their recorded status. The user's merge
instruction is recorded separately in `DECISIONS.md`.

## Verification and completion record

PR [#22](https://github.com/PhysiCoreEngine12/Drone-Project/pull/22) merged at
`b54406e`; PR [#21](https://github.com/PhysiCoreEngine12/Drone-Project/pull/21)
merged at `90b4a8ebc171038668950f211541631251d41719`. Every original remote
branch head and every historical PR head is included in the resulting main
history. Redundant PRs #1-#3 were closed because their heads were already on main;
the original #9 proposal is retained through #21, with its original PR left open.

Both integration runs passed at `902a0ea2460d67e84da9fe53f8288921da5fcc1a`:
[push CI](https://github.com/PhysiCoreEngine12/Drone-Project/actions/runs/39761676837)
and [PR CI](https://github.com/PhysiCoreEngine12/Drone-Project/actions/runs/39761686000).
The main merge tree was verified byte-identical to that checked integration tree
before this documentation-only completion receipt.

| Performed check | Actual result |
|---|---|
| Application suite | 670 passed, 6 deselected; existing deprecation warning |
| Reference suite | 118 passed; existing deprecation warning |
| Disposable PostgreSQL integration | 3 passed |
| Sphere smoke | 1 passed |
| Ruff; private smoke; bounded harnesses; worker recovery | Passed |
| Installed wheel and offline release images | Passed |
| Local/private and focused client-workflow browser journeys | Passed |

Reviewed the retained desktop and mobile screenshots for the affected merge UI.
The combined geometry and study controls remain visible, text has gutters and
contrast, and no new decorative styling or hidden entrance content was added.
Browser receipts confirm 390px layout without document overflow, native 200%
zoom, real downloads, retained geometry linkage, conflict recovery, private
denial/revocation and result viewing. This is a scoped integration check, not
client visual acceptance or a claim that every existing product control was
exhaustively tested. The optional full vendor-backend campaign was skipped;
no new aircraft validation is claimed.
