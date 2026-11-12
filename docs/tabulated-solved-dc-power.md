# Tabulated solved DC power (experimental)

`physimesh.drone.tabulated_solved_dc_power.evaluate_tabulated_solved_dc_power`
accepts exactly `evaluation`, `solve`, `motors`, and `auxiliary`. The evaluation
is `tabulated_solved_dc_power_experimental`; the response schema is
`tabulated_solved_dc_power_v1`. The fresh catalog closes fields, units, limits,
qualifications, and the dynamic response contract. There are no defaults.

`solve` is the full [V126 bounded tabulated static wrench request](tabulated-static-wrench-solve.md).
The ordered 1–8 motor declarations match `solve.assembly_template.rotors` IDs.
Motor parameters, declared limits, sources, heat fractions, and auxiliary fields
follow [V116](tabulated-target-dc-power.md); callers supply no motor operating
point. The whole request and all declarations undergo pure preflight before any
model call, including the V126 aggregate evaluation/annuli work bound.

The actual source chain is
`tabulated_solved_dc_power.py → tabulated_static_wrench_solve.py → tabulated_rotor_assembly.py → tabulated_hover_bemt_request.py`;
accepted operating points then pass to `dc_motor.py`. One actual V126 call is
immediately bounded and snapshotted. A pure full-success guard checks its static
metadata, units, hashes, counts, bounds, trace arithmetic, earliest strict minimum,
and outcome. Every trace request hash is recoverable from the template and speeds;
nonselected result digests are checked for format only because their payloads are
not retained. The selected full actual V112 request/result is cross-bound and
admitted with V126's pure assembly guard. No model is rerun by these guards.
SciPy TRF can adjust the first speed inside its bounds; the bridge does not claim
that the first trial equals the declared initial speeds.

When the guarded solve outcome is not `RESIDUAL_MET`, the root remains
`COMPUTED_EXPERIMENTAL`, retains the full solve once, and returns
`power_state="NOT_RUN_RESIDUAL_UNMET"`, `power=null`, and power units
`"not_applicable"`. No DC calls occur. Otherwise `power_state="COMPUTED"` and
power units describe the full power object. Each selected actual rotor row supplies
`actual_forward_request.angular_speed_rad_s` and unsigned
`actual_forward_result.outputs.shaft_torque_nm` directly to one actual DC call.
The full motor response passes the V116 pure guard; its actual absence of an
`evaluation_sha256` field is preserved. Shaft powers cross-bind with relative and
absolute tolerances of `1e-12`, allowing multiplication-order rounding only.

Outputs retain the full solve and each full motor request/result once. Stages
`solve` and `motor:<id>` contain actual inputs and request/full-result digests;
a rotor ID `solve` remains legal. Two scalar transfers per motor bind the full
solve digest to the actual DC request digest. Their producer paths are
`outputs.actual_assembly_result.outputs.rotors[i].actual_forward_request.angular_speed_rad_s`
and
`outputs.actual_assembly_result.outputs.rotors[i].actual_forward_result.outputs.shaft_torque_nm`.
These paths are relative to the retained full solve, not the outer bridge root.

Power includes the nine V116 watt totals and
`all_motors_within_declared_limits`. Allocated motor heat is the declared fraction
of actual motor loss; the remainder stays unallocated loss. Auxiliary electrical
power is added once, and auxiliary heat is its declared fraction once. Shaft
power is not heat. Exceeding caller-declared motor limits remains computed with
false limit flags; these declarations establish no attainable speed or authority.
Sources are unverified declarations, not fetched or qualified measurements.

Outer JSON budgets are 262144 nodes, depth 20, and 256 items per input container;
2097152 nodes, depth 32, and 2048 items per output container. Independent V126
budgets remain 262144/depth 16 for input and 1048576/depth 28 for output. Motor
budgets remain V116's 4096/depth 10 input and 8192/depth 12 output. Walks bound the
whole builtin JSON before copying, hashing, or equality; child returns are
immediately detached. Other scalar/string restrictions are exposed in the catalog.

Counts describe accepted guarded contracts: `solve_result_count` is 0–1,
`assembly_evaluation_count` and `forward_evaluation_count` copy guarded V126 trial
counts, and `motor_result_count` is 0–8 and increments only after full motor
admission. Zero accepted results does not establish zero attempted calls. Raw
noncomputed, malformed, or exceptional children yield only `SOLVE_BOUNDARY_FAILED`
or `MOTOR_BOUNDARY_FAILED`; their failure causes and counts are not trusted.
Other execution faults use `POWER_EXECUTION_FAILED`. Failures atomically clear
outputs, units, stages, and transfers while preserving prior guarded counts.
Ordinary exceptions are sanitized; `BaseException` propagates. Root sealing hashes
the entire response excluding its own evaluation hash, after bounded admission.

This local experimental bridge makes no physical control, stability, attainability,
thermal integration, mission, aircraft, global convergence, or global infeasibility
claim. It adds no battery or ESC feedback. Hashes establish data bindings, not
execution attestation or runtime identity. The three focused tests cover an actual
accepted chain, an actual residual-unmet budget stop, and computed declared-limit
exceedance with heat-fraction endpoints; their presence is not a test-run claim.

Success-only admission is intentional: even an actual V126 noncomputed return
with plausible trial counters contributes zero accepted solve/assembly/forward
counts. A later motor boundary failure retains the previously guarded solve counts
and only earlier fully guarded motor results. Neither case establishes a private
child failure cause. `power=null` with the exact state
`NOT_RUN_RESIDUAL_UNMET` belongs to a guarded computed solve with unmet residuals;
it is distinct from atomic failure outputs, which are empty.

The pure guard can accept a different well-formed nonselected result digest after
consistent root resealing. It validates trace contracts and retained selected
content, not unretained producer payloads or historical execution. Guard tests
therefore reject malformed nonselected digests while explicitly allowing a
well-formed replacement. Parameterized boundary tests also cover preflight,
resealed corruption, atomic counts, foreign hooks, and `BaseException`; this text
makes no claim that those tests have been executed.
