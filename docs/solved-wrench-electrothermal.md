# Solved wrench electrothermal

`evaluate_solved_wrench_electrothermal` in `physimesh.drone.solved_wrench_electrothermal` composes ordered static-wrench power calculations, electrical-energy accounting, and lumped thermal screening. `EVALUATION` is `solved_wrench_electrothermal_mission_experimental`. This is a core function; no API endpoint is provided.

The request is a builtin JSON dictionary with exactly `evaluation`, `usable_energy_j`, `reserve_fraction`, `thermal_body`, and `segments`. Unknown fields are rejected. Usable energy is positive; reserve fraction satisfies `0 <= r < 1`. Numeric fields reject booleans, nonfinite values, and nonzero subnormals.

`thermal_body` has exactly:

| Field | Contract |
|---|---|
| `mass_kg` | Positive |
| `specific_heat_j_kg_k` | Positive |
| `initial_temperature_k` | Positive Kelvin |
| `lumped_biot_number` | Within `[0, 0.1]` |
| `property_source` | Nonblank string, at most 2000 characters |

Thermal mass is separately declared, independent of aircraft mass. It supplies no mass feedback. Biot number is an unverified declaration; the conventional lumped criterion is `Bi < 0.1`.

`segments` contains 1-16 entries in chronological order. Each has exactly `id`, `duration_s`, `solve`, `conversion`, and `thermal`. IDs are unique, nonblank strings of at most 64 characters. Duration is positive seconds.

`solve` is a complete `bounded_static_wrench_solve_experimental` request used by the solved-power core, using a speedless assembly template: hover nodes omit `angular_speed_rad_s`. Its exact fields are `evaluation`, `assembly_template`, `rotor_speed_bounds`, `required_net_force_body_n`, `required_net_moment_cg_body_nm`, `absolute_force_tolerance_n`, `absolute_moment_tolerance_nm`, and `max_evaluations`. Existing solver, assembly, graph, bounds, and unit contracts apply.

`conversion` follows the accepted V93 power contract. It has exactly `rotors`, `auxiliary_power_w`, and `auxiliary_source`. Rotor entries follow assembly order, with exactly `node`, `conversion_efficiency`, and `conversion_source`. Efficiency satisfies `0 < eta <= 1`; auxiliary power is nonnegative. Sources are nonblank strings of at most 2000 characters.

Each segment's `thermal` has exactly `ambient_temperature_k > 0`, `conductance_w_k >= 0`, `heat_fraction_of_electrical_input` within `[0,1]`, and nonblank `heat_source` of at most 2000 characters. Ambient conditions and conductance are explicit declarations. Segments may declare different air, geometry, or aircraft mass; these differences remain unverified and introduce no dynamic feedback.

The complete request permits 65536 visited JSON values, counting keys and containers, checked before deep copying. Maximum depth is 10, with root depth 1; containers hold at most 256 entries; strings, including keys, have at most 2000 characters and must encode as UTF-8. Integers have at most 1023 bits. Only builtin JSON types are accepted.

Embedded V93 power requests retain their 49152-value limit, nested solver requests 32768, and graphs 4096. Existing graph and rotor limits also apply. Across all segments:

```text
sum(segment_sum_annuli * (segment_max_evaluations + 1)) <= 32768
```

The extra evaluation reserves each segment's power graph. Segments directly contain `solve` and `conversion`; no nested power wrapper consumes another request-depth level, allowing graph inputs at depth 10.

Every segment validates before any model executes, including augmented power graphs at initial speeds. Thermal capacity `mass * specific_heat` and reserve arithmetic must also pass preflight.

For each reached segment, the actual V93 power evaluator executes once. Its solver performs bounded candidate evaluations. Returned candidate counts, speed bounds, reconstructed residual arithmetic, selection, assembly totals, units, request hashes, and power arithmetic are checked. Only `RESIDUAL_MET` permits a fresh power graph at actual selected speeds, using the same declared air and geometry. Shaft power is checked against torque times angular speed, and refreshed loads against the solved assembly.

Electrical power is actual rotor shaft power divided by declared efficiency, summed with auxiliary power once. Positive contributions must remain distinguishable in accumulated totals.

The earliest unmet segment stops remaining execution. Status remains `COMPUTED_EXPERIMENTAL`; `mission_state` is `STOPPED_AT_UNMET_SEGMENT`. `power_segments` contains the executed prefix, including the unmet row with null power. Energy, thermal, and their units are null; transfers are empty. No mission totals or infeasibility conclusion are produced. `diagnostics_complete=true` means the returned decision record is complete, not that the mission was computed.

When every segment meets residuals, state is `COMPUTED_FROM_RESIDUAL_MET_SEGMENTS`. Energy accounting uses:

```text
segment_energy = actual_electrical_power * duration
mission_budget = usable_energy * (1 - reserve_fraction)
held_reserve = usable_energy - mission_budget
remaining_budget = mission_budget - total_energy
```

Reserve is applied once. Checked arithmetic rejects overflow, underflow, subnormal results, rounded-away positive reserve, and lost positive power, energy, or duration contributions. Remaining budget may be negative. `budget_status` is `WITHIN_DECLARED_ENERGY` or `EXCEEDS_DECLARED_ENERGY`; neither establishes feasibility. Exceeding budget still permits thermal computation.

Heat input is actual electrical power multiplied by the declared heat fraction, never inferred as `1 - eta`. Heat creates no additional electrical-energy charge. One actual `screen_thermal` call processes the entire chronological schedule, carrying each end temperature into the next segment. Fixed thermal properties apply throughout. The existing returned-thermal validator checks exact durations, heat-energy products, elapsed-time arithmetic, temperature continuity, totals, residuals, and units.

`outputs` has exactly `mission_state`, `power_segments`, `energy`, and `thermal`. Power rows contain `segment_id`, `duration_s`, `solve`, `power_state`, and `power`.

Energy rows contain `segment_id`, `duration_s`, `electrical_power_w`, `segment_energy_j`, `cumulative_energy_j`, and `remaining_budget_j`. Energy totals contain `elapsed_s`, `total_energy_j`, `total_energy_wh`, `held_reserve_j`, `mission_budget_j`, `remaining_budget_j`, and `budget_status`.

Thermal outputs are the actual screening outputs: segment indices, durations, cumulative elapsed times, start/end/ambient temperatures, heat input, storage change, convective exchange, and energy-balance residuals; plus elapsed time, final/maximum temperatures, and corresponding energy totals. `output_units` supplies matching contracts using seconds, watts, joules, watt-hours, Kelvin, dimensionless `1`, and `not_applicable`.

Transfers contain `segment_id`, `electrical_power_w`, `heat_fraction_of_electrical_input`, `heat_input_w`, and `heat_source`.

Stages `power_0`, `power_1`, and subsequent executed indices hash actual complete V93 inputs/results. The final `thermal` stage hashes the actual whole thermal input/result. There is no synthetic energy stage. Nested V93 request hashes are verified; nested result hashes receive syntax-only checks where raw inner results are absent. These syntax-only checks provide no independent cryptographic proof of those executions.

Invalid preflight returns `GRAPH_INVALID`, no request hash, zero model executions, empty stages/transfers/outputs/units, and incomplete diagnostics. The broad public execution boundary catches `Exception`, including `RuntimeError`, returning atomic `EXECUTION_FAILED`, retaining an established request SHA, clearing all outputs, units, stages, and transfers, and reporting a generic reason. `BaseException` is not caught.

Root evidence remains `unverified`; `physical_validation`, `numerical_qualification`, and `runtime_identity` remain `NOT_ESTABLISHED`; feasibility and aircraft status remain null. Isolated static residual agreement establishes no trim, control authority, installed-rotor behavior, battery chemistry, radiation, mass or heat closure, CFD, physical validation, or safety.
