# Prescribed tabulated DC energy to lumped thermal screening

`physimesh.drone.tabulated_electrothermal.evaluate_tabulated_electrothermal`
accepts evaluation `prescribed_tabulated_dc_electrothermal_experimental` and
returns schema `tabulated_electrothermal_v1`. This is forward one-way allocation
and temperature screening, with no thermal-dependent motor feedback or derating.

The exact root fields are `evaluation`, `energy_request`, `thermal_body`, and
`thermal_segments`. Supply the unchanged full V118 request as `energy_request`.
The thermal body has exactly `mass_kg`, `specific_heat_j_kg_k`,
`initial_temperature_k`, `lumped_biot_number`, and `property_source`. Positive
mass, heat capacity and initial temperature, finite Biot in [0, 0.1], a positive
normal derived capacity and a nonblank source are required. Scalar admission
uses actual thermal `_number`, including finite subnormal Biot declarations.
Each thermal segment has exactly `id`, `ambient_temperature_k` (>0), and
`conductance_w_k` (>=0). Its ID must match the energy segment at the same index;
there are 1–8 segments. Declarations retain their native JSON numeric types.

The full root is walked before copying, with only bounded builtin JSON accepted.
Full actual energy preflight checks all points, motors and the 65,536 aggregate
forward-annulus work budget; all thermal declarations are checked before any
model call. No dummy thermal request or fabricated child envelope is used.

Execution calls actual V118 energy once, immediately snapshots its full result,
and admits computed success through pure V120 with a required `None` return.
Every actual row's allocated `total_heat_w` and native `duration_s` then enter
one actual `lumped_thermal_screening` request containing all chronological
segments. Ambient and conductance come from the corresponding declarations.
Heat is neither total electrical power nor all motor loss, and auxiliary heat
is already allocated once. Actual thermal runs once; its full result is
immediately snapshotted and admitted through pure V119 returning `None`.
Neither guard reruns a model or the actual thermal integrator.

Each thermal row's `heat_input_j` must equal its energy row's
`energy_j.total_allocated_heat` exactly. Total heat is independently cross-bound
with relative tolerance `64 * sys.float_info.epsilon` and absolute tolerance
zero: V118 sums sequentially, whereas thermal uses `math.fsum`. This allowance
addresses summation rounding only and establishes no physical accuracy.

Successful `outputs` contains each full unchanged actual result once under
`energy` and `thermal`, preserving nested sources and limitations. Output units
are `energy: {outputs: <actual energy units>}` and
`thermal: {outputs: <actual thermal units>}`. Two stages retain the full energy
request and full injected thermal request with request/full-result SHA256
digests. There are exactly 2N scalar transfers, heat W then duration s for each
segment, binding the full energy producer result to the full thermal consumer
request. Ambient and conductance bind through the full root and thermal request
digests. No hash fields are added to the actual thermal result.

`energy_result_count` and `thermal_result_count` become 1 only after their full
success guards pass. Point/inverse/forward/motor counts are copied only after
V120 passes. Counts describe guarded contracts, never attempts or proof that a
model was not called. A thrown exception, noncomputed status, malformed snapshot
or failed guard at either child boundary yields atomic `EXECUTION_FAILED` with
`ENERGY_BOUNDARY_FAILED` or `THERMAL_BOUNDARY_FAILED`. Noncomputed children never
enter success-only guards. Raw unvalidated statuses and reasons are discarded;
the response makes no causal or numerical-failure claim. Outputs, units, stages
and transfers are cleared; earlier guarded counts survive. Injection/arithmetic
or provenance failure outside a child boundary uses the execution reason.
Thermal count remains 1 if later cross-binding or provenance fails.

Invalid preflight is `MODEL_INAPPLICABLE`; unsupported evaluation is
`SOLVER_UNSUPPORTED`. Both have zero counts and null hashes. Unexpected ordinary
snapshot/preflight exceptions give `EXECUTION_FAILED` with zero counts and null
hashes. Subsequent request/full-response hashes use the accepted JSON encoding;
the response digest omits itself. Digest infrastructure failure may leave a
null hash. Ordinary exceptions are sanitized; `BaseException` propagates.

| JSON boundary | Nodes including keys | Depth | Container items |
| --- | ---: | ---: | ---: |
| Root input | 1,048,576 | 24 | 256 |
| Root output | 8,388,608 | 36 | 2,048 |
| Energy input | 524,288 | 20 | 256 |
| Energy output | 4,194,304 | 32 | 2,048 |
| Thermal input | 8,192 | 8 | 2,048 |
| Thermal output | 32,768 | 10 | 2,048 |

All boundaries use root depth 1, strings up to 2,000 characters, integers up to
1,023 bits, finite floats and valid UTF-8. The catalog returns fresh code-owned
metadata without model execution. Diagnostics are complete only on success.
Declared motor limit exceedance remains computed with the nested flag false.
Physical validation, numerical qualification and runtime identity remain
`NOT_ESTABLISHED`; aircraft status and feasibility remain null. No measured
parameters, physical temperatures, hotspots, Biot validation, ESC, battery SOC,
reserve, climb, trim, control, stability, real-flight mission, API, publication
or novelty qualification is established.

## Duration representation and focused coverage

Native integer durations, including values above `2**53`, remain unchanged in
the energy result and the injected thermal request. The actual thermal model
converts durations to binary64 floats; its reported duration can therefore be
rounded. The bridge does not claim exact integer time representation in thermal
outputs. With an admissible body capacity and trajectory, per-row heat joules
still bind exactly to the actual energy row. The total comparison permits only
the documented 64-epsilon relative summation rounding, with zero absolute
tolerance.

Focused actual-model tests cover conducting and adiabatic chronology, eight
segments with small-exponent conduction and ambient cooling, zero-heat
equilibrium, allocation fractions zero and one, auxiliary heat exactly once,
declared-limit exceedance, subnormal Biot admission, and large integer duration.
Independent direct child captures compare the full retained JSON bytes and
digests. Spies check one energy call, one thermal call, N actual integrator calls
and unchanged nested model counts. Separate boundary tests check status
discarding before success guards, exact `None` guard returns, atomic failures,
retained guarded counts, ordinary exceptions and `BaseException` propagation.
None of these counts establishes causality, physical qualification or proof
that a model was not called.

Synthetic helper-only resource tests exercise all six JSON scopes at their exact
node, depth, container, string and integer-bit limits and one beyond. They are
resource-admission evidence, not actual-model qualification. Other tests check
strict UTF-8, cycles, nonfinite numbers, rejection of foreign subclasses before
copy hooks, full walk/copy/walk/guard ordering, detached child snapshots,
atomic output-resource failure and fresh catalog metadata without model calls.
