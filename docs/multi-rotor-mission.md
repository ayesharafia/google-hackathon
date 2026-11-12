# Experimental multi-rotor mission

Frozen-condition isolated-hover rotor energy sums; no aircraft qualification. Evaluation identifier: `constant_condition_multi_rotor_mission_experimental`.

The complete request is checked and deep-copied before execution. Segments run in declared chronological order without reordering; each graph is evaluated once when reached. Execution stops on failure.

- Exact request keys: `evaluation`, `usable_energy_j`, `reserve_fraction`, `segments`.
- `evaluation` must equal the identifier above; `usable_energy_j > 0`; `0 <= reserve_fraction < 1`; `segments` must be a list of 1–32 entries.
- Exact segment keys: `id`, `duration_s`, `graph`, `rotors`, `auxiliary_power_w`.
- Segment IDs must be unique, nonblank strings of at most 64 characters; `duration_s > 0`; `auxiliary_power_w >= 0`; `rotors` must be a list of 1–15 entries.
- Exact rotor keys: `node`, `conversion_efficiency`, `conversion_source`.
- Rotor node names must be distinct within a segment; `0 < conversion_efficiency <= 1`; `conversion_source` must be a nonblank string of at most 2,000 characters.
- The request passes `_json(..., budget=32768)`; recursively traversed values reject booleans, and every integer/float passes `_normal`. Numeric bounds receive additional checks.

Each graph must be a dictionary with `evaluation == GRAPH_EVALUATION` and pass the imported `_validate`; its full schema is defined there.

- Exactly one node uses `reference_air_properties`; every other node is a listed rotor using `isolated_hover_bemt_experimental`.
- Rotor inputs must omit `density_kg_m3`. No additional nodes are permitted.
- Connections must number exactly one per rotor and have exactly the set of edges from the air node’s `density_kg_m3` port to each rotor’s `density_kg_m3` port.
- The target set must be exactly each listed rotor’s `shaft_power_w`.
- Across all segments, at most 128 nodes and 8,192 summed rotor-input `annuli` are permitted.

For segment \(k\), \(P_k=\sum_i(P_{\mathrm{shaft},k,i}/\eta_{k,i})+P_{\mathrm{aux},k}\): shared auxiliary power is added once per segment.
Energy follows chronological durations: \(E_k=P_k\Delta t_k\), \(C_k=\sum_{j=1}^{k}E_j\), and \(t_k=\sum_{j=1}^{k}\Delta t_j\).
Reserve is held once per mission: \(B=U(1-r)\), \(H=U-B\), and remaining budget after segment \(k\) is \(B-C_k\). Total Wh is \(C_n/3600\).

Converted rotor powers, cumulative energies, and elapsed durations use checked arithmetic, including `math.fsum` for sums. Nonzero contributions must produce the required positive results and strict sum increases; unrepresentable arithmetic is refused. A negative remaining budget is reported without stopping execution.

Graph results pass `_json(..., budget=262144, items=2048)` and must report the expected evaluation, `COMPUTED_EXPERIMENTAL`, complete diagnostics, `unverified` evidence, empty reasons, and the matching graph-request hash. Their validation/qualification/identity fields must be `NOT_ESTABLISHED`, with aircraft status and feasibility present and null.
Graph output and unit dictionaries must contain exactly the listed rotor names; each rotor exposes only nonnegative checked `shaft_power_w`, with unit `W`.

- Each successful segment record contains `segment_id`, `duration_s`, `rotors`, `auxiliary_power_w`, `electrical_power_w`, `segment_energy_j`, `cumulative_energy_j`, `remaining_budget_j`, `graph_request_sha256`, and `graph_result_sha256`.
- Each rotor record contains `node`, `shaft_power_w`, `conversion_efficiency`, and `electrical_power_w`.
- Successful `outputs` contain exactly `elapsed_s`, `total_energy_j`, `total_energy_wh`, `held_reserve_j`, `mission_budget_j`, `remaining_budget_j`, and `budget_status`.
- Corresponding `output_units` are `s`, `J`, `Wh`, `J`, `J`, `J`, and `not_applicable`. Budget status is `WITHIN_DECLARED_ENERGY` when remaining budget is nonnegative, otherwise `EXCEEDS_DECLARED_ENERGY`.

The response includes `evaluation`, `status`, `evidence_level`, `physical_validation`, `numerical_qualification`, `runtime_identity`, `aircraft_status`, `feasibility`, `diagnostics_complete`, `reasons`, `segments`, `outputs`, `output_units`, and `limitations`; `request_sha256` is added only after successful preflight.
Preflight rejection returns `GRAPH_INVALID`, incomplete diagnostics, reason `Invalid multi-rotor mission request.`, and empty result containers. Execution rejection returns `EXECUTION_FAILED`, incomplete diagnostics, reason `Multi-rotor mission execution refused.`, and clears all segment/output containers while retaining the request hash.
Success returns `COMPUTED_EXPERIMENTAL`, complete diagnostics, and empty reasons. Results are all-or-nothing; exceeding declared energy remains a successful computation, not an aircraft verdict. The returned response is deep-copied.

Evidence remains `unverified`; physical validation, numerical qualification, and runtime identity remain `NOT_ESTABLISHED`; aircraft status and feasibility remain null. Air-property results are unverified, as are caller-declared efficiencies, auxiliary power, and usable energy. Literal source notes confer no authority; hashes identify data and are not proof of physical validity or runtime identity.
No installed physics, rotor interference, trim, dynamics, mass/fuel-state closure, thermal closure, aircraft pass, or feasibility determination is provided. This source establishes no physical validation or API service.
