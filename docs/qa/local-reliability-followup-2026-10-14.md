# Local storage and CI followup — 14 October 2026

This is an author verification receipt for `codex/local-reliability-followup`,
starting from the open draft stack at
`419b0d3f9a931072ad6eb21c4c5c85de772735fb` (PR #18). It is not independent
physics acceptance or production release approval. Hosting remains undecided;
the user confirmed that its selection is their later decision.

## Implemented behavior

- Content-addressed retries compare retained object bytes with the proposed bytes
  before acknowledging success. Empty, replaced or appended objects refuse;
  existing object bytes and first-write metadata remain untouched. Newly created
  shard entries are synced before publication is acknowledged. A directory-sync
  failure returns an error, cleans temporary files and permits a verified retry.
- Rotor-map reimport exposes that refusal through the local API as HTTP 422.
  A corrupt source cannot be silently repaired by reimport, frozen or accepted as
  a new study. Recovery of corrupt evidence remains an explicit operator action.
- Local backup refuses symlinked database/artifact source roots. Restore rejects
  symlinked manifests and unlisted empty-directory or dangling links before it
  creates a destination. SQLite's transactional backup retains committed WAL
  records without forcing a source checkpoint or changing its WAL bytes.
- The QA disk-pressure helper retains an executable file mode. CI cleanup succeeds
  when earlier setup never created service state; actual container-removal failures
  still fail and preserve state for retry.

The two CI defects were observed in the existing [GitHub run
38602799047](https://github.com/PhysiCoreEngine12/Drone-Project/actions/runs/38602799047):
Ruff EXE001 followed by missing `private.json` in the always-run cleanup step.
This followup does not treat that failed run as verification of later CI stages.

## Performed checks

Runtime: CPython **3.11.17**, with hash-verified `requirements-test.lock` installed.
The existing CI runtime pin is **3.11.16**; this local run does not replace pinned CI.

| Command/check | Actual result |
|---|---|
| `.venv/bin/python -m pytest -q -m 'not backend and not integration'` | **603 passed, 5 deselected**, 35.34 seconds |
| Reference suite, independently run under `reference_impl` | **118 passed**, 1.05 seconds; reference files unchanged |
| `.venv/bin/python -m ruff check .` | Passed after correcting the executable mode |
| `git diff --check` | Passed |
| `.venv/bin/python scripts/qa/platform_smoke.py` | Local synthetic V4 study/PDF worker journey, scoped denials and revocation passed |
| `.venv/bin/python scripts/qa/disk_pressure_drill.py --receipt …` | Both injected object/metadata ENOSPC paths recovered; stale publication refused and temporary directory cleaned |
| Declared numerical-module closure versus exact parent Git objects | All **18 modules byte-identical** |

The added behavioral tests cover three corruption forms, publication-sync failure
and retry, public rotor-map retry refusal, two linked source roots, three restore
link forms, WAL restoration, absent-state repeated CI cleanup and preservation of
state after a real cleanup command error. Docker calls in the cleanup error test
are mocked; no container was started by that test.

One existing Starlette/httpx deprecation warning appears in the unit/reference
suites. No dependency update was made to hide it.

## Review and remaining gates

Four agents were started including the lead, with model, backend and QA roles.
The backend agent identified the corrupt-object retry defect before account usage
limits stopped it and the QA agent. Their initial reviews used `main`; the lead
then found the newer open stack, preserved preliminary work outside the repository,
and performed the final integration and checks on the stack. Do not count these
agent roles as completed independent acceptance of this candidate.

The numerical model and historical/reference artifacts are unchanged. Current
cross-family model review, human engineering acceptance, real aircraft inputs and
preregistered validation remain open. No physics extension, merge, tag or external
deployment is performed by this receipt.

Backend/vendor, PostgreSQL/provider, browser, release-image and long-soak checks
were not rerun locally for this followup. Five backend/integration tests were
deselected, not passed. The injected ENOSPC drill does not establish physical disk
exhaustion, SQLite ENOSPC, hardware power-loss durability, a cross-store transaction
or hosted RPO/RTO. Backup still requires quiesced writers and trusted local roots;
the link checks do not protect against a concurrent hostile filesystem rewrite.

The prospective PR uses `main`, the required repository default base, and therefore
includes the earlier unmerged stack. Review this followup separately from its
parent commit; the cumulative comparison does not approve those earlier changes.

## Post-commit review and release checks

The same-family peer agent reviewed reliability commit `de9ad401a636fb49ed9fd103ac2c5e50ccdfa72f`
against its exact parent, found no correctness issues in this subset, and independently
passed **34 targeted tests** plus Ruff. This is bounded plumbing acceptance, not
the outstanding cross-family model or human engineering approval.

A clean wheel of that commit passed `scripts/release/verify-wheel.py` in a separate
runtime virtual environment outside the checkout: **130 verified resources**,
V4 study/PDF journey passed, **1.64-second local startup**. Build SHA-256:
`cd656818dff04bf5221d1e0b4d3a72f71974dc394a3548c6402ff0adba1a635b`;
wheel SHA-256: `0435abfd5bde434462c18cafe242d2f7f128b310265ab5a6917f3ee8c0eced97`.
This remains a Python 3.11.17 local check.

[PR #19](https://github.com/PhysiCoreEngine12/Drone-Project/pull/19) is a cumulative
draft against `main`. Its first [CI run](https://github.com/PhysiCoreEngine12/Drone-Project/actions/runs/38636829974)
passed lint, unit/reference, worker smoke/recovery, PostgreSQL integration and sphere
smoke, then failed the release-image stage because `rg` was unavailable on the runner.
The background PR-fix helper independently supplied `a0823db88fc87ac681e3104887df086c36a8e25d`:
use standard `grep -E` without early stream closure for the exact BuildKit driver guard.
That fix was preserved; no Docker/provider deployment was performed locally.

The new whole-entry-point regression tests run with a deliberately restricted PATH
containing `grep` and controlled Git/Python/Docker substitutes, with no `rg` or real
Docker daemon. The required `docker-container` driver reaches both offline image
targets; `docker` and `kubernetes` refuse before builds. The lead and peer agent
each passed **3 tests**, Ruff and shell syntax checks. Full release-image/browser
CI on the resulting head remains pending; the initial failed run is not a release PASS.

## Final implementation CI receipt

Implementation head **`5f5ffe4a2a39c50502bed8d4c40f92d4c5173d8a`** passed the
[PR integration run](https://github.com/PhysiCoreEngine12/Drone-Project/actions/runs/38638098734)
and [branch run](https://github.com/PhysiCoreEngine12/Drone-Project/actions/runs/38638091501).
The intervening browser-recording failure was missing `/usr/bin/ffmpeg`; the
background PR-fix helper provisioned it before browser journeys in `5f5ffe4`.
The recording requirement was retained rather than skipped.

The PR integration run used Python **3.11.16** and tested integration commit
`92641f93657a07fa9570bad344d8c234c47621ee`. Actual results: **606 unit tests passed,
5 deselected** (48.68 seconds), **118 reference tests passed** (1.29 seconds),
Ruff, local worker smoke, real supervisor interruption/recovery, PostgreSQL
integration, installed-wheel journey, restricted application/worker image
journey and both local/private browser journeys passed. The pinned sphere-smoke
job passed. The optional full vendor-backend job was **skipped**, not passed.

CI packaged build identity:
`ad2d226e2f40e4294f968e13cd2caa47fd9119cfd33a1c9a5bfa94bdfb1a7ace`.
Verified application image:
`sha256:2ed6a976c7823de611f02a0ca2a40648b1d812228a02f999b3cd593999fa8c00`;
worker image:
`sha256:562cac95a06682afefc2d450d76624de7ee819e1bc237a7fe80eb04857242769`.
These are tested CI artifacts, not a deployment or production release.

This final receipt and roadmap update change documentation only. No numerical
module differs from parent `419b0d3`; physics review, named human engineering
acceptance, real-aircraft validation and the user's later hosting decisions remain
open. PR #19 remains draft and unmerged.
