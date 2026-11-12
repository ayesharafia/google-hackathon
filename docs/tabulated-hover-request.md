# Experimental tabulated-hover request adapter

This is a local engineering request proposal, not an external standard. The
adapter is available through Python only. It is not registered with an API,
model registry, graph, trim, motor, ledger, or mission path. Existing V102
kernel behavior and integrations are unchanged.

The adapter has three distinct identifiers:

| Field | Value |
| --- | --- |
| `evaluation` | `tabulated_geometry_hover_experimental` |
| `model_id` | `tabulated_geometry_hover_v0_1` |
| `schema_version` | `tabulated_hover_request_v1` |

## Local usage

Import the catalog and evaluator directly from the new module. The catalog
returns fresh nested copies of its fields, units, limits, and interpretation
metadata; modifying one copy does not change subsequent calls.

```python
import json

from physimesh.drone.tabulated_hover_bemt_request import (
    evaluate_tabulated_hover_bemt,
    tabulated_hover_bemt_catalog,
)

catalog = tabulated_hover_bemt_catalog()
request = json.loads(r'''
{
  "evaluation": "tabulated_geometry_hover_experimental",
  "radius_m": 1.0,
  "angular_speed_rad_s": 100.0,
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
  "geometry_source": "synthetic numerical example; true SI radius",
  "geometry_kind": "synthetic",
  "uncertainty_status": "unknown; numerical verification only"
}
''')
response = evaluate_tabulated_hover_bemt(request)
assert response["status"] == "COMPUTED_EXPERIMENTAL"
print(response["outputs"]["thrust_n"], response["output_units"]["thrust_n"])
print(response["request_sha256"], response["evaluation_sha256"])
```

The JSON above is the complete request. The exact root has **13 fields**:
`evaluation` and the kernel's **12 required keyword arguments**. Missing or extra
root fields are refused. There are no defaults for geometry, density, source,
uncertainty, pitch, or any other input.

| Required core keyword | Units / contract |
| --- | --- |
| `radius_m` | m; positive |
| `angular_speed_rad_s` | rad/s; positive |
| `density_kg_m3` | kg/m³; positive |
| `blade_count` | dimensionless builtin integer, 1..32 |
| `root_cutout_m` | m; strictly between zero and `radius_m` |
| `annuli` | dimensionless builtin integer, 1..2048 |
| `lift_curve_slope_per_rad` | 1/rad; positive constant attached-linear slope |
| `profile_drag_coefficient` | dimensionless, nonnegative constant |
| `stations` | builtin list of 2..256 exact station dictionaries |
| `geometry_source` | required nonblank caller text, at most 2000 characters |
| `geometry_kind` | `measured`, `digitized_measurement`, `as_designed`, or `synthetic` |
| `uncertainty_status` | required nonblank caller text, at most 2000 characters |

Each station has exactly `radius_m` (m, nonnegative), `chord_m` (m, positive),
and `blade_angle_rad` (rad, nonnegative). Radii must strictly increase, remain
within the rotor radius, cover the active interval starting at the cutout, and
end exactly at `radius_m`. The first station may be at zero or anywhere up to
the cutout. No hub geometry, endpoint, or missing station property is inferred.
Chord and blade angle are interpolated independently, piecewise linearly at
uniform physical annulus midpoints, without extrapolation. Constant pitch
length is not constant blade angle.

The actual kernel owns physical numeric, geometry, numerical-domain, and work
preflight. Physical numbers require builtin int/float values representable as
finite normal binary64, with zero only where permitted; bool is refused. No
angle validity range is inferred from numerical support.

## Bounded JSON and execution

Before copying, an independent strict input walker accepts only builtin
dict/list/str/int/float/bool/null values. Dictionary keys must be builtin strings.
Subclasses, tuples, custom objects, NaN, infinity, and invalid UTF-8 strings
(including unpaired surrogates) are refused. JSON bool/null support does not
make them valid physical numbers.

| Guard | Input request | Output response |
| --- | --- | --- |
| Root depth | 1 | 1 |
| Maximum depth | 10 | 10 |
| Maximum nodes, including dictionary keys | 8192 | 32768 |
| Maximum items per container | 256 | 2048 |
| Maximum string length | 2000 characters, valid UTF-8 | 2000 characters, valid UTF-8 |
| Maximum integer magnitude bit length | 1023 | 1023 |
| Floats | finite | finite |

Nodes include containers, scalar values, and dictionary keys. Repeated aliases
count on each occurrence. Cycles exceed the depth bound. String length counts
characters, not UTF-8 bytes. The independent output budget accommodates all nine
2048-element annular arrays, 256 stations, and the entire envelope, units, limits,
and hashes. The actual 256-station / 2048-annulus / 32-blade maximum case is
covered by the focused adapter tests; its response exceeds the input node budget
and fits the output budget.

After strict snapshot validation, exact root shape, and supported evaluation,
the adapter hashes the copied request and calls `solve_tabulated_hover` exactly
once. A separate copy of the core arguments protects the hashed snapshot and
caller input from argument mutation. There is no dummy run or second core call.

Before exporting, the adapter requires the exact frozen
`TabulatedHoverSolution` and `GeometryStation` types and fixed fields. It checks
typed metadata, station/source/radius/cutout/annulus binding, builtin finite-normal
numeric tuples and lengths, interpolation, local solidity, retained inflow,
blade/momentum balance, power, normalization, and summaries. Governing checks
use returned values and deterministic arithmetic; they do not solve for a new
inflow or rerun the model.

The local balance identity guard is `abs(blade - momentum) <= 64 * epsilon * S`,
where binary64 `epsilon` is `sys.float_info.epsilon` and `S` is the largest
absolute blade operand before subtraction or momentum term. This operand-scaled
roundoff guard is a numerical return-contract check. It establishes no physical
angle envelope, physical error bound, or numerical accuracy qualification.

## Response, units, and markers

Every response contains `evaluation`, `model_id`, `schema_version`, `status`,
`core_model`, `core_version`, `core_status`, `evidence_level`,
`physical_validation`, `numerical_qualification`, `runtime_identity`,
`aircraft_status`, `feasibility`, `diagnostics_complete`, `reasons`,
`limitations`, `outputs`, `output_units`, `limits`, `request_sha256`, and
`evaluation_sha256`.

On completed validated output, the actual dataclass markers move once:

| Actual dataclass field | Envelope field | Required actual value |
| --- | --- | --- |
| `model` | `core_model` | `tabulated_geometry_hover_experimental` |
| `version` | `core_version` | `0.1` |
| `status` | `core_status` | `COMPUTED_EXPERIMENTAL` |
| `physical_validation` | `physical_validation` | `NOT_ESTABLISHED` |

These fields are removed from `outputs`; the adapter does not export duplicate
dataclass markers. `core_model`, `core_version`, and `core_status` are null on
failure. The envelope's physical/numerical/runtime qualifiers always remain
`NOT_ESTABLISHED`, evidence remains `unverified`, and `aircraft_status` and
`feasibility` remain null. `diagnostics_complete` is true only after all completed
result checks pass. All actual remaining dataclass values are copied to plain
JSON, including lists for stations and annular arrays.

`output_units` covers every output key. Array units apply to every element;
the nested `stations` unit dictionary applies to every station. `text` and
`label` designate nonphysical metadata. The catalog also labels the moved
envelope markers as labels.

| Output field(s) | Unit |
| --- | --- |
| `radius_m`, `root_cutout_m`, `radii_m`, `chord_m` | m |
| `geometry_source`, `uncertainty_status` | text |
| `geometry_kind` | label |
| `stations` | per station: `radius_m`: m; `chord_m`: m; `blade_angle_rad`: rad |
| `blade_angle_rad`, `approx_inflow_angle_rad`, `approx_angle_of_attack_rad` | rad |
| `radial_fraction`, `local_solidity`, `inflow_ratio` | 1 |
| `thrust_coefficient`, `blade_thrust_coefficient` | 1 |
| `induced_power_coefficient`, `profile_power_coefficient`, `shaft_power_coefficient` | 1 |
| `thrust_n` | N |
| `shaft_power_w` | W |
| `shaft_torque_nm` | N*m |
| `thrust_balance_coefficient`, `local_balance_coefficient`, `max_local_balance_coefficient` | 1 |
| `annuli` | 1 |

Solidity is `B*c(r)/(pi*R)`, using rotor radius. With rotor area `A=pi*R²`
and tip speed `U=Omega*R`, coefficients use `CT=T/(rho*A*U²)` and
`CP=P/(rho*A*U³)`, and torque is `Q=P/Omega`. Local residuals are blade minus
momentum integrands before annular width; global residuals compare summed
coefficients. Zero blade angle gives zero inflow, thrust, and induced power;
nonzero profile drag may still consume mechanical shaft power. Shaft power
is not electrical input power.

## Status and nullable digest semantics

| Condition | Status | Core calls | Request hash | Evaluation hash |
| --- | --- | --- | --- | --- |
| Invalid strict JSON, root shape, or evaluation type | `MODEL_INAPPLICABLE` | 0 | null | null |
| Exact strict root with different evaluation string | `SOLVER_UNSUPPORTED` | 0 | null | null |
| Actual core input/geometry/numerical-domain refusal | `MODEL_INAPPLICABLE` | 1 | copied-input digest | null |
| Actual completed output passes all checks | `COMPUTED_EXPERIMENTAL` | 1 | copied-input digest | actual-response digest |
| Unexpected ordinary core exception or invalid returned contract/export | `EXECUTION_FAILED` | 1 | copied-input digest | actual failure-response digest |
| Unexpected snapshot/preparation exception | `EXECUTION_FAILED` | 0 | digest if already available, otherwise null | failure-response digest only if request digest exists |
| `BaseException`, including `KeyboardInterrupt`/`SystemExit` | propagates | depends on stage | no returned envelope | no returned envelope |

Core input/numerical-domain refusals include `ValueError`, `TypeError`, and
`ArithmeticError`. Unexpected ordinary exceptions and returned-contract failures
are execution failures. Every returned failure has empty `outputs` and
`output_units`, false `diagnostics_complete`, and null core markers. Partial
results and exception text are not exported.

`request_sha256` uses the accepted `provenance.sha256_record` helper on the
strict copied input before execution. `evaluation_sha256` uses that same helper
on the actual completed or execution-failed response, including the nonnull
request digest and omitting `evaluation_sha256` itself. Encoding is compact,
sorted-key JSON, `ensure_ascii=False`, `allow_nan=False`, encoded as UTF-8 and
hashed with SHA-256. A null hash means no digest is available. A request digest
on a core refusal records the input; it does not claim a completed evaluation.
Digests establish data binding, not runtime identity or physical correctness.

## Interpretation limits

Geometry source/kind and uncertainty labels are caller assertions, not trusted
or independently verified provenance. Source strings are not fetched. Unknown
uncertainty stays unknown; classification does not upgrade evidence.

The kernel extends geometry representation for an experimental isolated-hover,
small-angle, attached-linear-lift closure. It provides no Reynolds-dependent
polars, stall, swirl, tip/root loss, Mach/compressibility, non-hover flight,
ground/interference effects, structural validation, electrical efficiency, or
aircraft qualification. Finite answers, balances, refinement, source labels,
and hashes establish no new physical accuracy, runtime identity, physical
validation, or aircraft feasibility.
