# Ledger dynamics refinement API

Authenticated, existing auth/CSRF; exact hosted routes:

- GET `/api/drone/ledger-dynamics-refinement/catalog`
- POST `/api/drone/ledger-dynamics-refinement/evaluate`

Root exactly `evaluation`, `dynamics`. Evaluation: `ledger_dynamics_timestep_refinement_experimental`; dynamics: accepted ledger-bridge JSON.

Three actual runs use the same ledger, assembly and dynamics inputs: (dt,N), (dt/2,2N), (dt/4,4N). Integer N: 1..250; maximum 1000 steps/run. Complete all preflight and exact common-horizon checks before model calls. Repeat every full stage fresh; no cache.

Limits: body 128 KiB; JSON 65,536 values, depth 10. Inner caps: bridge 49,152; ledger/assembly 16,384 each; frozen dynamics 32,768.

- Strict malformed input: HTTP 422.
- Semantic refusal: HTTP 200 `GRAPH_INVALID`, no hash.
- Admitted failure: HTTP 200 `EXECUTION_FAILED`, empty stages/outputs/output_units; request hash retained.

`input_sha256` aliases `request_sha256`; `evaluation_sha256` hashes the response before adding itself.

Adjacent final-state differences: Euclidean position, velocity, omega; quaternion chord min(||qA-qB||,||qA+qB||), sign-invariant, not angle. Order = log2(d01)-log2(d12) only for positive differences; zero gives null/undefined. Negative order is reported, unqualified.

Top-stage data hashes bind actual whole-bridge raw results. Inner guard metadata is inherited; nested result hashes are syntax-only, not end-to-end provenance.

Frozen body loads, raw-stage RK4, common frames; no air feedback. No accuracy bound, tolerance pass, exact reference, fourth-order guarantee, physical/API qualification, deployment, or installed-flight, control/stability, energy/thermal validation.
