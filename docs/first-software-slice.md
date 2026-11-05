# First software slice: layered atmosphere, not aircraft design

Local review patch, 5 November 2026. Base observed in company main:
e31f7314d1565b861aa39ee3d8d566a0c6af240a.

## Included

- Add `src/physimesh/drone/standard_atmosphere.py`: dry reference atmosphere,
  explicit geometric/geopotential convention, bounded 0–30,000 m, absolute p/T,
  density and model provenance. No default aircraft or flight duration.
- Add six test groups: independently published rounded table values;
  continuity at 11/20 km geopotential layers; altitude conversion; refusal of
  missing/invalid convention, nonfinite/nonnumeric/out-of-range inputs; positive
  properties/monotonic pressure/provenance; unchanged legacy helper boundary.
- Import-order-only change to `scripts/qa/agent_fixture.py`, matching the observed
  lint failure. Syntax compiled. Pinned Ruff passes for changed/new file scope; full company CI NOT run here.

## Explicitly not included

This is a partial local source snapshot, NOT a clone, complete build, remote
branch, commit in the company repository or pull request. It now adds a stateless strict API evaluation router with canonical evidence
hashes and existing app registration/auth gating. It does not silently change existing
atmosphere behaviour, grant high-altitude applicability to rotor maps, validate
an aircraft, add weather, or claim aircraft-level validation. Existing workflow checks are exercised below.

## Integrated executable contract

- Model/version: `coesa1976.lower-atmosphere.0-30km.v1`.
- Required inputs: supported model ID, altitude in metres, explicit convention.
- Outputs: absolute Pa, K, kg/m3, source and canonical input/evaluation hashes.
- Applicability: reference dry atmosphere only, input 0–30 km, not local weather
  or a pressure-altitude inverse. No wind/thermal/propulsion claim.
- Evidence: `unverified`, aircraft status null. Existing explicit manifest values
  are returned without automatic project persistence.
- Refusal: wrong model, convention, range or nonfinite input cannot fall back to
  tropospheric extrapolation or density-scaled unqualified propulsion maps.

## Next integration work, unblocked by aircraft design

1. Land the reviewed slice against current remote base and monitor company CI.
2. Add an explicit model selection to project authoring with backward-compatible
   migration, invalidation and actual UI checks. This stateless route does not
   implicitly alter saved project atmosphere inputs.
3. Register existing analytical models and scope/refusal rules incrementally.
   Graph/cycle integration follows actual dependencies; unsupported solver
   paths stay unavailable. Adapt the existing workflow, not a second ledger.

## Verification performed

Twenty-one new tests and 17 subtests pass on CI Python 3.11.16 with hash-verified
locked dependencies. Changed-scope Ruff passes. Real application checks and
broader tests are detailed below. Independent private review inspected the
physics, request contracts, finite-error handling and auth; final round is pending.
Table tolerances cover displayed rounding, not physical model-form uncertainty.

## Sources

- https://www.pdas.com/atmosdef.html : layers, sea-level conditions, standard.
- https://www.pdas.com/hydro.pdf : hydrostatic law, altitude conversion,
  gas constant/molecular weight, Earth-radius convention.
- https://www.pdas.com/atmosTable1SI.html : independent rounded p/T/rho at
  geometric0/10/20/22/30km. Do not compare these directly to geopotential heights.
- https://ngdc.noaa.gov/stp/space-weather/online-publications/miscellaneous/us-standard-atmosphere-1976/us-standard-atmosphere_st76-1562_noaa.pdf
  : primary1976standard; downloaded for source provenance. Its scanned text is
  noisy; constants used here were checked in the readable PDAS transcription.

The patch contains no credentials and no transfer to a personal repository.
This document does not authorize repository writes; execution permission is separate.
External-model company-source disclosure is not approved. This package is private.

## Integration follow-through

The stateless `/api/drone/atmosphere/evaluate` router takes a supported model ID,
SI altitude and explicit convention. It returns source, input/evaluation hashes,
explicit values for the existing manifest, unverified evidence level and null
aircraft status. Normal app authentication applies; no project data is read or
written. Existing project save/version/freeze is the only intended persistence
path. Actual project parser/readiness and canonical hashes were tested.

Python3.11.16 and hash-verified requirements-test.lock now match the inspected CI.
All21new tests and17subtests pass with pinned dependencies; scoped Ruff passes.
The legacy gas constant287.05 differs from the source constant used by COESA.
Both remain explicit; tests check the exact ratio rather than conflate densities.
The hosted auth route edit has isolated exact-middleware and real application
startup tests; final re-review remains pending. A reviewer-reproduced nonfinite-input
validation500 is fixed by route-specific error sanitisation and six regressions.
Canonical route is `/api/drone/atmosphere/evaluate`; hosted trailing slash403 is
explicitly tested as fail-closed, not an authenticated alias.

Existing workflow.py and task ledger recovered. Local ATMOS-001 is in_progress;
its check command retained test/lint receipts. It is not marked done. The loop
starts from already prepared code, so initial receipts document checks rather
than claim original code changes were made after task start.

## Real application checks after source recovery

Recovered text source/test/web at the inspected commit; binary solver fixtures
remain unavailable. Real create_app startup and SQLite identity tests pass in
both local and hosted mode: unauth/wrong token401, valid session without project
200, no project mutation, nonfinite422, unrelated hosted legacy403. This is no
longer only an AST isolation test. The broader drone/projects/platform/API run
passes475tests,3deselected,17subtests. Full CI/backend/browser jobs are separate.

The new route deliberately returns generic422 detail for validation errors to
avoid reflection/serialization of NaN or Infinity. Other routes are unchanged.

## Expanded baseline limits

The 475-test selection excludes backend and integration markers. Its three
excluded tests are the independent-writer, leases/fences/tenant-inventory and
artifact-reservation/failure/publication PostgreSQL tests in
`tests/platform/test_postgres_integration.py`.
Expanded recovered-tree execution (excluding remote_http because httpx2 is
missing) produced 756 passes and 36 failures due missing MCP SDK/native binary
solver fixtures. Full recovered-tree Ruff reports 67 baseline errors outside
this patch. These failures are retained, not suppressed or repaired speculatively.
Remote CI must be inspected separately; no full-green claim is made.
