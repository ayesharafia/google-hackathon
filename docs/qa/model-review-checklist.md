# Current-model reproducibility and review checklist — 14 October 2026

Documentation-only implementation of roadmap A02. Candidate: `codex/production-platform` at `60c0ab2efa7b2352d02458a517c4fe2fe5969b5b`; recorded numerical parent: `5e8cf066eea164398dbd94380175ae7d00a4279c`. Integrated main: `802c63a0a9f9b776f92fb94efe24a1708d95ebdb`. Re-select and record an exact head when code changes. This checklist is not a review PASS or a test execution receipt.

## Pin the review and capture identity

- [ ] Record issue/PR, base/head SHA, UTC timestamp, reviewer identity/tool and actual independence. An ordinary code-review agent does not establish cross-family physics review or human approval.
- [ ] Obtain the exact candidate and parent in an isolated checkout; confirm `git rev-parse HEAD` and a clean `git status --short` before execution.
- [ ] Inspect the candidate's `AGENTS.md` files if newly introduced. The two inspected complete trees contained none.
- [ ] Compare all declared numerical modules against the model parent. Capture exact bytes/hashes and NumPy/SciPy versions; a matching module name alone is insufficient.

`src/physimesh/projects/studies.py:MODEL_MODULES` declares 18 paths under `src/physimesh`: `drone/performance.py`, `drone/conditioning.py`, `drone/trim.py`, `drone/capacity.py`, `drone/mission_capacity.py`, `drone/scenarios.py`, `drone/authoring.py`, `drone/atmosphere.py`, `drone/mass.py`, `drone/screening_scope.py`, `drone/models.py`, `drone/frames.py`, `drone/units.py`, `drone/provenance.py`, `drone/snapshot_hash.py`, `drone/local_results.py`, `projects/contracts.py`, `projects/performance.py`. Inspect dependencies for closure rather than assuming this declaration proves completeness.

After setup below, capture the actual identity without printing design data or credentials:

```sh
.venv/bin/python -c 'import json; from physimesh.projects.studies import model_identity; print(json.dumps(model_identity(), indent=2, sort_keys=True))'
```

The default identity uses the static model version; extended study preparation explicitly selects `EXTENDED_MODEL_VERSION`. Review both paths. `convex_static_hover_v1` produces V3; opt-in `convex_axial_capacity_v2` produces `local_mission_capacity_v4`. Retained V2/V3/legacy readers must preserve original qualification and bytes.

## Reproduce supported software checks

The following setup and test commands follow the candidate's `.github/workflows/ci.yml`. Network/package availability is required; report installation failure before claiming a test pass. Python pin in CI is 3.11.16.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-test.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest -q -m 'not backend and not integration'
(cd reference_impl && ../.venv/bin/python -m pytest -q)
.venv/bin/python -m pytest -q tests/drone/test_conditioning_and_axial.py tests/projects/test_scenario_limits.py tests/projects/test_semantic_identity.py tests/projects/test_extended_retention.py tests/projects/test_contracts.py
.venv/bin/python scripts/qa/reproduce_conditioned_fixture.py
```

The last helper requires the retained synthetic snapshot/sources and exact model/library identity and deliberately refuses drift. A refusal must be recorded; do not refit, alter stored identities or regenerate accepted bytes to force a pass. Existing historical checks were not rerun while preparing this checklist.

Optional platform checks from CI, after their dependencies are provisioned:

```sh
.venv/bin/python scripts/qa/platform_smoke.py
.venv/bin/python scripts/qa/worker_failure_drill.py --receipt .backend/worker-failure.json
.venv/bin/python scripts/qa/platform_services.py start
.venv/bin/python scripts/qa/platform_services.py test
.venv/bin/python scripts/qa/platform_services.py stop
```

Ensure `stop` runs after failures too. These use local/disposable services and do not qualify a provider. Browser helpers need Playwright, Chromium and recording dependencies; use the candidate's CI browser environment and retain actual receipt paths. Backend tests need Docker, the immutable OpenFOAM pin and where applicable the verified vendor archive documented in README. Do not count skipped backend/integration/browser/release-image checks as passes. The frozen baseline verifier additionally requires retained `.backend` evidence unavailable from Git alone; exact historical verification differs from creating a new study.

## Review the numerical and contract behavior

Use [the existing review packet](production-model-review-packet.md), [ADR-0005](../decisions/ADR-0005-conditioned-axial-profile.md) and [validation](../validation/capacity-uncertainty.md), then inspect implementation and independent fixture derivations:

- [ ] Power envelope dominates declared sample/interpolation targets, shaft `Q × Ω` is reconciled and efficiency applied once. State the narrow surrogate conservatism scope; do not infer universal physical capacity bounds.
- [ ] Torque discrepancy checks cover independent rotor corners and sourced axis allowances; counterrotation does not cancel errors or establish controller capability.
- [ ] Motor-out commands are zero while hardware mass remains; check quad certificate and octo fixture separately. Preserve unresolved floating-point endpoints; do not clamp away failures.
- [ ] Climb requires exact covered density/inflow/pitch, documented sign and supported steady axial kinematics; missing coverage refuses rather than extrapolating hover.
- [ ] Scenarios retain joint changes and correlation; all cases and chronological energy are evaluated at one common candidate. No probability inferred.
- [ ] Caps remain separately sourced and qualified; smaller/zero payload may require fresh feasibility. A declaration is not authenticated engineering acceptance.
- [ ] Supported feasible/infeasible/unsupported/unresolved semantics and certificate scope hold. Conditioned-surrogate failure cannot prove physical impossibility.
- [ ] V2/V3/V4 read/export and snapshot numeric identity remain compatible; forged/omitted case, energy, source, coefficient or association fields refuse.
- [ ] Numerical closure includes eligibility, atmosphere, units, contract and source-policy dependencies. Cosmetic changes must not silently requalify old evidence.

## Required outcome receipt

For each attempted command record exact head, runtime, command, exit/result, counts and deselections, duration and retained evidence path. Separate **performed**, **failed**, **skipped**, and **not available**. Retain findings with severity, affected files/versions, independent derivation and proposed fix; flight-critical fixes require user approval before editing. Record author verification, independent model review and named human engineering acceptance separately. A synthetic fixture success is neither real-aircraft validation nor permission to merge/tag/deploy.
