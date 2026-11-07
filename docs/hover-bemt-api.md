# Experimental hover BEMT API

`POST /api/drone/hover-bemt/evaluate` evaluates one explicitly supplied rotor using an experimental, isolated-hover, small-angle blade element momentum theory (BEMT) model with attached linear lift. Send `Content-Type: application/json`.

Physical validation is **`NOT_ESTABLISHED`** and the evidence level is **`unverified`**. Every evaluation response has `aircraft_status: null` and `feasibility: null`. A computed result does not establish a physical operating envelope, aircraft readiness, or feasibility. Small-angle applicability is not established; numerical acceptance and balance diagnostics do not establish a physical angle threshold.

The endpoint is stateless and read-only. It does not mutate a project, automatically select catalog components or properties, establish aircraft strength or structural qualification, or deploy anything.

## Authentication

For local use, use your local server's base URL and configured authentication mode. For hosted API access, send `Authorization: Bearer YOUR_TOKEN` with a token authorized for that deployment. `YOUR_TOKEN` below is a placeholder, not a credential.

Browser requests using a session cookie must satisfy the deployment's CSRF protection and same-origin requirements. A session cookie alone does not replace those checks. Authentication, cookie handling, and CSRF are enforced by the deployment; this endpoint does not define a separate login or CSRF-token format.

## Request

All keys in the following table are required, and extra keys are forbidden. There are no implicit defaults. In particular, `pitch_root_rad` must be present even when its value is `null`.

| Key | JSON type / units | Meaning and constraints |
| --- | --- | --- |
| `evaluation` | string | Exactly `isolated_hover_bemt_experimental`. |
| `radius_m` | number, m | Positive rotor radius, `R`. |
| `angular_speed_rad_s` | number, rad/s | Positive angular speed, not RPM. |
| `density_kg_m3` | number, kg/m³ | Positive air density. |
| `blade_count` | integer, dimensionless | Integer from `1` through `32`, inclusive. |
| `chord_m` | number, m | Positive blade chord. |
| `lift_curve_slope_per_rad` | number, rad⁻¹ | Positive slope of the attached linear-lift model. |
| `profile_drag_coefficient` | number, dimensionless | Profile drag coefficient; must satisfy the core solver's coefficient domain. |
| `pitch_tip_rad` | number, rad | Tip pitch; must satisfy the core solver's numerical domain. |
| `root_cutout_fraction` | number, dimensionless | Active inner radius divided by `R`, denoted `r0`; strictly `0 < r0 < 1`. |
| `twist_law` | string | `constant`, `hyperbolic`, or `linear`. |
| `annuli` | integer, dimensionless | Number of radial annuli; `1` through `2048`, inclusive. |
| `pitch_root_rad` | number or null, rad | Required finite root pitch for `linear`; explicitly `null` for the older `constant` and `hyperbolic` laws. |
| `property_source` | string | Nonblank literal declaration, at most 2000 characters. Unverified. |
| `applicability_declaration` | string | Nonblank literal declaration, at most 2000 characters. Unverified. |

Numbers must be finite JSON numbers. Numeric strings, booleans, NaN, and infinities are rejected. `blade_count` and `annuli` must be JSON integers: `2.0` is not a substitute for `2`. Extremely large integers can also fail numeric validation. Only `pitch_root_rad` accepts `null`.

The core solver applies further domain and numerical guards after request validation. Pitch endpoints and profile drag are nonnegative; other physical numeric parameters are positive. The active cutout is strictly between zero and one. Passing numerical guards does not validate the physics.

For `linear`, `pitch_root_rad` anchors pitch at the active cutout, `r/R = r0`, and `pitch_tip_rad` anchors it at `r/R = 1`; pitch varies linearly between those anchors. The root anchor is the start of the modeled active blade span, not a physical hub location or a pitch specified at zero radius. There is no height input; ground effects are not modeled.

Declarations are echoed as supplied. They are not verified citations or applicability checks, and they cannot promote the evidence level or establish validation.

## Example request

This complete request uses synthetic, unverified values: radius 0.5 m, angular speed 300 rad/s, density 1.225 kg/m³, two blades, and eight annuli. It illustrates the request contract, not a qualified rotor design.

```json
{
  "evaluation": "isolated_hover_bemt_experimental",
  "radius_m": 0.5,
  "angular_speed_rad_s": 300,
  "density_kg_m3": 1.225,
  "blade_count": 2,
  "chord_m": 0.04,
  "lift_curve_slope_per_rad": 5.7,
  "profile_drag_coefficient": 0.01,
  "pitch_tip_rad": 0.12,
  "root_cutout_fraction": 0.2,
  "twist_law": "linear",
  "annuli": 8,
  "pitch_root_rad": 0.16,
  "property_source": "Synthetic example properties; unverified.",
  "applicability_declaration": "Synthetic isolated-hover example; applicability unverified and physical validation not established."
}
```

Save the example JSON as `hover-bemt-request.json`, replace `YOUR_HOST` with your hosted base host, and supply your own token in place of the placeholder:

```sh
curl --request POST 'https://YOUR_HOST/api/drone/hover-bemt/evaluate' \
  --header 'Content-Type: application/json' \
  --header 'Authorization: Bearer YOUR_TOKEN' \
  --data-binary @hover-bemt-request.json
```

For `constant` or `hyperbolic`, change `twist_law` accordingly and retain the `pitch_root_rad` key with the value `null`.

## Responses and errors

Check both the HTTP status and the response's `status` field. HTTP 200 means the evaluation request was processed; it does not mean the model is applicable or physically validated.

| Condition | HTTP status | Behavior |
| --- | --- | --- |
| Missing/extra keys, wrong JSON types, invalid nulls, nonfinite numbers, or blank/oversized declarations | `422` | Generic response: `{"detail":"Invalid hover BEMT request."}`; no evaluation envelope. |
| Well-typed but unsupported `evaluation` string | `200` | `status: "SOLVER_UNSUPPORTED"`; `outputs` and `output_units` are empty objects. |
| Inputs outside the core's supported input or numerical domain, including an unsupported twist law | `200` | `status: "MODEL_INAPPLICABLE"`; `outputs` and `output_units` are empty objects. |
| Core returns a solution | `200` | `status` comes from the core, with computed `outputs` and `output_units`; physical validation remains unestablished. |

Core input and numerical failures receive the generic reason `Request is outside the core solver's supported input or numerical domain.` Clients should not expect field-specific solver diagnostics or interpret this reason as a physical applicability assessment. Deployment authentication and security checks can reject a request before evaluation.

Evaluation envelopes contain:

| Field | Meaning |
| --- | --- |
| `model_id` | `isolated_hover_small_angle_bemt_v1` |
| `schema_version` | `hover_bemt_request_v1` |
| `status` | Evaluation outcome; inspect it even for HTTP 200. |
| `physical_validation` | Always `NOT_ESTABLISHED`. |
| `evidence_level` | Always `unverified`. |
| `aircraft_status`, `feasibility` | Always JSON `null`. |
| `reasons` | Array of outcome explanations; empty for a returned core solution. |
| `limitations`, `sources` | Model limitations and reference links. References do not establish validation of this implementation or request. |
| `inputs` | Parsed request values, including declarations and explicit nulls. |
| `outputs`, `output_units` | Computed values and their units, or empty objects for unsupported/inapplicable results. |
| `input_sha256` | Integrity hash of the parsed `inputs`, not the raw HTTP body. |
| `evaluation_sha256` | Integrity hash of the evaluation envelope before adding `evaluation_sha256` itself. |

The hashes provide integrity metadata only. They do not validate properties, declarations, applicability, physical accuracy, or feasibility.

When a solution is returned, output names and units are:

| Output | Unit |
| --- | --- |
| `radial_fraction`, `inflow_ratio` | Dimensionless (`1`) |
| `pitch_rad`, `approx_inflow_angle_rad`, `approx_angle_of_attack_rad` | rad |
| `thrust_coefficient`, `blade_thrust_coefficient` | Dimensionless (`1`) |
| `induced_power_coefficient`, `profile_power_coefficient`, `shaft_power_coefficient` | Dimensionless (`1`) |
| `thrust_n` | N |
| `shaft_power_w` | W |
| `shaft_torque_nm` | N*m |
| `thrust_balance_coefficient`, `max_local_balance_coefficient` | Dimensionless (`1`) |
| `annuli` | Dimensionless (`1`) |

Radial quantities are represented as JSON arrays when returned as radial sequences by the core. Approximate angles and balance diagnostics are model outputs, not a certified operating envelope or physical-validation evidence.

## Model omissions

The model omits rotor loss factors and swirl; airfoil polar tables, stall, Reynolds-dependent polars, and Mach/compressibility effects; non-hover flight; ground effects; rotor/aircraft interference; and electrical efficiency. Shaft power is mechanical shaft power, not electrical input power. These outputs do not establish aircraft strength, structural qualification, aircraft status, or feasibility.
