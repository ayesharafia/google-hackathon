# Frozen mass ledger request

`physimesh.drone.mass_ledger_request.evaluate_mass_ledger` evaluates a strict JSON request for `frozen_mass_ledger_experimental`.

The root has exactly three fields: `evaluation`, `items`, and `property_source`. Set `evaluation` to `"frozen_mass_ledger_experimental"`.

`items` contains up to 128 entries. Each supplies `name`, `category`, `mass_kg`, `cg_body_m`, and `inertia_own_cg_body_kgm2`.

All six categories must be explicit: `payload`, `structure`, `propulsion`, `energy`, `avionics`, and `other`. For each category known absent, include a declared zero-mass entry with zero own inertia.

Values are declared in body-frame SI units. Each component inertia tensor is about that component’s CG and already expressed in the common body axes. No orientation is inferred, and missing inertia never defaults to zero.

Admission limits are 16,384 values, depth 10, and container size 256. After admission, existing `mass.summarize` runs with `need_inertia=True` to calculate weighted CG and full parallel-axis inertia. Component tensor checks and numerical failures occur after admission.

Successful outputs are:

- `total_mass_kg`: kg
- `cg_body_m`: m
- `inertia_cg_body_kgm2`: kg*m^2
- `payload_kg`: kg
- `by_category_kg`: category-to-mass mapping, kg

Structural failure returns `GRAPH_INVALID` with no request hash (`nohash`). Admitted failure returns `EXECUTION_FAILED`, retains `request_sha256`, and has empty outputs. Success returns `COMPUTED_EXPERIMENTAL` and remains unverified.

This is a frozen snapshot; it does not represent time-varying fuel or payload uncertainty. Finite existing arithmetic provides no general conditioning or accuracy assurance. Mass is not derived from STL, and no aircraft verdict is provided.
