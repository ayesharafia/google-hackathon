The existing `evaluate_electrothermal_mission` contract remains unchanged: outer evaluation `constant_condition_electrothermal_mission_experimental` and root fields `evaluation`, `energy_mission`, `thermal_body`, and `thermal_segments`.

Inner evaluation `constant_condition_multi_rotor_mission_experimental` explicitly selects `multi_rotor_mission`. Existing `constant_condition_graph_mission_experimental` remains supported. Unknown selections are refused; payloads are never translated automatically.

Total electrical power is `P_electrical = sum(Pshaft_i / eta_i) + P_aux`. Include common auxiliary power exactly once. Integrate energy in joules, convert to watt-hours, and apply reserve exactly once.

Thermal input is actual total electrical power multiplied by an explicit caller-declared heat fraction: `P_heat = P_electrical * heat_fraction`. Total electrical power includes common auxiliary power. Never infer the heat fraction from `1 - eta`; heat creates no second energy charge.

Run the thermal body across the entire chronological schedule, carrying temperature between segments.

Retain the same source-driven ambient and conductance treatment and lumped-body applicability requirement, `Biot ∈ [0, 0.1]`. Declared applicability is not a measurement.

Retain the 49,152-value JSON budget and maximum depth of 10, plus inherited limits of 32 segments, 128 nodes, and 8,192 annuli. If exposed through the existing electrothermal HTTP selection, retain the existing 128 KiB API limit; this introduces no new API.

Preflight all inputs before invoking components. On failure, final outputs and transfers must be empty, while hashes from completed stages remain retained.

Sources are unverified caller declarations. Hashes establish neither source truth nor physical validity. Feasibility remains `None`.

Scope excludes installed physics, trim, dynamics, fuel-mass feedback, heat feedback, radiation, hotspots, chemistry, safety assessment, and flight qualification. No deployment or test results are asserted.
