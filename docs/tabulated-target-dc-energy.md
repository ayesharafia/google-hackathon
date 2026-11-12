# Experimental prescribed tabulated target DC energy

`physimesh.drone.tabulated_target_dc_energy` exposes
`evaluate_tabulated_target_dc_energy(request)` and the fresh metadata-only
`tabulated_target_dc_energy_catalog()`. Evaluation is
`prescribed_tabulated_target_dc_energy_experimental`; schema is
`tabulated_target_dc_energy_v1`. This is a separate local experimental contract.

The exact root fields are `evaluation` and `segments`. `segments` is an ordered
builtin list of 1–8 exact objects with `id`, `duration_s`, `power_request`.
IDs are unique, nonblank builtin strings of at most **1992 Unicode characters**,
with strict UTF-8 encoding. The prefix `segment:` therefore fits the 2000-character
JSON string limit; `air` is a valid segment ID. Duration is a strictly positive
builtin finite normal int or float, excluding bool. No defaults are supplied.
`power_request` is the complete unchanged V116 request, including its evaluation,
assembly, every motor and auxiliary declaration.

All segment declarations and complete actual V116 requests, including every motor,
are preflighted before the first model call. Each point retains its accepted
32768 limit on SUM over all rotors of `max_evaluations * annuli`. The corresponding
sum over **all** segments must be at most 65536, even if a later point would stop
execution. Structural preflight does not solve geometry or targets.

The root `limits` entries are `input_json`, `output_json`, `point_input_json`,
`point_output_json`, and `core_work`. Independent resource limits are:

| JSON scope | Nodes including keys | Maximum depth | Items per container |
| --- | ---: | ---: | ---: |
| Entire input | 524288 | 20 | 256 |
| Entire output | 4194304 | 32 | 2048 |
| Each point input | 131072 | 16 | 256 |
| Each point output | 1048576 | 28 | 2048 |

Depth starts at one. All scopes require builtin JSON, finite floats, valid UTF-8,
at most 2000 characters per string, and at most 1023 bits per integer. Walks
precede deep copies; subclasses and their copy/conversion/iteration hooks are
rejected. Keys count as nodes; repeated aliases are visited each time. Cycles
fail the depth bound. Accepted child resource limits also apply.

Each segment invokes the actual V116 point evaluator once with detached full
inputs. Its full returned JSON is immediately bounded and snapshotted, then the
pure V117 full actual-result guard is invoked exactly once. The guard must return
`None` before any counts are trusted. There is no substitute envelope, scalar
graph, or model rerun for validation. Import-time source catalog snapshots supply
metadata; catalog calls at runtime execute no models.

For each computed point, nine fixed mappings integrate actual `outputs.power`
watts using `thermal.checked_product(watts, duration_s)`:

| Energy key | Actual V116 power field |
| --- | --- |
| shaft | total_shaft_power_w |
| motor_electrical | total_motor_electrical_power_w |
| motor_loss | total_motor_loss_w |
| allocated_motor_heat | total_allocated_motor_heat_w |
| unallocated_motor_loss | total_unallocated_motor_loss_w |
| auxiliary_electrical | auxiliary_electrical_power_w |
| auxiliary_heat | auxiliary_heat_w |
| total_electrical | total_electrical_power_w |
| total_allocated_heat | total_heat_w |

Upstream `total_heat_w` explicitly means **allocated heat**, not all motor loss.
The nine mappings are distinct accounting components, not nine quantities to add
together. Shaft energy is mechanical work, not heat. Electrical energy is terminal
DC-equivalent demand, not battery energy. Allocated heat joules imply no temperature.

`outputs` has exactly `segments`, `elapsed_s`, `totals_j`, `totals_wh`, and
`all_motors_within_declared_limits`. Each row has `segment_id`, `duration_s`,
`start_time_s`, `end_time_s`, `actual_power_result`, `energy_j`, and
`cumulative_energy_j`. The full actual point appears **once**, unchanged, in that
row. The full request appears in its stage inputs, not again in the row.

Elapsed time uses the accepted DC `_power_sum` on each duration prefix. Each
`end_time_s` must exceed its start; loss of floating-point resolution fails.
Cumulative and total energies use the accepted `_power_sum` over individual
segment energies in order, not a sum of previously rounded cumulative values.
Each Wh value is explicitly `checked_quotient(total_j, 3600)`. Helpers reject
nonzero underflow, subnormal results, overflow and sum resolution loss. Output
units follow exact output scopes: seconds, joules, Wh, label/boolean dimensionless,
and nested actual point units only under `actual_power_result.outputs`.

A stage named `segment:<id>` contains only its full actual `power_request` inputs,
`inputs_sha256`, and the full actual point `result_sha256`. Nine transfers per
point bind the actual W scalar `outputs.power.<field>` to
`outputs.segments[i].energy_j.<key>`, with `to_stage: energy`, `unit: W`, full
actual point producer digest, and **root request digest** as consumer digest.
Duration is bound by the full root request digest, with no separate duration
transfer. These are data provenance records, not compute graph attestation.

Counts cover guarded returned contracts only: `point_result_count` 0–8,
`assembly_inverse_result_count` 0–64, `forward_evaluation_count` 0–4096, and
`motor_result_count` 0–64. A guard-valid noncomputed point contributes all its
counts, propagates its status with the fixed point reason, and stops later calls.
A malformed point contributes none. Arithmetic may fail after a point has been
counted; those trusted counts survive. Counts do not attest calls or attempts.

All failures atomically clear outputs/units and stages/transfers, with diagnostics
false. Invalid preflight returns `MODEL_INAPPLICABLE`; unsupported root evaluation
returns `SOLVER_UNSUPPORTED`; both have zero counts and null hashes. Unexpected
snapshot exceptions return `EXECUTION_FAILED` with the snapshot reason, zero counts
and null hashes. After admission, the root request hash binds the full snapshot.
Unexpected execution/guard/arithmetic exceptions return `EXECUTION_FAILED` with
the execution reason and previous trusted counts. Noncomputed child statuses use
the point reason. Result hashes cover the entire outer response omitting
`evaluation_sha256`; `MODEL_INAPPLICABLE` always has a null result hash. Digest
infrastructure failure can leave hashes null and does not establish a guarded
execution history. Ordinary exception text is sanitized; BaseException propagates.

All motor flags are conjoined. A known declared-limit exceedance remains a
computed result with a false flag, without an attainability or feasibility claim.
Diagnostics are complete only for computed results. Physical validation,
numerical qualification and runtime identity remain `NOT_ESTABLISHED`; aircraft
status and feasibility remain null.

Caller-prescribed durations and isolated static points are not a solved mission
profile, even when altitude varies. There is no interpolation, time dynamics,
changing mass/geometry coupling, temperature integration, SOC/battery, ESC, trim,
flight dynamics, reserve budget, available power, safety or aircraft feasibility
model. All actual point limitations remain in force. No physical, numerical,
runtime, publication, accuracy or novelty qualification follows from this bridge.
