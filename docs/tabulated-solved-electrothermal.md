# Tabulated solved electrothermal screening (V129)

`evaluate_tabulated_solved_electrothermal(request)` evaluates actual V128 solved
DC chronology once, then forwards its actual allocated heat and original durations
to one actual chronological lumped thermal screening request. The evaluation is
`tabulated_solved_electrothermal_experimental`; the response schema is
`tabulated_solved_electrothermal_v1`. This is an experimental one-way calculation.

The root has exactly `evaluation`, `energy_request`, `thermal_body`, and
`thermal_segments`. No fields default. `energy_request` is the unchanged V128
request (`tabulated_solved_dc_energy_experimental`), containing 1..8 ordered
`id`, `duration_s`, `power_request` segments. Every nested request and aggregate
work budget is checked before any model runs. See [V128](tabulated-solved-dc-energy.md).

`thermal_body` has exactly `mass_kg`, `specific_heat_j_kg_k`,
`initial_temperature_k`, `lumped_biot_number`, and `property_source`.
`thermal_segments` has exactly one ordered row per energy segment, with matching
`id`, explicit `ambient_temperature_k`, and explicit `conductance_w_k`.
Mass, specific heat, initial/ambient absolute temperatures and thermal capacity
must be positive; conductance is nonnegative. Source text is a nonblank builtin
string of at most 2000 characters. Biot is admitted in `[0,0.1]` for screening
only. The conventional `Bi < 0.1` criterion is documented, not imposed as an
additional gate, measured property, or physical validation.

Root JSON budgets are 4,194,304 nodes including keys, depth 28, container size
256 for input; 33,554,432 nodes, depth 40, container size 2048 for output.
The unchanged V128 input/output budgets and unchanged V119 thermal input/output
budgets apply independently. Only builtin finite JSON is accepted, with bounded
strings, integer sizes, and UTF-8. Every child response is fully bounded before
copying, comparison, or hashing, then detached and bounded again. Root responses
are bounded before and after sealing.

The inline pure energy guard checks the entire retained actual V128 success:
exact catalog metadata/types/limits, status, empty reasons, diagnostics, request
and result hashes, expected count sums, native segment IDs/durations, complete
stages, and actual ordered point unit rows. Each actual point passes V128's full
`_guard_point_success` exactly once during outer admission, without calling a
model, router evaluator, or manufacturing a replacement result envelope.
All-met admission also checks every one of the nine checked W×duration products,
ordered DC prefix/total sums, strictly resolved positive increments, elapsed time,
Wh conversion, declaration flags, energy rows, units and all nine transfers per
point. A claimed status or residual outcome alone never admits a result.

If any residual is unmet, the computed response retains the entire actual energy
result, including every point, stage and mixed met/unmet point unit row.
`outputs.thermal_state` is `NOT_RUN_RESIDUAL_UNMET`, `outputs.thermal` is null,
and thermal units are `not_applicable`. There is one outer energy stage, no outer
transfers and zero thermal results. No partial temperature is reported.

When all residuals are met, the sole thermal request uses
`outputs.points[i].actual_power_result.outputs.power.total_heat_w` and the exact
original native `outputs.points[i].duration_s`. Ambient temperature and conductance
come from the matched explicit thermal row. Heat is already allocated by the
actual point: it is neither reallocated nor replaced by total motor loss.
V119's full success guard admits the actual thermal result without rerunning an
integrator. Each actual thermal `heat_input_j` must equal V128's corresponding
`outputs.energy.segments[i].energy_j.total_allocated_heat` exactly. Thermal's
`fsum` total and V128's DC-summed total may differ only by rounding, with relative
tolerance `64 * sys.float_info.epsilon` and absolute tolerance zero.

Native duration values/types remain intact in the retained point, thermal request,
stage inputs and scalar transfer. Thermal's existing `_number` converts builtin
integers/floats to float; its output duration is therefore that converted float.
For example, native integer `9007199254740993` becomes float `9007199254740992.0`
in the thermal output row. Native integer heat also follows this conversion and
is accepted only when actual per-row joules still match exactly; no replacement
heat is invented. The full guards each establish their own chronology from the
bound original durations. Energy elapsed and thermal elapsed are deliberately
not compared: the DC sum and thermal's sequential float addition have different
arithmetic, and can produce different legitimate elapsed totals.

The all-met response has `thermal_state: COMPUTED`, the full actual children
retained once each, and two outer stages containing full supplied requests and
full result digests. Two scalar transfers per segment, heat then duration, bind
the actual energy point fields to thermal `segments[i].heat_input_w` and
`segments[i].duration_s`, using the full energy-result digest and full
thermal-request digest. Runtime energy units are the retained actual dynamic
units; thermal units come from the fully admitted actual thermal result.

Counts are `energy_result_count`, `thermal_result_count`, and every V128 count.
They advance only after an entire child success guard passes. They describe
accepted results, never attempts or execution attestation. Failures are atomic:
empty outputs/units/stages/transfers and incomplete diagnostics, preserving only
counts of previously fully admitted children. Energy exceptions, malformed or
noncomputed results give `ENERGY_BOUNDARY_FAILED`; thermal equivalents give
`THERMAL_BOUNDARY_FAILED`; faults after admission give
`ELECTROTHERMAL_EXECUTION_FAILED`. No raw child reason or child failure causality
is exported. Ordinary exceptions are sanitized; `BaseException` propagates.
Invalid bounded inputs are `MODEL_INAPPLICABLE`; other evaluation strings are
`SOLVER_UNSUPPORTED`. Successful results remain `COMPUTED_EXPERIMENTAL`.

`tabulated_solved_electrothermal_catalog()` returns fresh metadata without running
models, including both thermal states, dynamic mixed point unit variants,
input/output units, independent budgets, bindings, formulas, qualifications,
count semantics, and the status/reason matrix. Hashes bind full retained JSON,
not code identity or execution. Full child declarations and limitations apply.

This assumes a uniform lumped temperature and constant properties within each
segment. Source notes, motor declarations, thermal properties and Biot numbers
are caller assertions. There is no temperature feedback, derating, radiation,
battery or ESC model, SOC, reserve, flight dynamics, control, or real mission
model. Neither thermal screening, finite arithmetic, conservation residuals nor
hashes establish physical qualification, aircraft feasibility, numerical accuracy,
measured hotspots, safety or publication readiness. Existing files and the known
31 outside-drone fixture failures are outside this additive change.
