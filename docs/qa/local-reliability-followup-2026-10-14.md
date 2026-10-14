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
