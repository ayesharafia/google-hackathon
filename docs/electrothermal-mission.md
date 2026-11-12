# Electrothermal mission

The new local Python API `evaluate_electrothermal_mission` uses evaluation constant `constant_condition_electrothermal_mission_experimental`. No HTTP or deployment is added.

The root has exactly `evaluation`, `energy_mission`, `thermal_body`, and `thermal_segments`. `energy_mission` is the constant-condition graph mission payload documented in graph-mission.md.

`thermal_body` has exactly `mass_kg`, `specific_heat_j_kg_k`, `initial_temperature_k`, `lumped_biot_number`, and `property_source`.

Each thermal row has exactly `id`, `ambient_temperature_k`, `conductance_w_k`, `heat_fraction_of_electrical_input`, and `heat_source`. IDs and order match the energy segments.

Heat deposition is **Q = actual computed electrical P × fraction**. The fraction is explicit caller-sourced data in `[0,1]`, never inferred as `1 − conversion efficiency`. Wing propulsive losses are not all device heat. Ambient temperature and conductance are explicit caller data; they are not inferred from the reference-air graph.

The accepted lumped thermal kernel processes the entire chronological schedule, carrying each actual end temperature into the next start without reset. Mass, specific heat, and Kelvin temperatures are positive; conductance is nonnegative. Biot number is caller-declared, not measured, within `[0,0.1]`; the conventional criterion is `Bi < 0.1`. Zero heat and zero conductance are allowed.

Preflight all thermal and energy inputs before components. Inherited limits: 32 segments, 128 nodes, 8192 total annuli; JSON: 49152 values, depth 10.

Success returns nested energy/thermal outputs with corresponding units. Stages retain data-only request/result SHA hashes; transfers contain P, fraction, and Q. Failures return no final outputs, retaining completed-stage hashes and incomplete diagnostics.

An 80-digit Decimal closed-form ODE test checks supplied floating-point heat, not physical validity.

Heat adds no energy charge: electrical energy already includes it. No thermal feedback into efficiency, battery chemistry, radiation, hotspots, measured thermal limits, safety, climb, transition, mass closure, or aircraft/mission feasibility is established. All three unverified qualifications are `NOT_ESTABLISHED`; feasibility is `None`.
