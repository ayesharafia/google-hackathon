# Uniform cantilever modal API candidate (V51)

This separate stateless adapter calls the accepted V50 core without changing its
solver, gates, diagnostics or limits. Independent review is required; this is
not an acceptance claim. The dedicated routes do not extend the atmosphere-only
evaluation registry or imply integration of other models. The original core
notes describe its pre-adapter standalone scope; this document describes V51.

Authenticated `GET /api/drone/beam-modal/catalog` returns fresh research-only
metadata, required fields and units. Authenticated `POST
/api/drone/beam-modal/evaluate` requires exactly these keys, with no defaults:

```json
{"evaluation":"uniform_cantilever_modal_experimental","length_m":2.0,"E_pa":70000000000.0,"I_m4":0.000001,"mass_per_length_kg_m":2.0,"elements":8,"modes":3,"property_source":"Unverified example properties","applicability_declaration":"Research uniform ideal cantilever only"}
```

Scalars require exact builtin int/float, excluding booleans, strings, null,
arrays and nonfinite or overflowing numbers. The core enforces positivity and
normal binary64 representability. Counts require exact integers: elements
2..64 and modes 1..min(6, 2*elements). Both declarations must be nonblank
strings of at most 2000 characters. They are unverified text, not validation
or evidence. Unsupported evaluation names return `SOLVER_UNSUPPORTED`.

HTTP structural failures, including malformed JSON, return constant sanitized
422 detail `Invalid modal beam request.` without echoing inputs. Core domain
and numerical refusals return HTTP 200 `MODEL_INAPPLICABLE`, empty outputs and
units, and an exact `core_refusal` copy. Direct structural adapter refusals
also have empty outputs. No partial modes are returned.

Success is `COMPUTED_EXPERIMENTAL`, model `uniform_cantilever_modal_v1`, schema
`beam_modal_request_v1`. `outputs.inputs`, `outputs.modes` and
`outputs.diagnostics` preserve the corresponding core fields; `limits` preserves
all core limits. API `inputs` preserves the explicit request. `input_sha256`
hashes that request with the existing canonical provenance helper;
`evaluation_sha256` hashes the entire response before adding that hash.

Length is m, E is Pa, I is m^4 and mass per length is kg/m. Angular frequency
is rad/s and frequency is Hz. xi, eigenvalues and normalized shape arrays are
dimensionless. Deflection is w/w_tip, and its derivative is with respect to
xi=x/L, not physical rotation. Diagnostics are dimensionless except frequency
scale (rad/s); free_dofs is a count.

Every response keeps physical validation, numerical qualification and mesh
accuracy `NOT_ESTABLISHED`, evidence `unverified`, aircraft status and
feasibility null. This uniform undamped Euler-Bernoulli model assumes an ideal
cantilever and small linear vibration. It excludes rotation, prestress,
damping, aeroelasticity, shear deformation, rotary inertia and tip mass.
Numerical consistency diagnostics establish no mesh, frequency or physical
error bound. No aircraft support is provided.

The routes inherit application authentication, body limits and browser origin
restrictions. Hosted individual bearer sessions may use these exact routes.
Evaluation performs no filesystem or project mutation and makes no network calls.
