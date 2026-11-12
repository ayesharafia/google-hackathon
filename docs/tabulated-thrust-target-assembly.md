# Prescribed tabulated thrust-target static assembly (V114)

`physimesh.drone.tabulated_thrust_target_assembly` provides the separate evaluation
`prescribed_tabulated_rotor_thrust_target_assembly_experimental` through
`evaluate_tabulated_thrust_target_assembly(request)`. It solves each prescribed
isolated rotor thrust target and assembles the actual selected static loads.
Meeting every target tolerance does not imply zero net force or moment, trim,
or aircraft feasibility. There is no API, graph, trim, or mission integration.

## Runnable actual-component example

Run with the package installed, or with `PYTHONPATH=src` from the repository:

```python
from copy import deepcopy
from physimesh.drone.tabulated_thrust_target_assembly import (
    EVALUATION,
    evaluate_tabulated_thrust_target_assembly,
    tabulated_thrust_target_assembly_catalog,
)

target = {
    "evaluation": "tabulated_geometry_hover_thrust_target_experimental",
    "rotor_template": {
        "evaluation": "tabulated_geometry_hover_experimental",
        "radius_m": 1.0,
        "blade_count": 2,
        "root_cutout_m": 0.2,
        "annuli": 12,
        "lift_curve_slope_per_rad": 5.7,
        "profile_drag_coefficient": 0.012,
        "stations": [
            {"radius_m": 0.0, "chord_m": 0.08, "blade_angle_rad": 0.12},
            {"radius_m": 0.5, "chord_m": 0.06, "blade_angle_rad": 0.10},
            {"radius_m": 1.0, "chord_m": 0.04, "blade_angle_rad": 0.08},
        ],
        "geometry_source": "explicit synthetic variable chord and twist",
        "geometry_kind": "synthetic",
        "uncertainty_status": "unknown",
    },
    "target_thrust_n": 100.0,
    "angular_speed_bracket_rad_s": [50.0, 300.0],
    "absolute_thrust_tolerance_n": 0.001,
    "max_evaluations": 32,
}
request = {
    "evaluation": EVALUATION,
    "air": {"altitude_m": 1000.0, "altitude_kind": "geometric"},
    "rotors": [
        {"id": "air", "target_template": deepcopy(target),
         "center_body_m": [1.0, 0.0, 0.0], "axis_body": [0.0, 0.0, 1.0],
         "rotation_sign": 1},
        {"id": "left", "target_template": deepcopy(target),
         "center_body_m": [-1.0, 0.0, 0.0], "axis_body": [0.0, 0.0, 1.0],
         "rotation_sign": -1},
    ],
    "mass_kg": 3.0,
    "cg_body_m": [0.0, 0.0, 0.0],
    "gravity_direction_body": [0.0, 0.0, -1.0],
    "property_source": "unverified explicit example properties",
}
result = evaluate_tabulated_thrust_target_assembly(request)
assert result["status"] == "COMPUTED_EXPERIMENTAL"
assert result["inverse_result_count"] == 2
assert result["forward_evaluation_count"] == sum(
    row["actual_target_result"]["evaluation_count"] for row in result["outputs"]["rotors"]
)
for row in result["outputs"]["rotors"]:
    assert abs(row["actual_target_result"]["outputs"]["thrust_residual_n"]) <= 0.001
assert result["outputs"]["net_moment_cg_body_nm"] == [0.0, 0.0, 0.0]
assert result["outputs"]["net_force_body_n"][2] != 0.0
assert [stage["stage"] for stage in result["stages"]] == ["air", "rotor:air", "rotor:left"]
catalog = tabulated_thrust_target_assembly_catalog()
assert catalog["limits"]["core_work"]["total_forward_annuli_max"] == 32768
print(result["outputs"]["net_force_body_n"])
```

## Closed request and fresh catalog

Every field below is mandatory. Extra fields are forbidden in every request
object. No geometry, coefficient, target, tolerance, bracket, budget, source,
frame, mass, or spin defaults are supplied.

| Root field | Contract and units |
| --- | --- |
| `evaluation` | Exact evaluation label above |
| `air` | Exactly `altitude_m` (m) and `altitude_kind` (label) |
| `rotors` | Ordered builtin list of 1..8 exact rotor objects |
| `mass_kg` | Positive finite normal builtin int/float, exactly convertible to binary64; kg |
| `cg_body_m` | Explicit body-frame position in m, builtin list of three signed numbers |
| `gravity_direction_body` | Explicit declared unit direction, builtin list of three numbers |
| `property_source` | Nonblank unverified builtin string; no source fetch |

Air altitude must be finite builtin int/float in 0..30000 m. Altitude kind is
exactly `geometric` or `geopotential`.

Each rotor contains exactly `id`, `target_template`, `center_body_m`, `axis_body`,
and `rotation_sign`. IDs are unique builtin strings matching
`[A-Za-z][A-Za-z0-9_]{0,31}`; `air` is valid. Centers are positions in m; axes are
dimensionless declared unit vectors. Spin is builtin int `+1` or `-1`, excluding
bool. Positions and signed vector components must convert exactly to finite
normal binary64 or zero. Axes and gravity direction satisfy
`abs(math.hypot(*vector) - 1.0) <= 1e-12`; no normalization occurs.

Each `target_template` contains the exact V108 root fields:
`evaluation`, `rotor_template`, `target_thrust_n` (N),
`angular_speed_bracket_rad_s` (two-element list, rad/s),
`absolute_thrust_tolerance_n` (N), and `max_evaluations` (dimensionless integer).
Targets, tolerances, and both bracket endpoints are finite normal positive
builtin int/float, excluding bool. Tolerance is strictly less than target and
`0 < lo < hi`. All controls remain unchanged; the bracket is never expanded.

The inner rotor template contains exactly `evaluation`, `radius_m`, `blade_count`,
`root_cutout_m`, `annuli`, `lift_curve_slope_per_rad`,
`profile_drag_coefficient`, `stations`, `geometry_source`, `geometry_kind`, and
`uncertainty_status`. Both `density_kg_m3` and `angular_speed_rad_s` MUST be
omitted. Each station has exactly `radius_m` (m), `chord_m` (m), and
`blade_angle_rad` (rad). Radius and cutout are m; lift slope is 1/rad; drag
coefficient and counts are dimensionless. Source and uncertainty are nonblank
unverified text. Geometry kind is `measured`, `digitized_measurement`,
`as_designed`, or `synthetic`, as an unverified caller classification.

The actual accepted core owns the physical geometry and numerical domain,
including positive chord, station ordering and coverage, and cutout/radius
relations. Variable chord and twist use accepted piecewise linear interpolation.
No fabricated density, angular speed, dry-run model call, or envelope is used
to preflight the templates.

`tabulated_thrust_target_assembly_catalog()` returns fresh nested mutable JSON
with these schemas, units, bounds, frame/sign formulas, bindings, limitations,
status/reason matrix, hashes, and count semantics. It makes no model calls.

## Independent bounds and actual execution

Before ANY model call, every rotor passes actual accepted V110 structural
preflight. All structure, exact types, source/classification declarations,
counts, numeric types, mass, frame, axes, and spins are checked across the full
request. Physical geometry domain decisions remain with the actual core.

The global declared work bound is
`sum(rotor.target_template.max_evaluations * rotor.target_template.rotor_template.annuli) <= 32768`
over ALL rotors. There is no selected-subset budget. Each rotor has 1..512
annuli, 2..256 stations, 1..32 blades, and a budget of 2..64 forward evaluations.
There are at most 8 rotors and 4096 total annuli. The global boundary can be met
by eight 512-annulus rotors with budgets of 8; raising one budget to 9 declares
33280 work and is rejected before air.

| JSON boundary | Root depth | Maximum depth | Nodes including keys | Items per container |
| --- | --- | --- | --- | --- |
| Outer request | 1 | 14 | 65536 | 256 |
| Outer response | 1 | 24 | 524288 | 2048 |
| Each injected inverse request | 1 | 11 | 16384 | 256 |
| Each full inverse response | 1 | 16 | 65536 | 2048 |
| Each forward request, owned by inverse | 1 | 10 | 8192 | 256 |
| Each full forward response, owned by inverse | 1 | 10 | 32768 | 2048 |

Every boundary independently limits strings to 2000 Unicode characters,
integers to 1023 bits, and floats to finite values, and requires strict UTF-8.
The strict builtin JSON walk runs before copying the outer request; foreign
conversion/copy hooks are not admitted. Cycles and excess resources are rejected.
The outer output budget accommodates eight full inverses, each retaining its
selected full forward response once and at most 64 scalar trace records.

Actual `reference_air_properties` runs ONCE. The accepted V106 guard checks
exact frozen dataclass types/fields, markers, hydrostatic arithmetic, transport,
and gravity without rerunning air. Raw air, density, and gravity are immediately
snapshotted before any inverse call.

For each ordered rotor, actual density is injected into a copied V108 request.
Actual `evaluate_tabulated_hover_thrust_target` runs ONCE. Its full returned
JSON is bounded and snapshotted immediately, then the accepted pure V109
`validate_tabulated_hover_thrust_target_result` must return `None` against the
original injected request. It checks the selected full forward content, hashes,
units, trace arithmetic, and bounds without any second model evaluation.
No validation response is reconstructed. The V112 assembly evaluator is never
called; its load helper uses only the actual selected forward output values.

## Frame, signs, and loads

The body frame is right-handed forward/left/up. `axis_body` is positive THRUST
direction. Spin `+1` denotes right-hand angular velocity about that axis.
Hub reaction torque opposes spin, using actual selected shaft torque:

```text
F_i      = T_actual_selected_i * axis_i
Qreact_i = -rotation_sign_i * Qshaft_actual_selected_i * axis_i
M_i      = (center_i - CG) cross F_i + Qreact_i
F_grav   = mass * actual_reference_gravity * gravity_direction_body
F_net    = componentwise math.fsum(rotor forces plus gravity force)
M_net    = componentwise math.fsum(rotor moments about CG)
```

Gravity acts at CG and adds zero moment. Signed inputs and all arm, product,
difference, cross-product, moment, and sum results must be finite normal or
exact zero. Exact cancellation is allowed. Overflow, nonzero underflow, and
subnormal results are rejected atomically. No epsilon clamp is used. Unit norm
tolerance is a numerical declaration gate, not physical calibration.

## Outputs, nested units, and provenance

`outputs` contains exactly `air`, `rotors`, `gravity_force_body_n`,
`net_force_body_n`, and `net_moment_cg_body_nm`. Actual guarded raw air appears
once. Each ordered rotor row contains exactly `id`, `force_body_n`,
`reaction_torque_body_nm`, `moment_cg_body_nm`, `actual_target_request`, and
`actual_target_result`. The latter is the unchanged full actual inverse, including
its hashes and trace. The selected full forward response appears once inside
that inverse, with no separate outer copy. JSON snapshots isolate caller inputs,
component arguments, retained air, and retained inverse results; returned JSON
remains mutable and later caller edits can invalidate its hashes.

`output_units.air` covers all raw air fields. Forces use N; torques and moments
use N*m. `output_units.rotors.actual_target_request` describes the full injected
inverse input. The unit hierarchy is deliberately explicit:

```text
output_units.rotors.actual_target_result.outputs
    -> each actual_target_result.outputs only
output_units.rotors.actual_target_result.outputs.actual_forward_result.outputs
    -> its selected actual_forward_result.outputs only
```

Neither mapping claims units for an entire response envelope. Scalar trace
field units are separately described by the catalog's `trace_field_units`.

Stages are `air`, then `rotor:<id>` in order, including `rotor:air`. Each stage
contains only `stage`, actual `inputs`, `inputs_sha256`, and `result_sha256`;
there are no result payload arrays in stages. Air result hashes cover full raw
air; rotor result hashes cover full actual inverses. Each transfer records only
the actual density scalar in kg/m^3 from `air.state.density_kg_m3` to the rotor
stage's `rotor_template.density_kg_m3`, with producer full-air and consumer
injected-request digests.

Intermediate trace `full_actual_result_sha256` values are FORMAT-ONLY
producer-reported provenance. Their payloads are absent, so their content cannot
be independently verified; a different valid lowercase 64-hex intermediate
digest remains admissible. The selected retained full forward response IS
content-verified, and trace arithmetic is checked without rerunning the model.

## Counts, statuses, hashes, and atomic failures

`inverse_result_count` is builtin int 0..8 and increments ONLY after the full
inverse guard accepts an envelope, including a valid failure. The builtin int
`forward_evaluation_count`, 0..512, sums actual guarded inverses' `evaluation_count`
ONLY after full guard acceptance. Invalid returned payloads add zero to both.
These counts describe validated envelopes, not attempted calls or execution
attestation. They do not certify that a producer actually executed a model.

Execution stops on the first actual guarded noncomputed inverse, propagating
`MODEL_INAPPLICABLE`, `TARGET_NOT_BRACKETED`, `ITERATION_LIMIT`, `NUMERICAL_LIMIT`,
or `EXECUTION_FAILED`. Prior guarded counts are retained. A valid second inverse
failure counts both envelopes and their guarded forward counts; an invalid
second payload or an ordinary second-call exception counts only the first.

V109 failure admission is narrow and unchanged: atomic payload, exact reasons,
hashes, and necessary count bounds are checked. Such checks are necessary
envelope constraints, not execution attestation. Infrastructure copy/hash fault
envelopes outside that admission are rejected as `EXECUTION_FAILED`; their
untrusted counts are discarded. No fabricated valid component is substituted.

| Outcome | Status | Request SHA256 | Evaluation SHA256 |
| --- | --- | --- | --- |
| Invalid preflight | `MODEL_INAPPLICABLE` | null | null |
| Different outer evaluation on bounded exact root | `SOLVER_UNSUPPORTED` | null | null |
| Request snapshot failure | `EXECUTION_FAILED` | null | null |
| Guarded actual physical/numerical domain refusal | `MODEL_INAPPLICABLE` | Accepted snapshot | null |
| Guarded target not bracketed, budget exhausted, or numerical limit | Corresponding bounded failure status | Accepted snapshot | Full failed response |
| Ordinary exception or invalid component after request hashing | `EXECUTION_FAILED` | Accepted snapshot | Full failed response |
| All guarded targets and load arithmetic accepted | `COMPUTED_EXPERIMENTAL` | Accepted snapshot | Full success response |

Digests reuse accepted SHA256 over sorted compact UTF-8 JSON, with
`ensure_ascii=False` and `allow_nan=False`. The outer request hash covers the
actual accepted snapshot. Evaluation hashes cover the full outer response with
only its own `evaluation_sha256` omitted. Request hashing failure leaves no
request hash. If the hash/export mechanism itself fails, sealing is subject to
that mechanism's availability; hashes establish no runtime identity.

Every returned failure has empty `outputs` and `output_units` objects, empty
`stages` and `transfers` lists, and `diagnostics_complete` false. No partial
results or ordinary exception text are exported. Ordinary `Exception` becomes
`EXECUTION_FAILED`; `BaseException` propagates.

## Limitations

The model is isolated small-angle attached-linear hover with fixed lift slope
and drag coefficient. Reference air supplies density and gravity only. Geometry
source/classification, uncertainty, properties, frame, and spin remain unverified
caller declarations. Numerical finite values, unit gates, target residuals,
hashes, counts, and tests establish no physical accuracy or qualification.

There is no Reynolds/Mach feedback or polars, stall, loss factors, swirl,
interference, installed physics, or ground effect. There are no motor limits,
attainable RPM assessments, trim, control, stability, safety, feasibility,
structural model, dynamics, or mission. Physical validation, numerical
qualification, and runtime identity remain `NOT_ESTABLISHED`; aircraft status
and feasibility remain null. This local experimental contract makes no
publication, complete-standard, 80% accuracy, or novelty qualification claim.
