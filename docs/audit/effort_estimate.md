# Implementation record and pending effort estimate

Date: 2026-10-02. Branch: drone/wp01-foundation.

## Reviewed and committed

- Task 1.1: Python 3.11 scaffold, frozen third-party dependency versions,
  CI skeleton, greenfield ADR. Commit bd20974.
- Task 1.2: content-addressed artifacts, SQLite lifecycle ledger, hardened
  Docker argument builder. Commit e5015b2.
- Task 1.3: architecture guardrail. Commit 0507bd4.

Independent critic reviews approved all three tasks. The Task 1.1 review found
and resolved a directory-based CI gate that could skip backend fixtures.
Task 1.2 review clarified Docker memory units and required transactional orphan
recovery. Retained reference files and supplied test expectations are unchanged.

Final standards/spec review identified and corrected an untagged SQLite wait
timeout and a backend test that could silently skip when tutorial inputs were
absent. Missing backend fixture inputs now fail explicitly. The original backend failure was subsequently diagnosed and fixed with user
authorization; local meshing and profiling evidence is documented separately.
Backend CI still needs vendor source provisioning and is not passing evidence.

## Test evidence

Scaffold test first failed with `ModuleNotFoundError: No module named 'physimesh'`.
Core tests first failed with three missing-module collection errors. Both
passed after implementing their respective tasks.

Task 1.3 recorded project unit command:
`.venv/bin/python -m pytest -q -m 'not backend'`

```text
.........................                                                [100%]
25 passed, 1 deselected in 0.06s
```

Lint command: `.venv/bin/ruff check .`

```text
All checks passed!
```

Python 3.11 retained reference command, run from reference_impl:
`../.venv/bin/python -m pytest -q`

```text
118 passed, 1 warning in 4.31s
```

The warning is a FastAPI/Starlette TestClient deprecation for httpx. It did not
change test results. Reference code is excluded from production lint to retain
it unchanged; its own tests run separately. [ASSUMPTION]

## Sources

- Platform contracts, retained evidence and resource budgets: [M§26], plan Task 1.2.
- Execution states and allowed transitions: plan §4.2 and Task 1.2.
- Shared layer independence: [M§1], plan Task 1.3.
- Python, dependencies, CI and development fixture budgets: [ASSUMPTION], plan §6.0.
- Greenfield deviation and export integration seam: plan §2.1/§2.5, [M§0].
- No aerodynamic formulas or customer design values introduced in these tasks.

## BLOCKED / QUESTIONS

Task 1.4 Steps 1–5 have local fixture and short-window profiling evidence.
The mount failure is fixed; aircraft sizing and effort Steps 6/7 remain pending.
The user confirmed real geometry and rotor data are unavailable, and explicitly
authorized independent software tasks to continue with data-dependent steps
pending. See backend_pin.md and compute_sizing.md. The profiling window is
20 iterations and does not claim convergence.

No person-days estimate is supplied: [M§28] and Task 1.4 Step 7 require the
backend measurements plus first real STL and rotor-data review. Actual geometry
and rotor data remain required external inputs (Q03, Q04). Client greenfield
sign-off (Q01) remains separate from the user's implementation authorization.

This is a software progress record, not Release A acceptance or aircraft
validation. [M§2, M§27]


## Continued implementation checkpoint, 2026-10-02

Current branch: `drone/wp03-geometry`. All work remains unmerged into main.
The user approved OpenCFD v2606 and continuation of independent software tasks
while real geometry and rotor data are unavailable.

| Task | Delivered | Commit |
|---|---|---|
| 1.4 partial | Shared-path fixture recovery and two retained short-window profiles | dedd28d |
| 1.5 | Authenticated API shell, explicit settings, responsive browser workflow preview | e3064fd |
| 2.1 | Canonical input hashing and backend provenance gate | d3c83f1 |
| 2.2 | Declared length conversions and OpenFOAM dimension parsing | f6bcfef |
| 2.3 | Coordinate transforms, axial/polar distinction and signed rotor frame | 2265a49 |
| 2.4 | Atmosphere and mass ledger, including finite/physical inertia checks | b433e74 |
| 2.5 | Immutable snapshot, reconstructed YAML and input readiness | fb7d6ce |
| 3.1 | Bounded ASCII/binary STL parser and synthetic cube fixtures | 5bc0108 |
| 3.2 | Topology diagnostics, tolerance record and stable component IDs | dd9ed5f |
| 3.3 | Explicit assembly roles and rotor/zone assignments | a068a5f |
| 3.4 | Immutable parent geometry and deterministic logged repair revisions | 50fdac8 |

Each task was tested first with a missing-module/interface failure, implemented,
then reviewed by a supplementary critic. Supplied expected values were retained.
Review findings fixed: nonphysical principal inertia, finite input overflow,
mutable nested snapshot values, nested missing boundary/zone inputs, invalid
volume bounds, missed unknown record keys, and cyclic component-ID ties after
quantization. The runtime YAML is included in the built wheel, verified by ZIP
inspection. No new dependencies were added in WP02 or WP03.

Latest whole non-backend suite:

```text
$ .venv/bin/python -m pytest -q -m 'not backend'
149 passed, 1 deselected, 1 warning in 0.77s
$ .venv/bin/ruff check .
All checks passed!
```

The one warning is the installed FastAPI/Starlette TestClient httpx deprecation.
The excluded backend fixture has separate local success evidence in
`backend_pin.md`; backend CI provisioning is still pending.

Tasks 2.3 and 2.4 have supplementary same-family review and independent algebraic
checks, but plan §1.5 still requires a different model family or a human engineer
before merge. They are not merged or independently certified.

Next task is 3.5: the import endpoint and interactive 3D viewer. The current
browser is a working navigation/health shell; it does not yet upload CAD,
assign roles through the browser, or run aircraft CFD. Server backend pin is
still unset unless explicitly configured; the separate audit pin does not
silently become application configuration.

Aircraft sizing and person-day estimates remain pending Task 1.4 Steps 6/7.
Companion customer YAML reconciliation remains pending Q10. Synthetic fixtures
are software evidence, not customer geometry or aircraft validation.
