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

## Test evidence

Scaffold test first failed with `ModuleNotFoundError: No module named 'physimesh'`.
Core tests first failed with three missing-module collection errors. Both
passed after implementing their respective tasks.

Latest project unit command:
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

Task 1.4 is incomplete: hardened blockMesh cannot read the copied case's
controlDict. See backend_pin.md. Under plan §1.4 the capability failure stops
progress. Task 1.5 and WP02 onwards have not started.

No person-days estimate is supplied: [M§28] and Task 1.4 Step 7 require the
backend measurements plus first real STL and rotor-data review. Actual geometry
and rotor data remain required external inputs (Q03, Q04). Client greenfield
sign-off (Q01) remains separate from the user's implementation authorization.

This is a software progress record, not Release A acceptance or aircraft
validation. [M§2, M§27]
