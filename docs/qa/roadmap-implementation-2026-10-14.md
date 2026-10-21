# Roadmap implementation evidence — 14 October 2026

Implemented A01–A03 against platform source `60c0ab2efa7b2352d02458a517c4fe2fe5969b5b`. Issues [#10](https://github.com/PhysiCoreEngine12/Drone-Project/issues/10) and [#11](https://github.com/PhysiCoreEngine12/Drone-Project/issues/11) record scope/outcome. No production or numerical-source file changed.

## Delivered

- [Commit-aware baseline reconciliation](baseline-reconciliation.md) separates inherited main changes from model/platform work and identifies historical draft PR ancestry.
- [Exact-model review checklist](model-review-checklist.md) gives actual repository commands and independent/human gate requirements; it does not close those gates.
- [Bounded submission diagnostics](submission-profiling.md) adds a standalone helper and six regression tests. All measurement inputs are disposable synthetic fixtures; no worker/solver runs.

## Performed checks

| Check | Actual outcome |
|---|---|
| GitHub source comparison | Main/model/platform ancestry checked; zero changes in the declared 18 numerical modules between model/platform parents; closure completeness not proved |
| Source materialization integrity | 246 selected executable text files retrieved via connected GitHub API; each matched its exact Git blob hash after trailing-newline transport correction; not a complete 502-entry checkout |
| Targeted tests | `PYTHONPATH=src ../submission_profile_work/.venv/bin/python -m pytest -q tests/test_submission_profile.py tests/platform/test_identity_jobs.py`: **11 passed in 1.63 s** |
| Repository-rule lint | Ruff on `scripts/qa/submission_profile.py` and `tests/test_submission_profile.py`: passed; import grouping corrected after initial finding |
| Actual API diagnostic | Three primary and three separately instrumented fresh submissions; every response HTTP 202/queued; all six cancelled; no computation started |
| Documentation QA | Actual QA subagent checked source identities, links, command paths and gate semantics; ancestry/source-equality clarifications applied |
| Code review | Actual separate code-review subagent reviewed helper/docs, independently ran six helper tests; identity and cancellation-failure findings fixed; no remaining blockers |

Implementation used actual `baseline_implementation` and `submission_profile` subagents. `baseline_qa` and `code_review` performed the stated independent task checks. They are same-family agents; no cross-family physics acceptance or named human approval is claimed.

Final synthetic observations are retained in [the allowlisted JSON receipt](submission-diagnostics-2026-10-14.json). Primary request times: 7.191, 14.691 and 7.585 ms. Instrumented times are separate and their inclusive spans are not additive. Three serial loopback observations cannot explain the historical 50-user PostgreSQL p95 or establish a service target.

## Environment and verification limits

Direct Git clone lacked credentials; authorized GitHub app reads supplied the selected snapshot. Isolated scratch environment: Python **3.12.14**, FastAPI 0.143.0, httpx 0.28.1, Starlette 1.8.0, Pydantic 2.14.1, NumPy 2.3.5, SciPy 1.17.0. It differs from the repository's pinned Python 3.11.16/hash-locked CI environment. Commands above describe the actual temporary environment, not an installed user dependency requirement.

Full unit/reference suites, pinned CI reproduction, Docker/OpenFOAM backend, PostgreSQL/concurrent network load, browser checks, provider policy/recovery, 24-hour soak and engineering qualification were **not run**. Docker is unavailable here. No historical 529/118 pass is promoted to this run. This change leaves model review, human engineering acceptance and real-data gates pending; nothing merged or deployed and no flight-critical logic changed.

Next: run the diagnostic in the pinned CI environment; investigate relevant external workload before optimizing; execute safe disposable recovery/intake tasks from their approved issues. U05 remains review gated.
