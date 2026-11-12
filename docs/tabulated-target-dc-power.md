# Prescribed tabulated targets to DC electrical demand and allocated heat

`evaluate_tabulated_target_dc_power` is a local experimental bridge with evaluation
`prescribed_tabulated_target_dc_power_experimental`. It evaluates the full actual
V114 prescribed target assembly once, validates the retained response with the
pure V115 guard, and evaluates one actual constant-parameter DC motor per ordered
rotor. The selected forward request supplies angular speed; its retained actual
forward outputs supply unsigned shaft torque. Requested thrust and approximate
trace values do not supply the motor operating point. Assembly rotation signs
remain part of the signed assembly loads and never negate motor torque.

Run this self-contained example from the repository root. The fixed 100 N targets,
geometry, motor parameters, limits, sources and heat fractions are synthetic
unverified declarations. The example calls the bridge once.

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /downloads/physimesh-continuation-venv/bin/python -B - <<'PY'
import json
from copy import deepcopy
from physimesh.drone import tabulated_hover_bemt_request as forward
from physimesh.drone import tabulated_hover_thrust_target as inverse
from physimesh.drone import tabulated_thrust_target_assembly as assembly
from physimesh.drone.tabulated_target_dc_power import (
    EVALUATION, evaluate_tabulated_target_dc_power,
)

target = {
    "evaluation": inverse.EVALUATION,
    "rotor_template": {
        "evaluation": forward.EVALUATION,
        "radius_m": 1.0, "blade_count": 2, "root_cutout_m": 0.2,
        "annuli": 12, "lift_curve_slope_per_rad": 5.7,
        "profile_drag_coefficient": 0.012,
        "stations": [
            {"radius_m": 0.0, "chord_m": 0.08, "blade_angle_rad": 0.12},
            {"radius_m": 0.5, "chord_m": 0.06, "blade_angle_rad": 0.10},
            {"radius_m": 1.0, "chord_m": 0.04, "blade_angle_rad": 0.08},
        ],
        "geometry_source": "explicit synthetic variable chord and twist",
        "geometry_kind": "synthetic", "uncertainty_status": "unknown",
    },
    "target_thrust_n": 100.0,
    "angular_speed_bracket_rad_s": [50.0, 300.0],
    "absolute_thrust_tolerance_n": 0.001, "max_evaluations": 32,
}
rotors = [
    {"id": name, "target_template": deepcopy(target),
     "center_body_m": [x, 0.0, 0.0], "axis_body": [0.0, 0.0, 1.0],
     "rotation_sign": spin}
    for name, x, spin in [("air", 1.0, 1), ("left", -1.0, -1)]
]
request = {
    "evaluation": EVALUATION,
    "assembly": {
        "evaluation": assembly.EVALUATION,
        "air": {"altitude_m": 1000.0, "altitude_kind": "geometric"},
        "rotors": rotors, "mass_kg": 3.0,
        "cg_body_m": [0.0, 0.0, 0.0],
        "gravity_direction_body": [0.0, 0.0, -1.0],
        "property_source": "unverified explicit synthetic properties",
    },
    "motors": [{
        "id": rotor["id"],
        "parameters": {
            "motor_constant_si": 0.1, "terminal_resistance_ohm": 0.2,
            "zero_torque_current_a": 0.5,
            "parameter_source": "synthetic, not measured",
            "applicability_declaration": "constant_parameter_dc_equivalent_only",
        },
        "declared_limits": {
            "maximum_current_a": 10000.0,
            "maximum_terminal_voltage_v": 10000.0,
            "maximum_angular_speed_rad_s": 10000.0,
            "maximum_shaft_torque_nm": 10000.0,
            "limit_source": "synthetic declarations, not continuous ratings",
        },
        "heat_fraction_of_motor_loss": 0.5,
        "heat_source": "synthetic heat allocation",
    } for rotor in rotors],
    "auxiliary": {
        "power_w": 10.0, "heat_fraction": 0.25,
        "source": "synthetic auxiliary demand and allocation",
    },
}
result = evaluate_tabulated_target_dc_power(request)
assert result["status"] == "COMPUTED_EXPERIMENTAL", result["reasons"]
assert result["motor_result_count"] == 2
assert result["outputs"]["power"]["auxiliary_heat_w"] == 2.5
assert all("evaluation_sha256" not in row["actual_motor_result"]
           for row in result["outputs"]["power"]["motors"])
print(json.dumps({"status": result["status"], "power": {
    key: value for key, value in result["outputs"]["power"].items()
    if key != "motors"
}}, indent=2))
PY
```

The exact root fields are `evaluation`, `assembly`, `motors` and `auxiliary`, with
no defaults or extra fields. `assembly` is the complete unchanged V114 request:
`evaluation`, `air`, `rotors`, `mass_kg`, `cg_body_m`,
`gravity_direction_body`, `property_source`. All target controls and mandatory
frame, mass, geometry, source and reference-air declarations remain mandatory.
V114 retains its signed forward/left/up force and moment conventions, including
reaction torque opposing spin and gravity applied at the declared CG.

`motors` is a builtin ordered list of 1–8 exact objects, matching every assembly
rotor ID and order. Each object has exactly `id`, `parameters`, `declared_limits`,
`heat_fraction_of_motor_loss`, `heat_source`. The example lists every parameter
and limit field. `motor_constant_si` is strictly positive;
`terminal_resistance_ohm` and `zero_torque_current_a` are nonnegative, including
zero. All four declared maxima are strictly positive. Values must be builtin
finite normal int/float numbers or an explicitly allowed zero; bool and numeric
subclasses are rejected. Accepted integers retain the native arithmetic types
used by the actual motor rather than being gratuitously converted to floats.
Sources are nonblank strings; applicability is exactly
`constant_parameter_dc_equivalent_only`. No operating point may be supplied in
the motor declarations. Fractions are finite normal or zero values in [0, 1].
`auxiliary` has exactly `power_w`, `heat_fraction`, `source`, with nonnegative
power and a mandatory nonblank source.

Before any air, assembly or motor call, the bridge walks strict builtin JSON,
copies the request, checks the exact root/evaluation, and runs the actual V114
pure structural preflight. It checks every rotor and the global sum
`sum(max_evaluations * annuli) <= 32768`, then all motor parameters, limits,
IDs, sources, fractions and auxiliary fields. It does not fabricate an Omega/Q
pair or call the motor preflight with dummy data. Geometry and physical-domain
refusals remain owned by the actual accepted assembly components.

Every JSON walk counts values and keys, with root depth 1, strings at most 2000
characters with strict UTF-8, integers at most 1023 bits, and finite floats only.
Only builtin JSON containers and scalar types are admitted; foreign objects,
container subclasses and cycles are rejected before copying caller data.
Independent budgets are:

| Payload | Maximum nodes | Maximum depth | Maximum container items |
| --- | ---: | ---: | ---: |
| Outer input | 131072 | 16 | 256 |
| Assembly input | 65536 | 14 | 256 |
| Assembly output | 524288 | 24 | 2048 |
| Motor request | 4096 | 10 | 256 |
| Motor result | 8192 | 12 | 2048 |
| Outer output | 1048576 | 28 | 2048 |

The accepted V114 child budgets also apply independently. Structural maxima
include 8 rotors, 512 annuli per rotor, 256 stations, 32 blades, 64 inverse
trials per rotor, and the global 32768 forward-annulus work bound. Actual call
bounds are one assembly, one reference-air evaluation, at most eight inverses,
512 forward trials and eight motors. There are no HTTP byte limits.

The bridge immediately bounds and detaches the full actual assembly response,
then requires the actual V115 guard to return `None`. That pure guard checks the
retained full payload, including selected child content, signed loads, raw air,
metadata, units, hashes and stages. Its narrow infrastructure copy/hash-fault
admission behavior remains unchanged; a rejected assembly contributes zero
counts. Valid noncomputed assembly statuses propagate atomically without any
motor call. There is no bridge rerun of air, inverse or forward models.

For a computed assembly, each real motor request contains exactly `evaluation`,
`parameters`, `declared_limits`, `operating_point`. The bridge calls
`dc_motor.evaluate_dc_motor` once per rotor; the evaluator calls its `_compute`
once. Each full actual response is immediately bounded and detached before its
success guard. The guard never calls `_compute` or an evaluator. It compares the
actual full envelope directly against private explicit constants copied from
the accepted DC evaluator: exact keys, markers, null qualifications,
diagnostics, reasons, stages, transfers, units, source URL/scope and limitations,
plus the actual request digest. No response is fabricated to establish those
constants. The actual motor has **no `evaluation_sha256` field**; none is added.

The equation source retained in each actual motor envelope is the accepted
[MIT Drela constant-parameter motor theory URL](https://web.mit.edu/drela/Public/web/qprop/motor1_theory.pdf),
with scope `Steady constant-parameter DC-equivalent equations`. This is equation
provenance, not measured parameter evidence. Parameter, limit, heat and auxiliary
sources are unverified caller declarations and are not fetched.

With actual selected torque Q and angular speed omega, return-contract arithmetic
uses the accepted checked helpers and operation order:

```text
I = power_sum([Q/k, I0])
Eb = k*omega
V = power_sum([Eb, I*R])
Pshaft = Q*omega
Pelec = V*I
Pcopper = 0.0 if R == 0 else (I*I)*R
Pfriction_equivalent = Eb*I0
Ploss = power_sum([Pcopper, Pfriction_equivalent])
accounted = power_sum([Pshaft, Ploss])
residual = Pelec-accounted
eta = Pshaft/accounted if accounted > 0 else null
```

The guard compares native scalar types and values directly. It requires
`abs(residual/max(Pelec,accounted)) <= 64*sys.float_info.epsilon` when the norm is
positive, otherwise exact zero residual. Null efficiency is allowed only for
zero accounted, shaft, loss and electrical power. The normal positive-torque
example has nonnull efficiency, including ideal R=I0=0 with zero motor loss.
The selected forward shaft power and actual motor shaft power are additionally
cross-bound with relative tolerance `1e-12` and absolute tolerance `1e-12 W`.
Both bounds check arithmetic consistency and multiplication order; they are
not physical accuracy thresholds or independent physical oracles.

All four declared limit checks are inclusive. Equality is within the declaration;
exceedance is a valid `COMPUTED_EXPERIMENTAL` result with the actual flags and
`EXCEEDS_DECLARED_LIMITS` status retained. The power summary includes
`all_motors_within_declared_limits`. These declarations do not establish motor
attainability, continuous thermal ratings, safety or aircraft feasibility.

For each actual motor row, `allocated_heat_w = actual total_loss_w * declared
heat fraction`; `unallocated_loss_w = actual total_loss_w - allocated_heat_w`.
The latter is retained loss outside the declared heat allocation. Fraction zero
allocates zero heat; fraction one leaves zero unallocated loss. Motor loss
includes both copper and friction-equivalent loss and is not all copper.
Auxiliary electrical demand is counted once; auxiliary heat is its declared
power times its own fraction. Shaft power is never heat.

`outputs.power` contains ordered `motors` rows with exactly `id`,
`actual_motor_request`, `actual_motor_result`, `allocated_heat_w`,
`unallocated_loss_w`. Accepted `dc_motor._power_sum` accumulates
`total_shaft_power_w`, `total_motor_electrical_power_w`, `total_motor_loss_w`,
`total_allocated_motor_heat_w`, `total_unallocated_motor_loss_w` over the actual
rows. `auxiliary_electrical_power_w` and `auxiliary_heat_w` are separate.
`total_electrical_power_w` adds motor and auxiliary electrical power;
`total_heat_w` adds allocated motor heat and auxiliary heat. Heat fractions are
never applied to total electrical demand. Overflow, subnormal derived results,
nonzero product underflow and absorbed positive summands fail atomically.

`outputs.assembly` preserves the full actual V114 response once, including all
nested payloads and original hashes. Every motor row preserves its full actual
response once. Unit metadata is scoped precisely:

```text
output_units.assembly.outputs = actual assembly.output_units
output_units.power.motors.actual_motor_result.outputs = actual motor.output_units
output_units.power.motors.actual_motor_request = full request units
```

There is no assignment of output units to a full component envelope. Motor
request units cover evaluation, every parameter, declared limit, operating-point
scalar, and source/declaration string. Outer power and allocation values use W.

The first stage is `assembly`, followed by `motor:<id>` in rotor order. Each
stage retains actual inputs, their `inputs_sha256`, and a `result_sha256` of the
full actual component JSON; no stage result arrays are duplicated. Each motor
has two scalar transfers from assembly, with paths:

```text
outputs.rotors[i].actual_target_result.outputs.actual_forward_request.angular_speed_rad_s
  -> operating_point.angular_speed_rad_s  (rad/s)
outputs.rotors[i].actual_target_result.outputs.actual_forward_result.outputs.shaft_torque_nm
  -> operating_point.shaft_torque_nm      (N*m)
```

Each transfer binds `producer_result_sha256` to the full actual assembly digest
and `consumer_request_sha256` to the actual motor request digest. No component
response hashes are patched. Snapshots isolate caller data, component arguments,
retained assembly data and earlier motor returns from later mutations.

| Outcome | Request hash | Evaluation hash | Exported payload |
| --- | --- | --- | --- |
| Invalid preflight, MODEL_INAPPLICABLE | null | null | empty |
| Unsupported outer evaluation, SOLVER_UNSUPPORTED | null | null | empty |
| Computed | actual snapshot hash | full outer response hash | full assembly and motor rows |
| Guarded assembly MODEL_INAPPLICABLE | actual snapshot hash | null | empty |
| Guarded assembly TARGET_NOT_BRACKETED, ITERATION_LIMIT, NUMERICAL_LIMIT or EXECUTION_FAILED | actual snapshot hash | full outer response hash | empty |
| Later execution/contract/arithmetic failure, EXECUTION_FAILED | snapshot hash if established | full outer response hash if request hash exists | empty |
| Request snapshot/hash infrastructure failure | null if not established | null if no request hash | empty |

Evaluation hashes omit only their own `evaluation_sha256` field and otherwise
cover the full outer response. Canonical hashing uses sorted compact UTF-8 JSON,
`ensure_ascii=False`, `allow_nan=False`. All failures have `outputs` and
`output_units` empty, `stages` and `transfers` empty, and
`diagnostics_complete=False`; no exception text or partial component results
are exported. Ordinary exceptions are sanitized; `BaseException` propagates.

`assembly_inverse_result_count` (0–8) and `forward_evaluation_count` (0–512) are
trusted only after the entire V115 assembly guard, including valid failure
responses. `motor_result_count` (0–8) increments only after the complete motor
success guard. An invalid or actual EXECUTION_FAILED motor does not increment
it. A subsequent heat-allocation or total arithmetic failure retains prior
validated counts, including a motor that already passed its guard. Counts and
hashes are returned-contract provenance, not execution attestation.

`tabulated_target_dc_power_catalog()` returns deep-fresh request fields, complete
units, formulas, limits, status/hash/count contracts and bindings. Its private
V114 catalog metadata is captured at import time without model calls. Output
units come from that metadata rather than a fabricated component. Catalog reads
do not invoke any evaluator, and caller mutations cannot change later reads.

The focused tests include actual fixed-target component equality, exact nested
hash/unit preservation, inclusive limits, integer parameters, ideal and lossy
motors, endpoint heat allocations, rejected forgeries, actual numeric failures,
mutation isolation, and maximum bounded payloads. The total-overflow test is
explicitly a `_power_sum` helper arithmetic probe; it does not claim the standard
assembly reaches a total-overflow scenario.

This bridge adds no ESC loss, battery/bus, temperature or thermal integration,
Reynolds/Mach polar, interference, trim, control, stability, mission or API model.
Physical validation, numerical qualification and runtime identity remain
`NOT_ESTABLISHED`, with null aircraft status and feasibility. It establishes no
publication qualification, 80 percent result or novelty claim.
