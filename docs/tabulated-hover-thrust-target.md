# Bounded tabulated hover thrust target

This experimental inverse searches for angular speed at a caller-specified
thrust of the accepted tabulated-geometry hover model. Every trial executes
`tabulated_hover_bemt_request.evaluate_tabulated_hover_bemt` once. It solves a
bounded model-output target, not physical aircraft trim. A satisfied residual
does not establish physical accuracy, safety, numerical qualification, runtime
identity or aircraft feasibility.

The standalone entry points are
`physimesh.drone.tabulated_hover_thrust_target.evaluate_tabulated_hover_thrust_target`
and `tabulated_hover_thrust_target_catalog`. The catalog returns fresh nested
metadata, required fields, units, bounds, statuses and hash contracts.

## Explicit request

The root must be an exact builtin dictionary with exactly these six fields:

```json
{
  "evaluation": "tabulated_geometry_hover_thrust_target_experimental",
  "rotor_template": {
    "evaluation": "tabulated_geometry_hover_experimental",
    "radius_m": 1.0,
    "density_kg_m3": 1.225,
    "blade_count": 2,
    "root_cutout_m": 0.25,
    "annuli": 24,
    "lift_curve_slope_per_rad": 5.7,
    "profile_drag_coefficient": 0.01,
    "stations": [
      {"radius_m": 0.0, "chord_m": 0.04, "blade_angle_rad": 0.10},
      {"radius_m": 0.625, "chord_m": 0.08, "blade_angle_rad": 0.04},
      {"radius_m": 1.0, "chord_m": 0.02, "blade_angle_rad": 0.08}
    ],
    "geometry_source": "synthetic numerical fixture, revision 1; true SI radius",
    "geometry_kind": "synthetic",
    "uncertainty_status": "unknown; numerical verification only"
  },
  "target_thrust_n": 31.353032182835474,
  "angular_speed_bracket_rad_s": [50.0, 150.0],
  "absolute_thrust_tolerance_n": 1e-10,
  "max_evaluations": 32
}
```

There are no defaults. `rotor_template` has exactly the accepted forward
request fields except `angular_speed_rad_s`, which must be absent. Its
`evaluation` must identify the actual accepted child evaluation as shown.
Density is explicit caller input and remains unchanged throughout the search.
Each actual trial speed is inserted into a separate copied template.

| Root field | Unit | Requirement |
| --- | --- | --- |
| `evaluation` | label | Exact evaluation string above |
| `rotor_template` | field-specific | Exact template, with no angular speed |
| `target_thrust_n` | N | Positive finite normal builtin int/float |
| `angular_speed_bracket_rad_s` | rad/s per element | Exact builtin list of two positive finite normal numbers, lower < upper |
| `absolute_thrust_tolerance_n` | N | Positive finite normal builtin int/float, strictly less than target |
| `max_evaluations` | 1 | Builtin int, 2 through 64 inclusive |

Bool is forbidden for numeric controls and all physical numeric fields. Normal
positive controls convert to finite binary64 values at least
`sys.float_info.min`; zero, subnormal controls, infinity and NaN are rejected.
Physical template fields must have builtin numeric types, but their geometric
and physical numerical domain is decided by the actual forward core.

| Template field | Unit | Shape or domain |
| --- | --- | --- |
| `evaluation` | label | `tabulated_geometry_hover_experimental` |
| `radius_m` | m | Positive radius, forward-core domain |
| `density_kg_m3` | kg/m^3 | Explicit positive density, forward-core domain |
| `blade_count` | 1 | Builtin int, 1 through 32 |
| `root_cutout_m` | m | Strictly between zero and radius, forward-core domain |
| `annuli` | 1 | Builtin int, 1 through 512 |
| `lift_curve_slope_per_rad` | 1/rad | Positive attached-linear constant, forward-core domain |
| `profile_drag_coefficient` | 1 | Nonnegative constant, forward-core domain |
| `stations` | field-specific | Exact builtin list of 2 through 256 exact station dictionaries |
| `geometry_source` | text | Nonblank builtin string |
| `geometry_kind` | label | `measured`, `digitized_measurement`, `as_designed` or `synthetic` |
| `uncertainty_status` | text | Nonblank builtin string; unknown remains unknown |

Each station has exactly `radius_m` in m, `chord_m` in m and `blade_angle_rad`
in rad, all builtin int/float without bool. The actual core owns strict radial
ordering, coverage from cutout through tip without extrapolation, positive
chord, nonnegative blade angle and all finite-normal physical arithmetic.
Interpolation is the accepted forward model's piecewise linear chord and
blade angle at physical midpoint annuli. Source classification and uncertainty
text are unverified caller assertions; no source is fetched or verified.

## Bounded input and work

Before any copying, the outer request undergoes a strict builtin JSON walk.
Only exact dict/list/str/int/float/bool/null values are allowed. Subclasses,
tuples and foreign conversion or copying hooks are rejected. Counts include
each value and dictionary key; aliases count separately at every occurrence.
Cycles exceed the depth bound. The copied snapshot is walked again before
preflight and hashing.

| Input bound | Value |
| --- | --- |
| Root depth | 1 |
| Maximum depth | 11 |
| Maximum nodes, including keys | 16384 |
| Maximum items in any container | 256 |
| Maximum characters in a string | 2000 |
| String encoding | Strict valid UTF-8 |
| Maximum integer bit length | 1023 |
| Float requirement | Finite |

Exact shapes, numeric types, declarations, source classification, control
domains and work counts are checked before any actual forward calls.
`max_evaluations * annuli <= 32768` is required, in addition to the individual
limits of 64 calls and 512 annuli. The maximum supported combination is 64
calls, 512 annuli, 256 stations and 32 blades. No dummy speed is used for
preflight, and no geometric or physical dry-run evaluation occurs.

Each complete injected child request receives the independent accepted V105
input JSON walk before its request hashing and actual call. That child limit
remains depth 10, 8192 nodes including keys, 256 items per container, 2000
characters per string, 1023 integer bits and strict UTF-8 with finite floats.
The accepted child's independent output budget also remains unchanged: depth
10, 32768 nodes and 2048 items per container, with the same string, integer
and float restrictions.

## Actual calls and bounded search

1. Evaluate the actual lower endpoint, then the actual upper endpoint. Both
   are called even when the lower endpoint already meets tolerance. A first
   actual physical refusal or exception stops immediately and atomically.
2. Require observed upper thrust to be strictly greater than observed lower
   thrust. The sole equality exception is all-zero station blade angles with
   both actual endpoint thrusts equal to zero. This is an observed ordering
   check, not a physical monotonicity claim.
3. Select the earliest endpoint in call order whose absolute actual residual
   meets tolerance. The trace still records both actual endpoints.
4. Otherwise, refuse with `TARGET_NOT_BRACKETED` if the target is outside the
   observed endpoint interval. An outside target within caller tolerance of
   an endpoint has already been accepted by the preceding step.
5. With a strict target bracket, evaluate the actual midpoint
   `lo + (hi - lo) / 2`. Require a finite, representable, strict interior
   midpoint before calling the child. Its actual thrust must lie in the
   closed interval of the current endpoint thrusts. This check adds no
   roundoff allowance or hidden thrust tolerance.
6. Stop on `abs(actual_thrust_n - target_thrust_n) <= absolute_thrust_tolerance_n`.
   Otherwise use the actual signed residual to replace the corresponding
   endpoint, narrowing the speed bracket while retaining a strict target
   bracket.

There is no analytical angular-speed shortcut, surrogate, cached fake trial,
hidden bracket expansion or retry beyond the caller's call budget. Every
completed trial is a separate actual forward evaluation. Exhausting the budget
before success gives `ITERATION_LIMIT`. If there is no finite representable
strict interior midpoint, the result is `NUMERICAL_LIMIT` without another call.
For example, the actual fixture above has a positive thrust gap between speed
`50.0` and `math.nextafter(50.0, math.inf)`. A strictly interior thrust target
and `sys.float_info.min` tolerance give `NUMERICAL_LIMIT` after the two actual
endpoint calls.

Each actual response passes the unchanged accepted V106
`reference_air_tabulated_hover._validate_child(actual, injected)` guard. It
validates the full actual JSON envelope, exact fields and builtin types,
markers, units, limitations, limits, status, request and evaluation hashes,
and the actual output slice bound to the original injected request. It does
not run a second forward evaluation. `True` means a computed response passed
that contract; `False` means a legitimate actual physical or numerical domain
refusal. A malformed response or failed binding gives `EXECUTION_FAILED`.
No reference-air evaluation runs in this feature.

## Response, units and snapshots

Every response contains `evaluation`, `schema_version`, `status`,
`evidence_level`, `physical_validation`, `numerical_qualification`,
`runtime_identity`, `aircraft_status`, `feasibility`, `diagnostics_complete`,
`reasons`, `limitations`, `limits`, `request_sha256`, `evaluation_sha256`,
`evaluation_count`, `outputs`, `output_units` and `trace`.

Evidence is always `unverified`; physical validation, numerical qualification
and runtime identity are always `NOT_ESTABLISHED`. Aircraft status and
feasibility are null. `evaluation_count` is always a builtin integer: zero
before request acceptance, otherwise the number of actual child calls
attempted, including calls that refuse or raise. It never exceeds the accepted
`max_evaluations`. Its unit is 1. This scalar reports work even when no partial
results can be exposed.

Only `COMPUTED_EXPERIMENTAL` has `diagnostics_complete: true`, empty reasons,
the selected full actual forward response and a populated scalar trace.

| Success output | Unit or scope |
| --- | --- |
| `angular_speed_rad_s` | rad/s |
| `target_thrust_n` | N |
| `achieved_thrust_n` | N |
| `thrust_residual_n` | N; actual achieved thrust minus target |
| `absolute_thrust_tolerance_n` | N |
| `evaluations` | 1; equals root `evaluation_count` |
| `actual_forward_request` | Separate complete forward request unit catalog |
| `actual_forward_result` | Actual full child response; its unit catalog applies only to its nested `outputs` |

The full selected forward result appears once. Its data, including its
`evaluation_sha256`, are unchanged; it is retained by deepcopy rather than
semantic reconstruction. The forward request unit catalog is separate from
the forward result unit catalog. Result units do not describe the child
response envelope or its hashes, limits, markers and declarations.

Each successful trace entry contains only these five scalar fields, in actual
call order:

| Trace field | Unit or meaning |
| --- | --- |
| `angular_speed_rad_s` | rad/s; actual trial speed |
| `thrust_n` | N; actual returned thrust |
| `thrust_residual_n` | N; actual returned thrust minus target |
| `request_sha256` | Hash of the complete actual injected request |
| `full_actual_result_sha256` | Hash of the full actual child response, including its own evaluation hash |

The first two entries are lower and upper endpoints. Later entries are actual
bisection calls. No station arrays, full requests or full responses are
repeated in the trace. Trace length, success `evaluations`, root
`evaluation_count` and actual call count agree.

Caller snapshots and each injected request are distinct from the objects
passed to the child. Every validated actual child response is copied
immediately, protecting earlier trials when a child retains, mutates or reuses
its returned object during later calls. The selected response is detached
from the child's retained object. This differs from the original V106 child
object alias boundary while preserving the actual JSON data unchanged.
These are private JSON snapshots, not immutable objects; callers can mutate
their own returned result, which will invalidate previously recorded hashes.

The outer output budget is independent: depth 16 with root depth 1, 65536
nodes including keys and 2048 items per container. Strings remain limited to
2000 characters and strict UTF-8, integers to 1023 bits, and floats to finite
values. This accommodates the maximum selected forward result once, its
actual request once and up to 64 scalar trace entries.

## Atomic statuses and nullable hashes

Every failure has empty `outputs`, empty `output_units`, empty `trace` and
`diagnostics_complete: false`. Even validated earlier trials are discarded
when a later endpoint or midpoint fails. Only the scalar work count remains.
Reasons are fixed contract text; ordinary exception messages are not exposed.

| Status or condition | Actual calls | Request hash | Evaluation hash |
| --- | --- | --- | --- |
| `COMPUTED_EXPERIMENTAL` | 2 through budget | Present | Present |
| `MODEL_INAPPLICABLE`, invalid preflight | 0 | null | null |
| `SOLVER_UNSUPPORTED`, other outer evaluation string | 0 | null | null |
| `EXECUTION_FAILED`, snapshot failure before acceptance | 0 | null | null |
| `MODEL_INAPPLICABLE`, legitimate actual forward domain refusal | Calls attempted through refusal | Present | null |
| `TARGET_NOT_BRACKETED` | 2 | Present | Present |
| `ITERATION_LIMIT` | Accepted budget | Present | Present |
| `NUMERICAL_LIMIT` | Calls made before stagnation | Present | Present |
| `EXECUTION_FAILED`, after accepted request hashing | Calls attempted through failure | Present | Present |
| Catalog `RESEARCH_ONLY` | 0 | null | null |

Unsupported evaluation requires an otherwise strict JSON exact root and a
builtin string evaluation. Invalid JSON or root shape takes preflight failure
precedence. Actual observed ordering failures and invalid actual envelopes
are execution failures. Ordinary `Exception` is caught atomically;
`BaseException`, including `KeyboardInterrupt` and `SystemExit`, propagates.

`request_sha256` binds the accepted copied outer request before any actual
call. Once that hash exists, every outcome except `MODEL_INAPPLICABLE` also
gets `evaluation_sha256`, computed from the entire outer response with only
its own `evaluation_sha256` field omitted. A legitimate actual domain refusal
retains the outer request hash but has no evaluation hash. Null means no digest
is available; it is not a digest.

All hashes use the accepted provenance encoding: SHA256 of UTF-8 JSON with
sorted keys, compact separators, `ensure_ascii=False` and `allow_nan=False`.
The full actual result trace hash includes the child's evaluation hash;
the child's evaluation hash itself omits only its own hash field according
to the accepted child contract. These hashes bind data, not code or runtime
identity, evidence quality or physical accuracy.

## Interpretation limits

The residual is finite binary floating-point subtraction of model thrust and
the requested target. The caller's absolute tolerance is a numerical stopping
rule, not a bound on measurement error, physical thrust error, safety or
physical trim. No additional residual tolerance is inferred. Satisfying it or
observing component convergence establishes no physical accuracy, numerical
qualification or system feasibility.

Density affects the accepted forward load scales while lift-curve slope and
profile drag remain caller-specified fixed coefficients. Explicit density is
not weather. Reynolds-number and Mach-number effects are absent, with no
Reynolds/Mach feedback, airfoil polars, stall, compressibility correction,
tip/root loss model, swirl or rotor interaction. There are no motor limits or
electrical-efficiency constraints. Shaft power remains mechanical power.

This feature adds no API, graph, assembly, aircraft trim or mission integration
and performs no air-property evaluation. It establishes no additional physical,
numerical or runtime qualification, novelty claim or percentage accuracy claim.
The tests check bounded behavior, actual data binding and failure safety of the
software contract; they do not establish product-level physical performance.
