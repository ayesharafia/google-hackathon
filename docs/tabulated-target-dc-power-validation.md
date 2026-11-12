# Pure V116 target DC power result validation

`physimesh.drone.tabulated_target_dc_power_validation` exposes
`validate_tabulated_target_dc_power_result(actual, request)`. It returns `None`
for a consistent retained actual V116 power contract and raises `ValueError`
for a contract violation. Unexpected pure dependency exceptions propagate,
including `RuntimeError` and `BaseException`. This boundary is a prerequisite
for future chronological energy/thermal composition; it implements no energy
integration or temperature evolution.

```python
from copy import deepcopy
from physimesh.drone.tabulated_target_dc_power import evaluate_tabulated_target_dc_power
from physimesh.drone.tabulated_target_dc_power_validation import (
    validate_tabulated_target_dc_power_result,
)
from tests.drone.test_tabulated_target_dc_power import request

supplied = request()
actual = evaluate_tabulated_target_dc_power(supplied)  # once, before the pure guard
assert actual["status"] == "COMPUTED_EXPERIMENTAL"
before = deepcopy((actual, supplied))  # test-side preservation check only
assert validate_tabulated_target_dc_power_result(actual, supplied) is None
assert (actual, supplied) == before
```

Run the example from the repository root with `PYTHONPATH=src`.

## Admission and bounded JSON

A private import-time V116 catalog snapshot supplies trusted metadata and units.
It is independent of mutable actual results and public catalog returns. No
runtime catalog, model evaluator, DC compute, copy/conversion hook, dataclass
reconstruction, or mutation is used by validation. Expected scalar and input
mapping checks never fabricate a valid component result envelope.

The accepted strict builtin JSON walker bounds the entire actual result and
request before hashing, equality, hooks, or structural preflight. It rejects
foreign types and subclasses, cycles beyond the depth bound, nonfinite floats,
invalid UTF-8, integers exceeding 1023 bits and strings exceeding 2000 characters.
Aliased occurrences each consume their full node budget, as in serialized JSON.
The root depth is one; keys count as nodes. Input containers allow 256 items;
output containers allow 2048 items.

| Scope | Maximum nodes including keys | Maximum depth |
| --- | ---: | ---: |
| Outer request | 131072 | 16 |
| Outer result | 1048576 | 28 |
| Assembly request | 65536 | 14 |
| Assembly result | 524288 | 24 |
| Motor request | 4096 | 10 |
| Motor result | 8192 | 12 |

The actual V116 pure structural preflight checks the entire request, including
all motor declarations, without fabricating an operating point. Its underlying
assembly preflight enforces ordered rotor IDs, one through eight rotors, all
declared budgets and `SUM(max_evaluations * annuli) <= 32768`.

After bounded exact-root/type checks, an unsupported evaluation string admits
only `SOLVER_UNSUPPORTED`, its exact reason, zero counts and null digests.
Ordinary `ValueError` or `OverflowError` during preflight admits only
`MODEL_INAPPLICABLE`, the invalid-request reason, zero counts and null digests.
Unexpected preflight exceptions propagate rather than admitting V116 snapshot
fault responses.

The inherited V115/V109 narrow deterministic admission excludes request-null
snapshot/hash infrastructure fault envelopes. An admitted request always needs
its canonical actual request hash. A snapshot reason or request-null hash fault
cannot satisfy this boundary merely because the evaluator can emit it.
This preserves the existing infrastructure admission boundary.

## Full retained success contracts

Root fields, builtin types, markers, null qualification fields, limits,
limitations, status/reasons, diagnostics and unit scopes are exact. Request
digests use the accepted canonical JSON hash. The outer result hash covers
the full actual response, omitting only its own `evaluation_sha256` field.
`MODEL_INAPPLICABLE` has a null outer result hash, including an assembly refusal
with a nonnull request hash.

Success has exactly `outputs.assembly` and `outputs.power`. The unchanged full
actual assembly occurs once; the V115 pure guard must return `None` on that full
actual assembly and the caller's full assembly request. It must be computed.
Root inverse/forward counts equal the guarded assembly counts. Motor count,
ordered row count and request motor count agree.

Each closed motor row holds its ID, full actual motor request, full actual motor
result, allocated heat and unallocated loss. The operating point uses the actual
selected forward request's angular speed and the actual selected forward result's
unsigned torque, including for opposite rotor spin. It never substitutes the
requested thrust target. Parameters and declared limits preserve their original
builtin integer/float types. Motor request and result receive independent bounded
walks before the actual V116 pure full-motor guard, which must return `None`.
The actual DC motor result has no `evaluation_sha256`; adding one is rejected.

The shaft cross-binding uses only `math.isclose(rel_tol=1e-12, abs_tol=1e-12)`
to allow the accepted multiply-order difference. It is a numerical comparison,
not a physical tolerance. Motor arithmetic, exact native scalar types, inclusive
declared limit checks and the accepted operation order come from V116's pure
guard, without running `dc_motor._compute` or any evaluator.

Allocated heat is `actual_total_loss * declared_fraction`; unallocated loss is
the accepted checked difference. Auxiliary electrical demand is included once;
auxiliary heat is its declared power times heat fraction. Totals use the accepted
DC power sum over actual rows. The overall limit flag is a builtin boolean and
matches all actual motor limit statuses. Declared exceedance remains computed.
Shaft power is not allocated heat.

Output units cover assembly outputs only at `assembly.outputs`, and motor outputs
only at `power.motors.actual_motor_result.outputs`. Motor request units include
all parameters, limits, operating-point values and source declarations exactly.
Stages are ordered `assembly` then `motor:<id>`, with actual input/request digests
and full actual result digests. Two ordered transfers per rotor bind angular
speed then torque, exact producer/consumer paths, values, units, the full assembly
producer digest and actual motor request consumer digest. Full results are not
duplicated into stages or transfers.

V115 and V109 continue to content-verify selected retained forward results.
Intermediate trace digests remain **FORMAT-ONLY producer-reported provenance**:
absent intermediate payloads cannot be content-verified. Full-result hashes bind
retained JSON snapshots; they establish neither runtime identity nor execution
attestation. This is contract arithmetic, not an independent physical oracle.

## Atomic failure envelopes and necessary bounds

All failures have outputs/units `{}`, stages/transfers `[]`, and diagnostics
exactly false. Reasons are exact private-catalog reasons. All counts are builtin
integers. No discarded assembly/motor payload is fabricated to validate failure.

Let `N` be the number of requested rotors, `n` the root assembly inverse count,
`f` the forward count, `m` the motor count, and `b[i]` the ordered inverse budgets.
Always `0 <= n <= N`, `0 <= f <= SUM(b[:n])`, and `0 <= m <= N`.

For an actual noncomputed assembly reason, `m == 0` and the V115 necessary
prefix bounds apply. For `n > 0`, let `p = 2*(n-1)`, `P = SUM(b[:n-1])`,
and `L = b[n-1]`:

| Assembly status | Additional necessary bounds |
| --- | --- |
| `TARGET_NOT_BRACKETED` | `n >= 1`, `p+2 <= f <= P+2` |
| `ITERATION_LIMIT` | `n >= 1`, `p+L <= f <= P+L` |
| `NUMERICAL_LIMIT` | `n >= 1`, `L >= 3`, `p+2 <= f <= P+L-1` |
| `MODEL_INAPPLICABLE` | `n >= 1`, `p+1 <= f`; null result hash |
| `EXECUTION_FAILED` | `n == 0` requires `f == 0`; otherwise `p <= f` |

A counted final execution-failed inverse can have zero forward evaluations;
earlier computed inverses require at least two each. Zero inverse results with
an assembly reason admit only `EXECUTION_FAILED`, never a fabricated early air
`MODEL_INAPPLICABLE`. Invalid air requests fail V116 preflight; unexpected runtime
air failures yield assembly execution failure with zero counts.

For V116's own execution reason, either all three counts are zero (the full
assembly guard never supplied trusted counts), or `n == N`,
`2*N <= f <= SUM(b)` and `0 <= m <= N`. Partial assembly prefixes are excluded
for this reason because trusted assembly counts are assigned only after the full
V115 guard. A discarded noncomputed assembly rejected by that guard also leaves
zero counts. Motor failure preserves the previous guarded motor count; allocation
failure can occur after the last motor guard and therefore retain `m == N`.

These are **necessary bounds only**, not proof of calls, fault causation or a
specific history. A deliberately rehashed failure inside the bounds may validate.
No retained payload exists to verify its full execution content.

## Focused verification

The new tests capture actual V116 results before blocking air, atmosphere,
assembly, inverse, forward, core, DC compute/evaluate and runtime catalog calls,
including catalog aliases in V115/V109 modules. They check `None` and unchanged
actual/request content and native scalar types. Success fixtures cover two rotors,
ideal integer motor parameters with limit exceedance, and eight rotors with
512 annuli, 256 stations and declared total work 32768.

Actual domain/status and injected execution-fault captures are distinguished from
synthetic envelope-only count grids. A genuine numerical-limit fixture uses
adjacent speeds starting at 150 rad/s, an independently observed strict interior
endpoint-thrust target and the minimum normal tolerance, all before model blocking.
Rehashed mutations repair motor/result/stage/transfer hashes where appropriate
to exercise full content arithmetic and bindings. Tests also cover resource
boundaries, foreign hooks, child budgets, unexpected dependency exceptions and
the intentional intermediate-trace provenance limit.

No energy/temperature integration, physical qualification, ESC/battery model,
attainability, trim, control, stability, safety, aircraft feasibility, API, mission,
publication, 80 percent accuracy or novelty upgrade follows from this validator.
