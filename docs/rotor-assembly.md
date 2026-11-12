# Isolated-rotor static assembly

Local `evaluate_rotor_assembly` uses exact evaluation `isolated_rotor_static_assembly_experimental`. The exact root contains `evaluation`, `graph`, `air_node`, `rotors`, `mass_kg`, `cg_body_m`, `gravity_direction_body`, and `property_source`.

The graph requires one `reference_air_properties` node and 1–15 `isolated_hover_bemt_experimental` nodes, connected only through common air density. Targets are air gravity and each rotor’s thrust/shaft torque. All nodes must be used. Graph caps apply: 16 nodes, 64 edges, 32 targets, and 8192 annuli; 15 rotors require 31 targets.

Each rotor contains exactly `node`, `center_body_m`, `axis_body`, and `rotation_sign`; the sign must be a built-in integer ±1. Body FLU means forward, left, up. Positions share an origin; moment arms subtract CG. Axes point along thrust; positive spin follows the right-hand rule about each axis.

- `F = T * axis`
- Aircraft reaction to absorbed torque: `reaction = -rotation_sign * Q * axis`
- `M_cg = (center - cg) × F + reaction`

Gravity is `mass * g * unit_direction`, applied at CG. Axis/direction norms must already be within `1e-12` of unity; no normalization occurs. Properties are explicit and unverified.

All preflight checks precede execution; failures yield no final outputs. Data SHA is not validation. Force/moment residuals establish neither trim, stability, control authority, airworthiness, nor a 750 kg/20 km pass.

Isolated small-angle linear superposition ignores interference, crossflow, gyroscopic effects, dynamics, and mass evolution. No HTTP, deployment, or physical qualification; feasibility is `None`.
