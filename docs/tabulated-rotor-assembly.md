# Literal tabulated rotor static assembly (V112)

`physimesh.drone.tabulated_rotor_assembly` provides the separate evaluation
`literal_tabulated_rotor_static_assembly_experimental`. It linearly superposes
isolated tabulated hover rotor loads and gravity in an explicitly declared body
frame. It does not integrate with a graph, trim solver, mission, or API.

## Runnable actual-component example

Run with the package installed, or from the repository with `PYTHONPATH=src`:

```python
from copy import deepcopy
from physimesh.drone.tabulated_rotor_assembly import (
    EVALUATION,
    evaluate_tabulated_rotor_assembly,
    tabulated_rotor_assembly_catalog,
)

template = {
    "evaluation": "tabulated_geometry_hover_experimental",
    "radius_m": 1.0,
    "angular_speed_rad_s": 120.0,
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
}
request = {
    "evaluation": EVALUATION,
    "air": {"altitude_m": 1000.0, "altitude_kind": "geometric"},
    "rotors": [
        {"id": "air", "rotor_template": deepcopy(template),
         "center_body_m": [1.0, 0.0, 0.0], "axis_body": [0.0, 0.0, 1.0],
         "rotation_sign": 1},
        {"id": "left", "rotor_template": deepcopy(template),
         "center_body_m": [-1.0, 0.0, 0.0], "axis_body": [0.0, 0.0, 1.0],
         "rotation_sign": -1},
    ],
    "mass_kg": 3.0,
    "cg_body_m": [0.0, 0.0, 0.0],
    "gravity_direction_body": [0.0, 0.0, -1.0],
    "property_source": "unverified explicit example properties",
}
result = evaluate_tabulated_rotor_assembly(request)
assert result["status"] == "COMPUTED_EXPERIMENTAL"
assert result["rotor_evaluation_count"] == 2
assert result["outputs"]["net_moment_cg_body_nm"] == [0.0, 0.0, 0.0]
assert [stage["stage"] for stage in result["stages"]] == [
    "air", "rotor:air", "rotor:left",
]
print(result["outputs"]["net_force_body_n"])
catalog = tabulated_rotor_assembly_catalog()
assert catalog["limits"]["core_work"]["total_annuli_max"] == 4096
```

## Closed request and catalog schema

Every listed field is mandatory; extra fields are forbidden at every request
object. No geometry, coefficient, speed, source, frame, spin, or mass defaults
are supplied. The catalog returns fresh mutable JSON describing required fields,
input/output units, limits, formulas, frame, spin, bindings, statuses, hashes, and
count semantics. Calling the catalog executes no evaluator and fetches no source.

| Root field | Contract and units |
| --- | --- |
| `evaluation` | Exact evaluation label above |
| `air` | Exact `altitude_m` (m) and `altitude_kind` (label) |
| `rotors` | Ordered builtin list of 1 through 8 exact rotor objects |
| `mass_kg` | Positive finite normal builtin int/float, kg |
| `cg_body_m` | Explicit body-frame position, m, builtin list of three numbers |
| `gravity_direction_body` | Declared unit direction, dimensionless, list of three numbers |
| `property_source` | Nonblank unverified builtin string; no source fetch |

Air altitude is explicit builtin finite int/float from 0 through 30000 m, with
`altitude_kind` exactly `geometric` or `geopotential`, following accepted V106.

Each rotor has exactly `id`, `rotor_template`, `center_body_m`, `axis_body`, and
`rotation_sign`. IDs are unique builtin strings matching
`[A-Za-z][A-Za-z0-9_]{0,31}`. The ID `air` is valid. Centers are explicit positions
in m; axes are dimensionless declared unit vectors; spin is builtin int `+1` or
`-1`, excluding bool.

Each template contains exactly the V105 request fields except `density_kg_m3`,
which MUST be omitted even if it would equal the reference density:

| Template field | Units or declaration |
| --- | --- |
| `evaluation` | `tabulated_geometry_hover_experimental` |
| `radius_m`, `root_cutout_m` | m |
| `angular_speed_rad_s` | rad/s; explicit forward speed, no inverse solve |
| `blade_count`, `annuli` | Dimensionless builtin integer counts |
| `lift_curve_slope_per_rad` | 1/rad |
| `profile_drag_coefficient` | Dimensionless |
| `stations` | Ordered list of exact `radius_m` (m), `chord_m` (m), `blade_angle_rad` (rad) objects |
| `geometry_source`, `uncertainty_status` | Nonblank unverified text |
| `geometry_kind` | `measured`, `digitized_measurement`, `as_designed`, or `synthetic`; unverified caller classification |

The actual core owns the physical geometry domain: positive chord and radius,
strictly increasing station radii, coverage through exactly the rotor radius,
first station at or inside the root cutout, and cutout strictly inside the radius.
Chord and blade angle may both vary; accepted interpolation is piecewise linear.
Source declarations and classification establish no measurement verification.

## Frame, signs, and numerical arithmetic

The body frame is right-handed forward/left/up. Each axis is the positive THRUST
direction. A spin sign of `+1` means angular velocity follows the right-hand rule
about that positive axis. The hub reaction opposes the spin sign:

```text
F_i      = T_i * axis_i
Qreact_i = -rotation_sign_i * Qshaft_i * axis_i
arm_i    = center_i - CG
M_i      = arm_i cross F_i + Qreact_i
F_grav   = mass * actual_reference_gravity * gravity_direction_body
F_net    = componentwise math.fsum(rotor forces plus gravity force)
M_net    = componentwise math.fsum(rotor moments about CG)
```

Gravity acts at the declared CG and adds no gravity moment. Reference gravity
varies with the requested altitude; no constant gravity is inferred.

Vector inputs must be builtin lists of three builtin int/float values, excluding
bool and subclasses. Positions and signed vector components must convert exactly
to finite normal binary64 values or zero. Mass must convert exactly to a positive
finite normal binary64 value. Each axis and gravity direction must satisfy
`abs(math.hypot(*vector) - 1.0) <= 1e-12`. This is a numerical declaration gate,
not physical calibration; vectors are never normalized or epsilon-clamped.

Arms, signed products, cross-product differences, moment additions, and net sums
must remain finite normal or exact zero. Negative loads and exact cancellation
to zero are legitimate. Overflow, subnormal results, and nonzero products that
underflow to zero fail atomically. Zero blade angle legitimately gives zero
thrust and induced power, while profile drag may retain nonzero shaft torque and
power. Zero profile drag with zero angle permits exact zero shaft torque.

## Preflight, independent budgets, and actual execution

Strict builtin JSON is walked before copying and the copied request is checked
again. Foreign object conversion/copy hooks are not invoked. Cycles, excessive
depth, foreign types, nonfinite floats, invalid UTF-8 strings, and oversized
containers, strings, integers, or node counts are rejected before component calls.
All entries undergo structural/type/count/declaration/classification/numeric-type,
axis/spin/frame/mass preflight before air runs. No dummy defaults or core dry run
are used. Physical geometry domain checks remain with the actual core; a late
physical refusal may follow prior successful rotor calls.

All rotors are executed on success. Before ANY air, adapter, or core call, there
must be at most 8 rotors and the sum of annuli over ALL entries must be at most
4096. Each rotor independently requires 1..2048 annuli, 2..256 stations, and
1..32 blades. Counts are builtin integers only. There is no selected-subset budget.

| JSON boundary | Root depth | Maximum depth | Nodes including keys | Items per container |
| --- | --- | --- | --- | --- |
| Outer request | 1 | 12 | 65536 | 256 |
| Outer response | 1 | 20 | 262144 | 2048 |
| Each injected V105 request | 1 | 10 | 8192 | 256 |
| Each full V105 response | 1 | 10 | 32768 | 2048 |

Every boundary also limits strings to 2000 Unicode characters, integers to 1023
bits, and floats to finite values, and requires strict UTF-8. These are independent
budgets visible in the catalog. No HTTP byte limit is added. The outer response
budget accommodates the full 4096-annulus assembly and eight 256-station rotors.

Execution calls actual `reference_air_properties` once. The accepted V106 guard
checks exact frozen dataclass types, fields, markers, altitude, hydrostatic
arithmetic, and transport/gravity arithmetic without rerunning the model. Raw air,
density, and gravity are snapshotted immediately before any rotor call.

For each ordered rotor, the actual validated density is injected into a copied
V105 request. The actual forward adapter runs once and calls its actual core once.
Its returned full JSON is immediately bounded and copied, then checked through
the accepted V106 full-child guard, including metadata, units, request/result
hashes, interpolation, governing balances, and output arithmetic. No fake envelope,
replacement dataclass, or second evaluation is constructed to validate it.

## Outputs, units, stages, and data hashes

`outputs.air` retains the actual guarded raw air once. Ordered `outputs.rotors`
rows contain exactly `id`, `force_body_n`, `reaction_torque_body_nm`,
`moment_cg_body_nm`, `actual_forward_request`, and `actual_forward_result`.
The actual full forward result is retained unchanged once per rotor, including
its own hashes. The other outer outputs are `gravity_force_body_n`,
`net_force_body_n`, and `net_moment_cg_body_nm`. Retained JSON is detached and
mutable; later mutation of a component's retained result cannot change earlier
exports. Caller mutation of the returned JSON can invalidate its hashes.

`output_units.air` covers the entire raw air object. Rotor IDs have label units;
force vectors have N and torque/moment vectors N*m. Actual forward request units
include all injected input fields. Units under
`output_units.rotors.actual_forward_result.outputs` apply ONLY to each retained
forward result's nested `outputs`, never to its entire response envelope.

Stages are `air` then `rotor:<id>` in request order, including `rotor:air` for the
valid rotor ID `air`. Each stage contains `stage`, actual `inputs`,
`inputs_sha256`, and `result_sha256`; it contains no duplicate result arrays.
Each transfer records only the actual density scalar in kg/m^3 from
`air.state.density_kg_m3` to the corresponding injected request's
`density_kg_m3`, with the actual raw-air producer digest and consumer request
digest. Stage rotor result digests cover the entire retained forward envelope.

Digests reuse accepted SHA256 over UTF-8 JSON with sorted keys, compact separators,
`ensure_ascii=False`, and `allow_nan=False`. The outer request digest covers the
accepted snapshot. The outer evaluation digest covers the full outer response
with only its own `evaluation_sha256` field omitted.

| Outcome | Status | Request hash | Evaluation hash |
| --- | --- | --- | --- |
| Preflight invalid before acceptance | `MODEL_INAPPLICABLE` | null | null |
| Different outer evaluation string on bounded exact root | `SOLVER_UNSUPPORTED` | null | null |
| Fully guarded actual core physical/numerical refusal | `MODEL_INAPPLICABLE` | Accepted request | null |
| Ordinary exception or invalid actual component after acceptance | `EXECUTION_FAILED` | Accepted request if available | Full failed response if request hash available |
| All components and assembly arithmetic accepted | `COMPUTED_EXPERIMENTAL` | Accepted request | Full success response |

A hash-generation failure can leave the request hash unavailable, so acceptance
alone does not guarantee a hash. Hashing/export failures cannot guarantee a sealed
response if the hashing/export mechanism itself is unavailable. Hashes identify
data, not execution, accuracy, qualification, or runtime identity.

`rotor_evaluation_count` starts at trusted zero and increments ONLY after a full
component guard accepts its envelope, including a legitimate domain refusal.
A valid second-rotor refusal after a successful first rotor therefore reports 2;
an invalid second result or an ordinary second-call exception reports 1. An
unvalidated returned result is never counted. This is a validated-envelope count,
not an attempted-call count or execution attestation.

Every returned failure is atomic: `outputs` and `output_units` are empty objects,
`stages` and `transfers` are empty lists, and `diagnostics_complete` is false.
Ordinary exception text and partial payloads are not exported. `BaseException`
propagates. A guarded actual physical refusal differs from an invalid component
contract: the former is inapplicable; the latter is execution failure.

## Scope and qualification

Reference air supplies density and gravity only. It supplies no measured weather
or Reynolds/Mach coefficient feedback. The rotor model uses isolated small-angle
attached-linear hover with constant lift slope and drag coefficient. No Reynolds
or Mach polars, stall, loss factors, swirl, ground effect, installed losses, rotor
interference, motor or structural model, dynamics, gyroscopic moments, inertia
evolution, or mission are modeled.

Net loads are static residuals. They establish no trim, control authority,
stability, safety, or aircraft feasibility. Physical validation, numerical
qualification, and runtime identity remain `NOT_ESTABLISHED`; aircraft status and
feasibility remain null. Finite results, unit gates, residuals, hashes, and tests
establish no physical accuracy or qualification. This local experimental contract
makes no complete-PDF, publication, novelty, or 80% accuracy claim.
