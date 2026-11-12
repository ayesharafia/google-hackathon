# Pure prescribed target assembly result validation

`physimesh.drone.tabulated_thrust_target_assembly_validation`
provides `validate_tabulated_thrust_target_assembly_result(actual, request)`.
It returns `None` for a consistent retained V114 contract and raises
`ValueError` for a contract violation. Unexpected exceptions from pure
dependencies, including `RuntimeError` and `BaseException`, propagate.

This is a local result boundary for downstream actual-component composition.
It adds no physical model, evaluator, API route, registry entry or publication
behavior. Accepted implementation files remain unchanged.

Run this smoke example from the repository root with `PYTHONPATH=src` and
Python. The request comes from the accepted
V114 test fixture; the evaluator runs once before the pure guard. The copies
are test-side mutation checks, outside validation.

```python
from copy import deepcopy

from physimesh.drone.tabulated_thrust_target_assembly import (
    evaluate_tabulated_thrust_target_assembly,
)
from physimesh.drone.tabulated_thrust_target_assembly_validation import (
    validate_tabulated_thrust_target_assembly_result,
)
from tests.drone.test_tabulated_thrust_target_assembly import request

supplied = request()
actual = evaluate_tabulated_thrust_target_assembly(supplied)
assert actual["status"] == "COMPUTED_EXPERIMENTAL"
before = deepcopy((actual, supplied))
assert validate_tabulated_thrust_target_assembly_result(actual, supplied) is None
assert (actual, supplied) == before
print("Captured actual V114 result validated; actual and request unchanged.")
```

## Admission and resources

The validator walks actual output and request using the accepted strict builtin
JSON walker before hashing, equality checks or structural preflight. It never
copies caller data, invokes copy or conversion hooks, mutates children, fabricates
dataclasses, or reconstructs valid component response envelopes. Aliased JSON
occurrences each consume their full node budget; cycles exceed the depth bound.
Foreign containers and scalar subclasses, nonfinite floats, invalid UTF-8,
oversized strings, integers and containers are rejected by that walker.

The trusted V114 catalog is a private import-time snapshot. Validation makes no
runtime catalog calls and derives no trusted metadata from the mutable result.
Public catalog mutations cannot change that snapshot.

| Scope | Nodes including keys | Maximum depth |
| --- | ---: | ---: |
| Outer input | 65,536 | 14 |
| Outer output | 524,288 | 24 |
| Inverse input | 16,384 | 11 |
| Inverse output | 65,536 | 16 |
| Selected forward input | 8,192 | 10 |
| Selected forward output | 32,768 | 10 |

Other walker limits are inherited exactly from the accepted catalogs. The actual
V114 structural preflight admits all rotor declarations before any output
arithmetic. It uses no fabricated air, density or angular speed. Declared work
must satisfy `SUM(max_evaluations * annuli) <= 32768`, with one through eight
rotors and the accepted per-rotor controls and geometry declaration limits.

A bounded exact root with an unsupported evaluation string admits only
`SOLVER_UNSUPPORTED`, zero counts and null request/result digests. Ordinary
`ValueError` or `OverflowError` during request admission admits only
`MODEL_INAPPLICABLE`, the invalid-request reason, zero counts and null digests.
Unsupported dispatch precedes structural preflight after the JSON/root checks.

The boundary deliberately excludes infrastructure snapshot/hash fault envelopes
outside deterministic admission, following the narrow V109 approach. An admitted
request always requires its actual canonical request digest, including on
execution failure. A request-null snapshot or hash fault does not satisfy that
contract. No inference of execution or fault causation is made.

## Retained success content

Root fields, builtin types, static markers, null qualification fields,
limitations, limits, reasons and nested unit scopes match the captured catalog
exactly. Root result digests cover the full actual response omitting only
`evaluation_sha256`, using accepted sorted compact UTF-8 JSON canonicalization.
Domain refusal has a null result digest.

Success retains exactly one raw air mapping, ordered rotor rows, gravity force,
net force and net moment. Raw air and its state have closed key sets. Every
state value, marker and transport value is checked directly against the request
and accepted V106 hydrostatic, viscosity, sound and gravity arithmetic. Constants,
layer boundaries, geometric/geopotential conventions and floating operation order
match the accepted guard. No air-properties or atmosphere evaluator is called.

Each row retains exactly one full actual inverse and its actual injected request.
Injection adds only the validated density to the caller's target template. The
accepted pure V109 guard must return `None` on that unchanged actual pair, and the
inverse must be `COMPUTED_EXPERIMENTAL`. V109 independently bounds inverse and
selected forward payloads, checks the selected full forward content and digest,
and checks trace arithmetic without a second model evaluation. Counts equal the
ordered row count and sum of guarded inverse evaluation counts.

V112 signed load helpers consume the actual selected full forward outputs.
They preserve axis, spin, center-of-gravity signs and floating operation order.
Gravity is `(mass * actual_gravity) * direction` at the CG. Nets use componentwise
`math.fsum` through the accepted signed helper; finite-normal arithmetic and exact
zero cancellation retain their accepted behavior.
This checks arithmetic on actual mappings in the same binary floating operation
order as the accepted code; it is not an independent physical oracle.

Stages are exactly `air` followed by `rotor:<id>`, including `rotor:air` when that
is the declared ID. Inputs and both stage digests bind the actual retained
payloads. Density-only transfers bind the full raw-air producer digest and the
actual injected consumer request digest. Nested unit scopes cover the full raw
air, inverse outputs, and selected forward outputs exactly.

Intermediate trace full-result digests remain **FORMAT-ONLY producer-reported
provenance**: absent intermediate payloads cannot be content-verified. The
selected full forward digest is content-verified. No intermediate envelope is
invented to fill that gap.

## Atomic failures and necessary prefix bounds

Every failure has empty outputs and units, empty stages and transfers, and
`diagnostics_complete` exactly false. Reasons follow the exact admitted V114
matrix. Counts are builtin integers. Let `n` be the guarded inverse count,
`b[i]` the ordered request budgets, `P = SUM(b[:n-1])`, `L = b[n-1]`, and
`p = 2 * (n-1)`. Always `0 <= n <= number_of_rotors` and
`0 <= forward_count <= SUM(b[:n])`.

| Admitted failure | Additional necessary forward-count bounds |
| --- | --- |
| `TARGET_NOT_BRACKETED` | `n >= 1`, `p + 2 <= count <= P + 2` |
| `ITERATION_LIMIT` | `n >= 1`, `p + L <= count <= P + L` |
| `NUMERICAL_LIMIT` | `n >= 1`, `L >= 3`, `p + 2 <= count <= P + L - 1` |
| `MODEL_INAPPLICABLE` | `n >= 1`, `count >= p + 1`; null result digest |
| `EXECUTION_FAILED` | `n == 0` requires count zero; otherwise `count >= p` |

Execution failure permits a guarded last inverse with zero forward evaluations;
previous computed inverses each require at least two. A later invalid child
contributes no count, preserving only the already guarded prefix. Failure after
load arithmetic can also retain guarded counts. The payload-free outer failure
cannot distinguish those histories or recover individual actual counts.

These are necessary envelope bounds, **not execution attestation**. A rehashed
failure count inside the bounds may validate without proving that those calls
occurred, that the stated cause occurred, or that each declared budget was used.
No empirical threshold or inferred failure history is used.

## Focused verification

Tests capture actual V114 results before blocking air, atmosphere, inverse,
forward, core, assembly evaluators and runtime catalog functions. Captures cover
two-rotor success, eight rotors with 512 annuli and budget eight each (declared
work 32768), domain refusal, bracket refusal, iteration exhaustion, execution
faults, invalid children and load arithmetic faults. Actual and request data
remain unchanged on validation and rejection.

Rehashed adversarial cases cover raw air fields and types, coherent
pressure/density changes, signed loads and nets, nested units, static metadata,
row order, stage inputs, transfers, hashes, atomic failure counts and reasons.
Resource tests cover both inputs and outputs before hooks or hashing.
Unexpected pure dependency exceptions propagate. Intermediate digest substitution
is accepted only where the retained trace provides no full payload.

The new suite checks `NUMERICAL_LIMIT` prefix bounds as rehashed envelope-only
cases; it does not claim a newly captured V114 numerical-limit execution.
The inherited inverse tests contain actual adjacent-speed numerical-boundary
coverage. No physical or numerical qualification, runtime identity, trim,
attainability, interference, control, mission, feasibility, API, publication,
80 percent accuracy or novelty claim follows from validation.
