# Reference-air tabulated hover thrust target

This separate V110 local experimental composition supplies reference dry-air density to the accepted tabulated hover thrust target. It targets computed isolated-hover thrust. The density describes a reference atmosphere, not measured weather. Source declarations, geometry classification and unknown uncertainty remain unverified caller assertions.

The direct module is `physimesh.drone.reference_air_tabulated_hover_thrust_target`. Its entry points are `evaluate_reference_air_tabulated_hover_thrust_target(request)` and `reference_air_tabulated_hover_thrust_target_catalog()`. This addition makes no API, graph, rotor assembly, trim, mission or identity changes.

## Closed request

Every field below is explicit and required. Every request object has closed fields, including each station. The target template contains exactly the accepted V108 request fields, including its evaluation declaration. Its rotor template forbids both `density_kg_m3` and `angular_speed_rad_s`, even if a caller supplies the same density that reference air would produce. There are no defaults or speed-bracket expansion.

```json
{
  "evaluation": "reference_air_tabulated_hover_thrust_target_experimental",
  "air": {
    "altitude_m": 0,
    "altitude_kind": "geometric"
  },
  "target_template": {
    "evaluation": "tabulated_geometry_hover_thrust_target_experimental",
    "rotor_template": {
      "evaluation": "tabulated_geometry_hover_experimental",
      "radius_m": 1.0,
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
      "geometry_source": "synthetic numerical fixture, revision 1; true SI radius",
      "geometry_kind": "synthetic",
      "uncertainty_status": "unknown; numerical verification only"
    },
    "target_thrust_n": 20.0,
    "angular_speed_bracket_rad_s": [50.0, 150.0],
    "absolute_thrust_tolerance_n": 0.000001,
    "max_evaluations": 32
  }
}
```

`altitude_m` must be an explicit finite builtin integer or float from 0 through 30000 m, inclusive. `altitude_kind` must be `geometric` or `geopotential`. Booleans are not numeric inputs. Geometry scalar and station values must have builtin numeric types. Physical geometry validity belongs to the actual accepted inverse and forward model, rather than to a preliminary calculation with invented density or speed.

`geometry_source`, `geometry_kind` and `uncertainty_status` must be nonblank strings. Geometry kind must be `measured`, `digitized_measurement`, `as_designed` or `synthetic`. These classifications confer no evidence upgrade. No sources are fetched.

Target, absolute thrust tolerance and both bracket endpoints must be finite positive normal builtin numbers. Tolerance must be smaller than target. The bracket is exactly a two-item builtin list with `0 < lo < hi`. The caller's target, tolerance, bracket and evaluation budget pass through unchanged. Counts must be builtin integers: annuli 1..512, blades 1..32, stations 2..256 and maximum evaluations 2..64. The product `max_evaluations * annuli` must not exceed 32768.

## Actual component results

Strict bounded builtin JSON admission happens before copying. Closed shapes, numeric types, declarations, classifications, controls and work counts are checked before any component call. Foreign objects and container subclasses are rejected without conversion or copy hooks.

`reference_air_properties(**deepcopied_actual_air_request)` runs once. The accepted V106 `_validate_air(actual_air, actual_air_snapshot)` checks the actual frozen air and atmosphere-state dataclasses, their types and markers, and the accepted hydrostatic and transport arithmetic. No air evaluation is repeated. The validated raw air JSON and its actual density are immediately detached before any inverse call. No dataclass is reconstructed to pass a guard.

A copied actual inverse request receives only the validated scalar `rotor_template.density_kg_m3`. Its original injected snapshot is retained separately from the arguments sent to the inverse. An independent V108 input walk applies to that request. The actual `evaluate_tabulated_hover_thrust_target` runs once; it owns its actual forward trials, up to the caller's budget and at most 64 calls. One inverse call does not mean one forward core call. Work remains bounded by 32768 evaluation-annuli.

The inverse checks both endpoints, including when the low endpoint already meets tolerance. It then either selects an acceptable endpoint, performs bounded bisection, or returns an atomic failure. It adds no bracket expansion or fallback target.

The actual returned inverse JSON undergoes its strict bounded output walk and is immediately deep-copied before further work. The accepted V109 `validate_tabulated_hover_thrust_target_result(actual_inverse_snapshot, injected_actual_snapshot)` must return `None`. This pure guard makes no inverse, forward or air call and creates no substitute result envelope. The full selected forward response and the inverse provenance remain unchanged inside the retained actual inverse JSON.

## Independent resource limits

Root depth is 1. Nodes include values and dictionary keys; repeated aliases count on each JSON occurrence. Cycles exceed the depth limit. Every boundary allows only builtin JSON values, strings of at most 2000 Unicode characters with strict UTF-8 encoding, integers of at most 1023 bits and finite floats.

| JSON boundary | Maximum nodes including keys | Maximum depth | Maximum items per container |
| --- | ---: | ---: | ---: |
| Outer request | 32768 | 12 | 256 |
| Actual injected inverse request | 16384 | 11 | 256 |
| Each actual forward request | 8192 | 10 | 256 |
| Each full actual forward response | 32768 | 10 | 2048 |
| Full actual inverse response | 65536 | 16 | 2048 |
| Outer response | 131072 | 20 | 2048 |

The outer response budget accommodates the actual full inverse, its selected full forward payload, and the stage input requests. It does not duplicate component result arrays. The maximum shape of 512 annuli, 256 stations and a caller budget of 64 is covered by an actual endpoint-success test. A blade count of at most 32 is admitted. Separate child budgets remain in the catalog; passing the outer walk does not bypass them.

## Outputs, units and data bindings

Success has `diagnostics_complete: true`, `evidence_level: "unverified"`, physical validation, numerical qualification and runtime identity all `"NOT_ESTABLISHED"`, and `aircraft_status` and `feasibility` both null.

`outputs.air` contains the actual validated raw air exactly once. `outputs.target` contains the actual full inverse JSON exactly once, including its unchanged selected full forward response. The outer response has no duplicate full-result payloads in its stages.

`output_units.air` uses the accepted V106 full raw-air units, covering the atmosphere state and all transport and reference-property fields. `output_units.target` is the actual inverse `output_units` and applies **only to `outputs.target.outputs`**, not the full inverse envelope. The selected forward units retain their narrower scope: `outputs.target.outputs.actual_forward_result.outputs`. The inverse's `actual_forward_request` units describe that request separately.

The ordered `stages` list has `air` and `target` records. Each contains only `stage`, actual `inputs`, `inputs_sha256` and `result_sha256`. Each result digest covers the corresponding actual full result: raw air or full inverse JSON, including the inverse's own evaluation digest. No full result is copied into a stage.

The sole `transfers` record binds:

- `from_stage: "air"`, `from_field: "state.density_kg_m3"`;
- `to_stage: "target"`, `to_field: "rotor_template.density_kg_m3"`;
- the actual validated density scalar as `value`, with `unit: "kg/m^3"`;
- `producer_result_sha256` of the full actual raw air and `consumer_request_sha256` of the full actual injected inverse request.

Caller data, the original injected request and component arguments have separate snapshots. The validated raw air and density are detached before the inverse can mutate a retained air object. The inverse result is detached before validation can expose it to later changes of a retained producer object. Returned snapshots are plain mutable JSON, not immutable objects. Editing a returned response invalidates its data hashes.

## Status, reason, count and hash matrix

Every non-success response has empty `outputs`, `output_units`, `stages` and `transfers`, and `diagnostics_complete: false`. No partial component response or private exception text is exported. `inverse_evaluation_count` is always a builtin integer from 0 through 64. Before any accepted inverse result, it is 0, including after an invalid inverse response, however plausible that response's reported count appears.

In the table, "request" means the actual accepted copied outer request digest, and "evaluation" means a digest of the entire outer response omitting only `evaluation_sha256`.

| Condition | Status | Exact sole reason, or empty reasons | Count | Request hash | Evaluation hash |
| --- | --- | --- | --- | --- | --- |
| Another outer evaluation string after bounded root admission | `SOLVER_UNSUPPORTED` | `Unsupported evaluation.` | 0 | null | null |
| Invalid bounded request | `MODEL_INAPPLICABLE` | `Invalid bounded reference-air target request.` | 0 | null | null |
| Ordinary request snapshot exception | `EXECUTION_FAILED` | `Request snapshot failed.` | 0 | null | null |
| Actual validated inverse success | `COMPUTED_EXPERIMENTAL` | `[]` | Accepted actual count, 2..budget | request | evaluation |
| Actual validated endpoint range refusal | `TARGET_NOT_BRACKETED` | `Actual target is outside the observed endpoint thrust range.` | Accepted actual count, exactly 2 | request | evaluation |
| Actual validated budget exhaustion | `ITERATION_LIMIT` | `Actual target forward evaluation budget exhausted.` | Accepted actual count, exactly budget | request | evaluation |
| Actual validated representable midpoint limit | `NUMERICAL_LIMIT` | `Actual target reached a representable numerical limit.` | Accepted actual count, 2..budget-1 | request | evaluation |
| Actual validated physical or numerical domain refusal | `MODEL_INAPPLICABLE` | `Actual target refused the physical or numerical domain.` | Accepted actual count, 1..budget | request | null |
| Actual validated inverse execution failure | `EXECUTION_FAILED` | `Reference-air target execution or returned contract failed.` | Accepted actual count, 0..budget | request | evaluation |
| Invalid actual air or inverse, or ordinary component/guard exception | `EXECUTION_FAILED` | `Reference-air target execution or returned contract failed.` | 0 before an accepted inverse result | request | evaluation |
| Ordinary exception after actual inverse guard acceptance | `EXECUTION_FAILED` | `Reference-air target execution or returned contract failed.` | Already accepted actual count | request | evaluation |

A fault before the accepted request digest can be produced leaves both hashes null. `BaseException` propagates instead of becoming a response. Ordinary exception text is never included.

Hashes use the accepted canonical SHA256 encoding: sorted compact UTF-8 JSON, `ensure_ascii=False`, `allow_nan=False`. `request_sha256` binds the actual copied outer request, not the density-injected child request. Each evaluation digest omits only its own field. Domain refusal has no outer evaluation hash even when its accepted request has a hash. Pre-admission failures have neither hash.

Failure count bounds are necessary consistency checks on the accepted actual inverse envelope, not execution attestation. A malformed or forged response cannot provide a trusted count. The narrower V109 normal deterministic admission contract excludes inverse infrastructure copy/hash fault envelopes. Such unexpected actual inverse envelopes fail the pure guard and become atomic outer `EXECUTION_FAILED` with count 0. They cause no model rerun or fabricated envelope to satisfy validation.

## Provenance and scientific limits

Intermediate inverse trace `full_actual_result_sha256` values are **FORMAT-ONLY producer-reported provenance**. Their intermediate full response payloads are absent, so their content cannot be independently verified. A different well-formed intermediate digest remains acceptable after consistent inverse rehashing. The selected full forward response is retained, content-verified and bound to its selected trace digest by the accepted V109 guard. The outer response makes no stronger attestation.

Density transfer provides no Reynolds or Mach feedback, polars, stall, swirl, losses, compressibility correction, motor or structural limits, attainable RPM, physical trim or aircraft/mission feasibility. Attached-linear small-angle isolated hover remains experimental, with angle validity and physical accuracy not established. Geometry representation, residual tolerance and finite values establish no physical validation, numerical qualification or runtime identity. Unknown uncertainty stays unknown. There is no 80 percent accuracy, novelty, publication or qualification claim.

The fresh catalog exposes closed request fields, units, all separate budgets, work limits, bindings, status reasons, hash rules, snapshot boundaries and limitations. Mutating a returned catalog does not alter a later catalog or evaluation.
