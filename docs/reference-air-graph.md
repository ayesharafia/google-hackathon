# Bounded reference-air graph

`physimesh.drone.reference_air_graph.evaluate_reference_air_graph` uses evaluation literal `bounded_reference_air_graph_experimental`.

Accepted models:
- `reference_air_properties` (new fourth model)
- `standard_atmosphere`
- `isolated_hover_bemt_experimental`
- `fixed_wing_aerodynamic_screening`

Air inputs are exactly `altitude_m` (0–30000 m) and `altitude_kind` (`geometric` or `geopotential`).

Air output ports and units:
- `density_kg_m3`: kg/m^3
- `dynamic_viscosity_pa_s`: Pa*s
- `speed_of_sound_m_s`: m/s
- `gravity_m_s2`: m/s^2
- `temperature_k`: K
- `pressure_pa`: Pa

Connect air density, viscosity, and sound speed to the same wing input ports to compute Reynolds number, Mach number, and drag using supplied, unverified coefficients. Omit those wing literals; all other inputs remain required.

Request keys: `evaluation`, `nodes`, `connections`, `targets`. Edge keys: `from_node`, `from_port`, `to_node`, `to_port`. Target keys: `node`, `port`.

Execution uses the selected targets’ ancestor closure, serially in lexicographic order. Whole-graph preflight rejects global cycles. Limits: 16 nodes, 64 edges, 32 targets, 8192 aggregate hover annuli; existing bounds apply.

Viscosity uses NASA CAPE Sutherland MKS, not exact COESA transport. No weather, wind, or turbulence. Numeric, physical, and runtime qualification: `NOT_ESTABLISHED`.

No API integration, cache, parallel execution, cyclic solution, full M3, or aircraft feasibility. Hashes identify data, not executables.

Failure leaves final outputs empty; diagnostics retain completed stages as incomplete. Preceding accepted files remain unmodified. Independent review pending.
