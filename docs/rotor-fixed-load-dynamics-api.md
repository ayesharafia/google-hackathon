# Rotor fixed-load dynamics API

- Authenticated endpoints: `GET /api/drone/rotor-fixed-load-dynamics/catalog` and `POST /api/drone/rotor-fixed-load-dynamics/evaluate`.
- Use these exact hosted paths. Existing authentication and CSRF behavior remain unchanged.
- Accepted evaluation module (`EVALUATION`): `isolated_rotor_frozen_load_dynamics_experimental`.
- Required fields: `evaluation`, `assembly`, `initial_state`, `inertia_body_kg_m2`, `dt_s`, `steps`, and `applicability_declaration`.
- `dt_s` must be positive; `steps` must be an integer from 1 through 1000.
- Applicability requires initial identity orientation and assembly gravity direction `[0,0,-1]`, using ENU/FLU conventions.
- Dynamics use existing frozen rotor body forces, apply gravity once, and hold mass, inertia, air conditions, and RPM constant.
- The accepted constant-body-wrench RK4 uses raw stage quaternions; it is not the normalized-stage callback method.
- Step-refinement checks are required; no accuracy or simulation-horizon guarantee is provided.
- Admission limits: 128 KiB request size; JSON budget 32,768; nesting depth 10; assembly budget 16,384.
- Malformed JSON or strict-syntax violations return HTTP `422`.
- Semantic rejection returns HTTP `200` with `GRAPH_INVALID` and no hash.
- After admission, execution failure returns HTTP `200` with `EXECUTION_FAILED`; result containers are cleared atomically.
- Execution failures preserve the admitted request hash, including inertia failures occurring after assembly processing.
- `input_sha256` aliases `request_sha256`. `evaluation_sha256` hashes the response before its own field is added.
- Hashes identify content; they do not establish physical validity.
- Excluded capabilities: installed-flight evaluation, trim, control, stability, interference, energy/thermal analysis, mass closure, trajectory history, and flight pass/fail qualification. No API qualification or deployment is claimed.
