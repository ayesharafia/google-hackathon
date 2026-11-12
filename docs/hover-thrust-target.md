# Hover thrust target

`evaluate_hover_thrust_target` accepts exactly these root keys:

- `evaluation`: `isolated_hover_thrust_target_experimental`
- `rotor_template`
- `target_thrust_n`
- `angular_speed_bracket_rad_s`
- `absolute_thrust_tolerance_n`
- `max_evaluations`

`rotor_template` is an accepted `hover_bemt_request` without angular speed. Geometry, air and pitch stay fixed; all physical inputs and declarations are required, with no defaults.

Preflight requires:

- Positive angular-speed bounds, low < high, in **rad/s, not RPM**.
- Target > tolerance > 0.
- `max_evaluations`: integer 2–64; annuli: integer 1–512; their product ≤32768.
- JSON ≤8192 values, checked before copying.

Actual forward BEMT evaluates both endpoints, then bisects within the bracket. No omega² scaling or hidden extrapolation. Monotonicity checks concern observed samples, not a global proof. The best candidate is actually evaluated; its thrust residual is in N.

Outcomes: `TARGET_RESIDUAL_MET`, `TARGET_NOT_BRACKETED`, `EVALUATION_LIMIT`, `FLOATING_POINT_STAGNATION`. Completed searches have outer status `COMPUTED_EXPERIMENTAL`; this does not establish feasibility.

Core-model refusal or an invalid result fails atomically: preserve the data hash and clear outputs. Invalid preflight produces no hash.

Tolerance bounds only the model root residual, not physical accuracy, hover trim, rotor available power, attached-flow angle validation, stall or installed-aircraft performance. Shaft power is **not electrical power**.

This frozen, unverified, small-angle isolated model has no loss/swirl corrections, Reynolds/Mach polars, control or stability analysis. Existing body and propulsion limits remain explicit. Data hashes identify records, not runtime identity or physical proof.

No project mutation, API changes or deployment.
