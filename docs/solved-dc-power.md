# Solved DC power point bridge

`physimesh.drone.solved_dc_power.evaluate_solved_dc_power(request)` evaluates
`solved_static_wrench_dc_power_experimental` using the accepted V95 contracts.
This is an experimental, unverified static point computation. It does not execute
a mission or thermal model, establish aircraft feasibility, or qualify parameters.

## Request schema

The root is an exact builtin dictionary with only `evaluation`, `solve`, `motors`,
and `auxiliary`. `evaluation` is the string shown above. `solve` is a complete
accepted `bounded_static_wrench_solve_experimental` request, including its assembly
template, ordered rotor speed bounds, required force/moment, absolute tolerances,
and evaluation budget. Its accepted schema and model restrictions apply unchanged.

`motors` is an ordered builtin list, with one entry for each rotor in
`solve.assembly_template.rotors`, in exactly that order. Each entry has exactly:

```text
node: matching rotor node string
parameters:
  motor_constant_si: positive number
  terminal_resistance_ohm: nonnegative number
  zero_torque_current_a: nonnegative number
  parameter_source: nonblank string, at most 2000 characters
  applicability_declaration: "constant_parameter_dc_equivalent_only"
declared_limits:
  maximum_current_a: positive number
  maximum_terminal_voltage_v: positive number
  maximum_angular_speed_rad_s: positive number
  maximum_shaft_torque_nm: positive number
  limit_source: nonblank string, at most 2000 characters
heat_fraction_of_motor_loss: number in [0, 1]
heat_source: nonblank string, at most 2000 characters
```

Both nested motor dictionaries have exactly the listed V95 fields. There is no
caller-supplied motor operating point. `auxiliary` has exactly these fields:

```text
power_w: nonnegative number
heat_fraction: number in [0, 1]
source: nonblank string, at most 2000 characters
```

Numbers must be builtin integers or floats, finite, and normal when nonzero;
booleans and subnormals are rejected. Zero resistance, zero zero-torque current,
zero heat fractions, and zero auxiliary power are valid. Positive fields remain
strictly positive. Extra keys, reordered motors, and mismatched nodes are invalid.

## Preflight and selected point

The outer JSON validator runs with keyword `budget=49152` before deepcopy.
This is a structural JSON node budget, not a byte allowance; inherited depth,
container, string, and integer bounds also apply. The accepted shaft bridge
preflight enforces its solve/graph restrictions and aggregate annuli work bound
`sum(annuli) * (max_evaluations + 1) <= 32768`. The solver's own work bound and
request budget remain in force. Each motor request receives the accepted DC
preflight with JSON budget 4096, initial bounded speed, and zero torque solely
for structural validation. All preflight finishes before evaluator calls.

Internally, the shaft request uses conversion efficiency one for every rotor and
auxiliary power zero, with explicit internal shaft-only source declarations.
Those conversion values do not estimate motor electrical input. The bridge calls
the accepted solved wrench power evaluator once, then validates its request hash,
experimental envelope, actual outputs, units, selected candidate, and provenance
through `se._validated_power_result(raw, request)`.

An unmet residual returns the actual solve outputs/units, nested shaft stages,
`power_state="NOT_RUN_RESIDUAL_UNMET"`, and null power/units. No motors run.
When met, each motor runs exactly once at its actual validated selected shaft-row
speed and torque. Motor results require the accepted envelope, exact units and
output keys, strict numeric/boolean types, empty stages/transfers, and exact
`dc._compute(request)` reconstruction after type checks. This is V95 DC electrical
input, rather than a caller efficiency estimate.

## Outputs and accounting

`outputs` contains `solve`, `power_state`, and `power`. A computed power object has
`motors`, whose rows contain `node`, `angular_speed_rad_s`, `shaft_torque_nm`,
the actual V95 outputs under `motor`, `allocated_heat_w`, and `unallocated_loss_w`.
The motor object includes current, back EMF, terminal voltage, shaft/electrical
power, copper/friction-equivalent/total loss, balance residual, efficiency, declared
limit status, and the four boolean limit checks. Output units mirror this shape.

The power totals are `total_shaft_power_w`, `total_motor_electrical_power_w`,
`total_motor_loss_w`, `total_allocated_motor_heat_w`,
`total_unallocated_motor_loss_w`, `total_electrical_power_w`,
`auxiliary_electrical_power_w`, `auxiliary_heat_w`, and `total_allocated_heat_w`.
All these totals and row heat/loss allocations use watts.

Motor heat is total motor loss times its declared capture fraction. Unallocated
motor loss is the checked difference between loss and captured heat. Auxiliary
power enters total electrical input exactly once; auxiliary heat is independently
its power times its fraction. Total allocated heat includes both heat terms.
This differs from the V94 mission convention of a fraction of total electrical
input. Checked products/differences and accepted nonloss sums reject unsupported
overflow, underflow, or resolution loss. Existing tolerances are unchanged.

`EXCEEDS_DECLARED_LIMITS` retains actual motor outputs and screening checks. It
does not become execution failure or an aircraft feasibility conclusion. There is
no bus current, ESC, battery, regeneration, installed-flight, or thermal feedback
calculation.

## Standalone Decimal arithmetic anchor

This loaded motor example is independent arithmetic, not the real solved test
fixture or a claim that its operating point satisfies any requested wrench:

```python
from decimal import Decimal as D, localcontext
with localcontext() as context:
    context.prec = 60
    k, R, I0, omega, Q = map(D, (".1", ".2", "1", "100", "2"))
    current = Q / k + I0                       # 21 A
    electrical = (k * omega + current * R) * current  # 298.2 W
    loss = current * current * R + k * omega * I0     # 98.2 W
    heat = loss * D(".25") + D("20") * D(".5")      # 34.55 W
    total_electrical = electrical + D("20")           # 318.2 W
    unallocated_motor_loss = loss - loss * D(".25")   # 73.65 W
```

## Failure, provenance, and evidence bounds

Invalid preflight uses the accepted narrow exception set and returns `GRAPH_INVALID`.
Runtime `Exception` produces atomic `EXECUTION_FAILED` with empty outputs, units,
stages, and transfers plus a generic reason; the valid request hash is retained.
`BaseException` propagates. Success is `COMPUTED_EXPERIMENTAL` with diagnostics true.
Evidence stays `unverified`; physical validation, numerical qualification, and
runtime identity stay `NOT_ESTABLISHED`; feasibility and aircraft status stay null.
Deep copies isolate inputs and returned results. Stages hash actual shaft/motor
requests and results, preserve nested shaft stages, and record operating-point and
heat-source transfers. Hashes establish neither physical validation nor identity.

The [MIT Drela motor theory](https://web.mit.edu/drela/Public/web/qprop/motor1_theory.pdf)
provides the steady constant-parameter equation source, not parameter validation.
Focused tests cover real solve/shaft/motor paths and invalid/adversarial contracts.
Local full-drone regression completed with 4654 tests passed, 5 skipped, and 359 subtests passed. This is software verification only; independent acceptance and physical validation remain separate gates.
