`evaluate_ledger_rotor_dynamics(request)` accepts exactly these root keys: `evaluation`, `ledger`, `assembly_template`, `initial_state`, `dt_s`, `steps`, `applicability_declaration`.

`evaluation` must be `"ledger_rotor_frozen_load_dynamics_experimental"`.

`assembly_template` is the accepted `rotor_assembly` request with exactly `evaluation`, `graph`, `air_node`, `rotors`, `gravity_direction_body`, `property_source`. Duplicate `mass_kg`, `cg_body_m`, and dynamics inertia are forbidden; inertia is ledger-derived only. All accepted baseframes and limits apply.

The caller explicitly declares that ledger body axes already match template body axes; no rotation is inferred. Whole-request JSON limits are 49,152 JSON values, depth 10, and container size 256, checked before copying. Ledger structural preflight precedes exact template checks. Temporary unit mass, zero CG, and identity inertia serve only structural dynamics preflight; they are never output or evaluated physics.

One real ledger evaluation supplies weighted mass, CG, and parallel-axis inertia to accepted assembly/dynamics. Numerical inertia can still cause refusal after ledger evaluation.

Execution is all-or-nothing: any post-admission failure returns `EXECUTION_FAILED`, retaining the request hash with empty stages, transfers, outputs, and units. Success records ledger/frozen-dynamics stage hashes, transfers the three mass properties, and nests only raw stage outputs and units.

Hashes are not physical proof. This is one ledger snapshot, not installed-mass validation or mass evolution. Frozen initial loads and raw-stage RK4 imply no air update, refinement accuracy guarantee, or flight closure.
