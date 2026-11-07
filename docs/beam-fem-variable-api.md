# Experimental variable-inertia beam API

`POST /api/drone/beam-fem-variable/evaluate` calls
[`evaluate_variable_beam(request)`](../src/physimesh/drone/beam_fem_variable_request.py).
See the [router](../src/physimesh/api/beam_fem_variable.py) and [beam model notes](beam-fem-variable.md).

Authentication is required in hosted and nonhosted modes; existing CSRF rules apply. Hosted allowlisting covers this exact path only.
The evaluation is stateless: no artifact, project, or job writes, or catalogue/selection changes.

Run against a configured application instance with `BASE_URL` set to its origin and
`AUTH_CURL_CONFIG` pointing to a local curl config supplying the existing authentication
and any required CSRF headers/cookies. No new authentication header is defined here.

```bash
curl --config "$AUTH_CURL_CONFIG" \
  --request POST "$BASE_URL/api/drone/beam-fem-variable/evaluate" \
  --header 'Content-Type: application/json' --data-binary @- <<'JSON'
{
  "evaluation": "variable_beam_fem_experimental",
  "length_m": 2,
  "E_pa": 70000000000,
  "second_moments_m4": [0.000001, 0.00000125, 0.0000015],
  "nodes_m": [0, 1, 2],
  "outer_fibre_m": 0.01,
  "tip_force_n": 10,
  "uniform_load_n_m": 0,
  "ramp_load_root_n_m": 0,
  "ramp_load_tip_n_m": 0,
  "tip_moment_n_m": 0,
  "probes": [
    {"element_index": 0, "local_coordinate": 0.5},
    {"element_index": 1, "local_coordinate": 1}
  ],
  "property_source": "Unverified supplier values",
  "applicability_declaration": "Experimental static cantilever only"
}
JSON
```

Every shown field is required, with no defaults; extra root or probe keys are forbidden.
Numbers must be finite builtin `int`/`float`, excluding booleans, strings, subclasses,
NaN, infinity, and gigantic integers. Arrays must be builtin lists of 2..65 numbers;
only these lists become tuple core arguments. The core requires equal lengths,
positive length/E/inertias/outer-fibre distance, nonnegative loads, and strictly
increasing nodes starting at 0 and ending exactly at `length_m`.
Core limits remain: minimum element length ≥ `length_m * 2**-20`, element-length
ratio ≤ 1024, inertia ratio ≤ 1e12, and finite-normal arithmetic guards.
`probes` is a builtin list of 1..128 exact objects: `element_index` is a builtin
integer (not `2.0`), checked by the core against the element count;
`local_coordinate` is finite numeric in [0,1]. Both declaration fields are literal,
nonblank builtin strings of at most 2000 characters; they are not evidence.
Text is not evaluated, fetched as a URL, or rendered as HTML. Requests are unmutated.

Structural validation failures return HTTP 422 with exactly
`{"detail":"Invalid variable beam request."}`; numeric strings are not coerced.
Shape-valid requests outside the core domain return HTTP 200 with `MODEL_INAPPLICABLE`;
unsupported `evaluation` returns `SOLVER_UNSUPPORTED`. Refusals have generic `reasons`
and empty `outputs` and `output_units`. All probes complete before success; no partial output.

Success has `status: "COMPUTED_EXPERIMENTAL"`, `model_id: "variable_inertia_cantilever_fem_v1"`,
`physical_validation: "NOT_ESTABLISHED"`, `evidence_level: "unverified"`,
`aircraft_status: null`, `feasibility: null`, `reasons: []`, `limitations`, and `sources`.
`outputs` has exactly these keys; `output_units` has the same keys and these unit values:

| Output key | Unit / shape |
| --- | --- |
| `elements` | `1`; element count |
| `nodes_m`, `second_moments_m4` | `m`, `m^4`; physical nodal lists |
| `displacements_m`, `rotations_rad` | `m`, `rad`; nodal lists |
| `root_force_n`, `root_moment_nm` | `N`, `N*m`; signed reactions (example ≈ −10, −20) |
| `normalized_linear_residual` | `1` |
| `probes` | Ordered list; units are the nested field map below |

Each probe has exactly `element_index` (`1`), `local_coordinate` (`1`), `x_m` (`m`),
`deflection_m` (`m`), `rotation_rad` (`rad`), `curvature_1_m` (`1/m`), and
`nominal_bending_stress_pa` (`Pa`). Internal DOFs, scales, matrices, code, and process metadata are excluded.
The API adds `schema_version: "variable_beam_request_v1"`, `inputs` equal to
`model_dump(mode="json")`, and `input_sha256 = sha256_record(inputs)`.
`evaluation_sha256` hashes the full result, including inputs, their hash, and the
schema version, before adding `evaluation_sha256` itself, using existing deterministic `sha256_record` serialization.

Limitations: straight static ideal-clamped Euler–Bernoulli beam, constant E, continuous
piecewise-linear nodal I, small displacement, and neglected shear deformation.
Inputs/properties are unverified; jump inertia is not represented. One-sided probe
stress can jump at element boundaries without smoothing. Nominal stress establishes
no strength, fatigue, buckling, or aeroelastic certification. Residual measures arithmetic
balance only, not mesh or physics error. No aircraft feasibility, physical validation,
or physical qualification is established. The [CU Boulder notes](https://ceae.colorado.edu/~regueiro/courses/CVEN4511_5511_notes.pdf)
support Euler–Bernoulli/Hermite theory, not experimental validity.
