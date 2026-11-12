# Ledger rotor dynamics API

Authenticated endpoints use existing auth/CSRF and these exact hosted paths:

- `GET /api/drone/ledger-rotor-dynamics/catalog`
- `POST /api/drone/ledger-rotor-dynamics/evaluate`

Evaluation root fields: `evaluation`, `ledger`, `assembly_template`, `initial_state`, `dt_s`, `steps`, `applicability_declaration`. Set `evaluation` to `ledger_rotor_frozen_load_dynamics_experimental`.

One frozen ledger supplies mass, CG and full parallel-axis inertia once. Duplicate assembly mass/CG or root inertia is forbidden.

Limits: body 128 KiB, 49,152 JSON values, depth 10. JSON-value budgets: inner ledger 16,384; frozen dynamics 32,768; assembly 16,384.

- Malformed parser input: HTTP 422.
- Semantic refusal: HTTP 200, `GRAPH_INVALID`, no hash.
- Admitted execution failure: HTTP 200, `EXECUTION_FAILED`; all result containers cleared, hash retained.

`input_sha256` aliases `request_sha256`. `evaluation_sha256` hashes the response before its own field is added.

**Material limits:** Reconstructed inner guard metadata is inherited, not independently recovered. Nested `result_sha256` is syntax-checked only, not rebound to the nested raw result. Nested `request_sha256` is rebound to canonical inputs. The top-stage hash binds the actual complete ledger and frozen-dynamics raw records. Nested provenance is not end-to-end verified.

Constant mass and frozen rotor body loads; gravity applied once; initial identity attitude; ENU/FLU frames. Raw-stage RK4 with step refinement provides no accuracy guarantee.

No mass evolution, control, stability, installed flight closure, physical qualification, API qualification or deployment.
