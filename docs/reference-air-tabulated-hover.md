# Reference air to tabulated hover - V106

This separate local workflow composes the accepted reference dry-air evaluator
with the accepted V105 tabulated-hover request adapter. It adds no graph, rotor
assembly, trim, mission or API integration and changes no accepted identities.
The contract is a local engineering proposal, not an external standard.

Call `evaluate_reference_air_tabulated_hover(request)` from
`physimesh.drone.reference_air_tabulated_hover`. The fresh
`reference_air_tabulated_hover_catalog()` exposes fields, units, bounds,
bindings, limitations and refusal semantics.

## Exact request

```json
{
  "evaluation": "reference_air_tabulated_hover_experimental",
  "air": {"altitude_m": 10000.0, "altitude_kind": "geometric"},
  "rotor_template": {
    "evaluation": "tabulated_geometry_hover_experimental",
    "radius_m": 1.0,
    "angular_speed_rad_s": 100.0,
    "blade_count": 2,
    "root_cutout_m": 0.25,
    "annuli": 24,
    "lift_curve_slope_per_rad": 5.7,
    "profile_drag_coefficient": 0.01,
    "stations": [
      {"radius_m": 0.0, "chord_m": 0.05, "blade_angle_rad": 0.08},
      {"radius_m": 1.0, "chord_m": 0.05, "blade_angle_rad": 0.08}
    ],
    "geometry_source": "synthetic numerical example",
    "geometry_kind": "synthetic",
    "uncertainty_status": "unknown"
  }
}
```

Every shown field is mandatory. Root, air, template and station objects are
closed. `density_kg_m3` must be absent from the template, even when its value
would equal reference density. No altitude convention, geometry, weather,
coefficient or density defaults are supplied.

Air altitude is an exact builtin int or float, excluding bool and subclasses,
finite and in 0..30000 m. Convention is exactly `geometric` or `geopotential`.
Rotor numeric literals also require builtin int/float, excluding bool.
`annuli` is a builtin int in 1..2048; `blade_count` is a builtin int in 1..32;
`stations` is a builtin list of 2..256 exact numeric station objects.
Source and uncertainty declarations are nonblank strings. Geometry kind is
`measured`, `digitized_measurement`, `as_designed` or `synthetic`.
Source claims, classification and uncertainty remain unverified caller assertions.

All geometry lengths are m; angular speed is rad/s; blade angle is rad; lift
slope is 1/rad. Counts and drag coefficient are dimensionless (`1`).
Declarations use `text` or `label`, which are nonphysical units.

## Execution and bounds

The outer strict builtin JSON walk runs before copying. It counts every value
and key; aliases count on each occurrence. Foreign objects and subclasses are
rejected without calling their conversion or copy hooks. Cycles exceed the
depth bound. Strings must encode as strict UTF8.

| Budget | Depth, root = 1 | Nodes including keys | Items per container |
| --- | ---: | ---: | ---: |
| Outer input | 11 | 16384 | 256 |
| Injected V105 input, independent walk | 10 | 8192 | 256 |
| Actual V105 output | 10 | 32768 | 2048 |
| Outer output, independent walk | 16 | 65536 | 2048 |

All walks allow at most 2000 Unicode characters per string, 1023 bits per
integer and finite floats only. The character bound is not a byte bound.
The full maximum station/annuli/blade shape fits the separate outer output
budget. This feature supplies no HTTP byte budget.

Preflight checks exact fields, JSON resources, numeric types, work counts,
source classification and declarations before either evaluator. It does not
duplicate core physical geometry or numerical domain validation. For example,
a negative chord can pass structural preflight, evaluate actual air once and
then receive the actual child domain refusal.

For an admitted request:

1. Call imported `reference_air_properties(**deepcopy(actual_air_request))`
   exactly once.
2. Validate the actual exact frozen `ReferenceAirProperties` and nested
   `StandardAtmosphereState`, including exact dataclass fields, instance fields,
   supported markers and qualifiers, before exporting the actual `asdict`.
3. Bind requested altitude/convention with the accepted `_validate_state`, then
   bind pressure, temperature and density to accepted hydrostatic arithmetic:
   base 101325 Pa and 288.15 K; Earth radius 6356750 m; gravity 9.80665 m/s^2;
   gas constant 8314.32/28.9644 J/(kg K). Ordered geopotential layers are
   0..11000 m at -0.0065 K/m, 11000..20000 m isothermal, and 20000..32000 m at
   0.001 K/m, stopping at the first inclusive upper boundary. Conversion and
   arithmetic order match the accepted atmosphere.
4. Bind geometric altitude, Sutherland viscosity (mu0 1.716e-5 Pa*s,
   T0 273.15 K, C 110.33333 K), ideal dry-air sound speed (gamma 1.4), and
   inverse-square gravity to the accepted formulas. Legacy C 110.4 is rejected.
   These are contract checks, with no second atmosphere/property evaluator.
5. Inject actual validated `air.state.density_kg_m3` into a separate copied
   child request, independently walk that request and call the actual V105
   adapter exactly once. The actual hover core runs once inside that adapter.
6. Validate the actual full builtin JSON child envelope: exact fields, supported
   model/schema/status/markers, unqualified evidence, null feasibility, reasons,
   limitations, limits, diagnostics, units, request hash and evaluation hash.
   For success, pass its actual `outputs` and actual injected snapshot to
   V105 `_validate_output_values`. No dataclass, envelope or result is fabricated
   for that helper, and no model is rerun for validation.

## Response, units and provenance

The closed outer response has exactly `evaluation`, `schema_version`, `status`,
`evidence_level`, `physical_validation`, `numerical_qualification`,
`runtime_identity`, `aircraft_status`, `feasibility`, `diagnostics_complete`,
`reasons`, `limitations`, `limits`, `request_sha256`, `evaluation_sha256`,
`outputs`, `output_units`, `stages`, `transfers`.

On success, status is `COMPUTED_EXPERIMENTAL`, schema is
`reference_air_tabulated_hover_v1`, reasons are empty and diagnostics complete
is true. `outputs.air` is the actual exported full air raw object.
`outputs.rotor` is the actual full V105 response, retained unchanged, including
its own request/evaluation digests. Each full result appears only once.

`output_units.air` covers every raw air field, including every nested state
field: altitude m, pressure Pa, temperature K, density kg/m^3, viscosity Pa*s,
sound speed m/s, gravity m/s^2; identifiers, conventions and qualifiers are
`label`, and viscosity/sound/gravity descriptions are `text`.
`output_units.rotor` equals the actual child's `output_units` and applies only
to `outputs.rotor.outputs`. It does not describe the whole child envelope.
Array units apply to each element and station units to each station object.
Child thrust is N, shaft mechanical power W and torque N*m; coefficients,
solidity, radial fraction and inflow ratio are dimensionless.

`stages` contains air then rotor, each with exactly `stage`, actual `inputs`,
`inputs_sha256` and actual `result_sha256`. The air result digest hashes the
actual full raw air object; the rotor result digest hashes the actual full
child response, including its evaluation digest. No full results or annular
arrays are duplicated in stages.

The sole transfer contains `from_stage: air`, `from_field: state.density_kg_m3`,
`to_stage: rotor`, `to_field: density_kg_m3`, the actual scalar `value`,
`unit: kg/m^3`, `producer_result_sha256` and `consumer_request_sha256`.
It links the actual air result digest to the actual injected rotor request
digest. Viscosity, sound and gravity do not feed rotor coefficients.

All hashes use accepted provenance SHA256 of sorted compact strict UTF8 JSON,
`ensure_ascii=False`, `allow_nan=False`. The outer request digest describes
the accepted copied outer request. Outer evaluation hashing omits only its
own `evaluation_sha256` field. Child hashes are checked, never manufactured or
replaced. Digests bind data; they do not prove evaluator identity, successful
physical validation or accuracy.

| Outcome | Request digest | Evaluation digest |
| --- | --- | --- |
| Preflight invalid: `MODEL_INAPPLICABLE` | null | null |
| Different outer evaluation: `SOLVER_UNSUPPORTED` | null | null |
| Actual exact child domain refusal: `MODEL_INAPPLICABLE` | accepted request | null |
| Completed: `COMPUTED_EXPERIMENTAL` | accepted request | completed response |
| `EXECUTION_FAILED` after acceptance | accepted request if available | failed response if request digest available |
| Snapshot failure before acceptance: `EXECUTION_FAILED` | null | null |

A legitimate child domain refusal must have its exact expected atomic
MODEL_INAPPLICABLE envelope, request hash and null evaluation hash. Child
unexpected failure, forgery or invalid contract becomes outer
`EXECUTION_FAILED`. Every outer failure clears `outputs`, `output_units`,
`stages` and `transfers` and leaves diagnostics incomplete, including failures
after air has executed. Ordinary exceptions are sanitized without exception
text; `BaseException` propagates. Caller requests are untouched.

## Interpretation

Evidence remains `unverified`. Physical validation, numerical qualification
and runtime identity remain `NOT_ESTABLISHED`; aircraft status and feasibility
are null. Reference dry air is not local measured weather or aircraft evidence.
The atmosphere and transport assumptions are inherited from
[reference air properties](reference-air-properties.md) and
[standard atmosphere](standard-atmosphere.md).

Density-only coupling does not correct lift or drag coefficients with Reynolds
number or Mach number. This initial feature reports no Re/Mach diagnostics and
adds no polars, stall, swirl, tip/root losses or compressibility treatment.
Attached-linear small-angle hover assumptions and unknown angle validity
remain. Zero angle produces zero lift/inflow/thrust and induced power while
profile drag may still consume mechanical power. No electrical efficiency is
modeled. Finite numbers, balance checks and data hashes establish no physical
accuracy, new qualification, 80 percent accuracy or novelty claim.
