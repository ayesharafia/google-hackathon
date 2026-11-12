# Constant-condition graph mission

The exact root keys are `evaluation`, `usable_energy_j`, `reserve_fraction`, and `segments`. `evaluation` must be `constant_condition_graph_mission_experimental`. `usable_energy_j` is already usable energy BEFORE holding reserve. `reserve_fraction` is the held fraction, satisfying 0 ≤ r < 1. `segments` contains 1–32 ordered segments.

Each segment has exactly these fields: `id`, `duration_s`, `graph`, `power_node`, `power_port`, `conversion_efficiency`, `auxiliary_power_w`, and `conversion_source`.

Only air graphs with a sole W-valued target are accepted: hover `shaft_power_w` or wing `drag_power_w`.

- P_electrical = P_target / eta_conversion + P_aux.
- E = Σ(P_electrical × duration_s), in J; Wh = J / 3600.
- Reserve applies once: E_budget = E_usable × (1 − r).

Wing efficiency combines propulsive and electrical efficiency; hover efficiency converts shaft power to electrical demand. Conversion provenance is caller supplied and does not validate efficiency.

All segments undergo preflight before evaluation. Limits include 32 segments, global totals of 128 nodes and 8192 annuli, and inherited graph caps. Failures close with empty final outputs; diagnostics may be incomplete and retain prior-segment diagnostics.

Evaluation records chronological segment IDs, graph request/result hashes, and component power per segment. Full graph snapshots stay in the caller request and are not copied into the result. It performs scalar energy accounting, without resizing or dynamic-state integration. The 80-digit decimal checks verify arithmetic, not independent aerodynamic truth.

Positive or negative energy-budget margins are not aircraft verdicts. Full mission limits, including original A§5 missing transient mass/thermal closure, remain unresolved. No HTTP endpoint or deployment is provided.
