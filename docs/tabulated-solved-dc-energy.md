# Tabulated solved DC energy (V128)

`evaluate_tabulated_solved_dc_energy` accepts the exact root fields `evaluation`
and `segments`. Evaluation is `tabulated_solved_dc_energy_experimental`; response
schema is `tabulated_solved_dc_energy_v1`. Supply 1..8 ordered segments with exact
fields `id`, `duration_s`, and a full V127 `power_request`. IDs are unique,
nonblank strings of at most 1992 characters. Durations are positive finite normal
builtin integers or floats, retained in their native type. There are no defaults.

Every full V127 request, motor and auxiliary declaration passes preflight before
any point runs. Each point runs once, is immediately copied only after a bounded
builtin JSON walk, and passes a pure full success guard. The guard checks the
actual full solve, selected rotor operating points, full DC motor contracts,
allocations, nine power totals, units, hashes, stages and scalar transfers without
rerunning models. Point JSON budgets remain the independent V127 catalog budgets.
The root budgets are 1048576 input nodes/depth 24/container 256 and 16777216 output
nodes/depth 36/container 2048. Total admitted work is the sum of
`solve.max_evaluations * sum(rotor annuli)`, at most 65536; each point separately
retains the V126 work limit.

All points run sequentially even after a computed residual-unmet point. Successful
responses always contain `outputs.points`, `energy_state`, and `energy`. Each point
row retains `segment_id`, native `duration_s`, and its full `actual_power_result`
once. Each stage retains the actual full power request and request/result digests.
`output_units.points` is a literal ordered parallel list of row units, so mixed
met/unmet points report their actual power units, including `not_applicable` for
null power. The fresh catalog describes both row variants rather than a fixed list.

If any residual is unmet, the root remains `COMPUTED_EXPERIMENTAL` with complete
diagnostics and all actual points, `energy_state=NOT_RUN_RESIDUAL_UNMET`, null
energy and no energy transfers or elapsed time. This makes no invalid-input or
global-infeasibility claim. If all are met, energy contains ordered segment
start/end times, nine individual and cumulative joule fields, elapsed seconds,
nine joule and Wh totals, and `all_motors_within_declared_limits`.

The nine keys are shaft, motor_electrical, motor_loss, allocated_motor_heat,
unallocated_motor_loss, auxiliary_electrical, auxiliary_heat, total_electrical,
and total_allocated_heat. Each uses its literal V118 power mapping and checked
watts-times-native-duration arithmetic; auxiliary demand is included once.
Every time prefix and energy prefix uses ordered accepted DC power sums.
Positive increments must resolve strictly; absorption, overflow, underflow or
subnormal arithmetic fails atomically. Zero energy increments may remain unchanged.
Wh uses checked total joules divided by 3600. Each of nine W transfers per segment
binds its actual full point digest and the root request digest; duration binds
through the root request. Full point payloads are never duplicated in energy.

A noncomputed, malformed or throwing point is sanitized to `POINT_BOUNDARY_FAILED`.
Failures empty outputs, units, stages and transfers while preserving counts only
from earlier entirely guarded points. Counts describe accepted results, not
attempts, and zero does not imply no call. Root request and evaluation hashes bind
full bounded JSON; the evaluation hash omits itself. `BaseException` propagates.

Settings and source declarations may differ between segments and remain caller
claims, without coupling into a physical mission. This local experimental module
adds no API, UI or publication qualification, source fetching, temperatures,
battery/reserve model, flight dynamics, interpolation, control or mass feedback.

The adversarial tests rehash forged actual point snapshots to ensure hashes alone
do not admit changed scientific contracts. They cover pure success admission,
static metadata and native types, units/counts/totals, motor and solve bindings,
full stages/transfers, preflight of later segments, and atomic prefix counts.
These tests supplement actual-component success and mixed residual-unmet tests.

Actual-component tests exercise every admitted point count from 1 through 8,
zero energy prefixes, and positive duration or energy absorption. Integration
faults occur only after all actual points pass their full guards, so every
accepted point count survives while the outer scientific payload remains atomic.
