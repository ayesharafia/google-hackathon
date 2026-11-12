# Frozen ledger solved DC electrothermal mission (V100 local candidate)

`physimesh.drone.ledger_solved_dc_electrothermal.evaluate_ledger_solved_dc_electrothermal`
composes the accepted frozen mass ledger with the accepted V99 solved DC
electrothermal mission. It adds request validation, frozen mass/CG transfers,
returned-contract validation, and provenance. It introduces no new physical
model or scientific discovery claim. This candidate adds no application route,
deployment, publication, or changes to accepted modules.

## Request and use

The root object has exactly these keys:

```text
evaluation: "ledger_solved_dc_electrothermal_mission_experimental"
ledger:
  evaluation: "frozen_mass_ledger_experimental"
  property_source: nonblank string
  items: 1..128 declared mass items
mission_template:
  evaluation: "solved_dc_electrothermal_mission_experimental"
  usable_energy_j: positive number
  reserve_fraction: number in [0, 1)
  thermal_body:
    mass_kg: positive number
    specific_heat_j_kg_k: positive number
    initial_temperature_k: positive number
    lumped_biot_number: number in [0, 0.1]
    property_source: nonblank string
  segments: 1..16 chronological segments
```

Each ledger item has exactly `name`, `category`, `mass_kg`, `cg_body_m`, and
`inertia_own_cg_body_kgm2`. Names are unique. All six categories (`payload`,
`structure`, `propulsion`, `energy`, `avionics`, `other`) must be represented;
explicit zero mass items are allowed. Masses are nonnegative, CGs are body-frame
three-vectors in metres, and own-CG inertia is a declared 3×3 body-frame tensor in
kg·m². The accepted mass kernel checks inertia admissibility and positive total
mass.

Each mission segment has exactly `id`, `duration_s`, `point`, and `thermal`.
Identifiers are unique nonblank strings of at most 64 characters. Duration is
positive. `thermal` has exactly positive `ambient_temperature_k` and nonnegative
`conductance_w_k`. `point` retains the V99 DC point schema: `evaluation`, `solve`,
`motors`, `auxiliary`. Motor parameters, declared limits, loss-capture fractions,
auxiliary power and heat fractions retain their accepted contracts.

Every `point.solve.assembly_template` must have exactly `evaluation`, `graph`,
`air_node`, `rotors`, `gravity_direction_body`, and `property_source`. It must
omit both `mass_kg` and `cg_body_m`; supplying either is rejected even if its
value agrees with the ledger. All remaining solve, graph, rotor, and motor
fields follow the accepted V99 request contracts. See
[the accepted source](../src/physimesh/drone/solved_dc_electrothermal.py) and
[the new real-fixture examples](../tests/drone/test_ledger_solved_dc_electrothermal.py).

For existing declared input dictionaries:

```python
from copy import deepcopy
from physimesh.drone.ledger_solved_dc_electrothermal import (
    EVALUATION, evaluate_ledger_solved_dc_electrothermal,
)

# frozen_ledger_request and mission_template are supplied declarations.
# Every assembly template already omits mass_kg and cg_body_m.
request = {
    "evaluation": EVALUATION,
    "ledger": deepcopy(frozen_ledger_request),
    "mission_template": deepcopy(mission_template),
}
result = evaluate_ledger_solved_dc_electrothermal(request)
```

## Validation and execution contract

The strict builtin JSON outer guard permits depth at most 13 (root depth one),
98,304 visited nodes including dictionary keys, 256 items per container, strings
of at most 2,000 characters that encode as UTF-8, and integers of at most 1,023
bits. Floating values must be finite. Custom containers/scalars, tuples, and
non-string dictionary keys are rejected. Boolean JSON values are not accepted
in numeric fields. Independent accepted child guards remain unchanged.

Before any evaluator call, the wrapper validates the ledger request and every
mission segment. A copied mission containing structural mass `1` and CG
`[0, 0, 0]` is used solely for preflight. These placeholders never enter reported
results or evaluator calls. The accepted 1..16 segment limit, global annuli work
bound `sum(annuli * (max_evaluations + 1)) <= 32768`, independent child work
bounds, thermal capacity arithmetic, reserve arithmetic, and nonloss duration
arithmetic all remain enforced, including on later segments that might never
be reached during execution.

The actual ledger evaluator is called once. Its actual envelope, request hash,
qualification fields, units, and typed outputs are checked. The wrapper then
constructs `MassItem` entries from the declared ledger and calls `summarize`
directly, with inertia enabled. It binds total mass, CG, inertia, payload mass,
and each category mass to those declarations. This is deterministic ledger
arithmetic, not a second ledger evaluation or a rotor/motor model rerun.

The validated actual mass and CG are injected into every segment. The complete
instantiated mission is preflighted before the single actual V99 mission
evaluator call. The wrapper independently validates that actual mission
envelope, status, qualifications, diagnostics, reasons, request hash, stage
structure, transfers, and retained outputs. Its calls to V99
`_point_output_values` and `_heat_output_values` check only retained values and
units; those calls do not authenticate the actual envelope or its provenance.
Additional typed comparisons prevent bool/number substitutions, including in
selected candidates; thermal row indices must be builtin integers.

Retained slices are bounded and checked individually. There is no new global
JSON node cap on the entire returned multi-segment mission. Stage lists,
transfers, energy, and metadata are instead constrained by exact schemas,
request-derived lengths, and typed comparisons to reconstructed expectations.
Malformed deep or oversized values fail closed without being exported.

## Results, stages, and hash scope

A successful result has `outputs.ledger`, `outputs.mission`, and corresponding
`output_units.ledger` and `output_units.mission`, preserving accepted units.
`transfers.mass_cg` contains an explicit `segment_id`, `mass_kg`, `cg_body_m`, and
`source: "validated_frozen_mass_ledger"` for every declared segment, including
segments not reached after an unmet point. `transfers.mission` retains the
validated V99 energy/heat transfers. Each transfer CG is independently copied;
inputs, child results, and exported ledger and transfer branches are isolated.

The wrapper records two stages:

- `ledger`: hashes of the actual ledger request and actual ledger result.
- `mission`: hashes of the actual instantiated mission request and actual V99
  result, with the actual nested mission `stages` preserved.

The root `request_sha256` hashes the copied original wrapper request. All hashes
use the accepted canonical JSON hashing function. For retained `point_N`,
`solved_wrench_power`, nested `solve`/`power_graph`, motor, and thermal stages,
the wrapper reconstructs child requests from the instantiated mission and
validated selected solve/candidate values. It checks identifiers, request
hashes, bounds, and lowercase 64-character hexadecimal result digest syntax.

V99 does not retain complete child raw envelopes, point transfers, or
solver-internal evaluation stages in the mission result. Their absent raw
preimages are never fabricated. Retained child result hashes remain opaque
digests; checking their syntax does not authenticate their preimages or runtime
identity. The wrapper hashes complete ledger and mission results only because
those actual envelopes are available.

If a residual is unmet, V99 retains exactly the reached chronological prefix
including the first unmet segment. No later point or thermal calls occur.
Mission energy and thermal outputs/units are null and mission transfers are
empty. When all segments meet residual tolerances, electrical energy covers the
full mission independently of captured heat; allocated motor loss and auxiliary
heat feed one chronological thermal stream. Both are checked using accepted
arithmetic, without rerunning the mission or point models.

Preflight failures return `GRAPH_INVALID`. Ordinary execution exceptions and
returned-contract failures return `EXECUTION_FAILED` with empty outputs, units,
stages, and transfers; no partial success data is exported. `BaseException`
subclasses such as `KeyboardInterrupt` and `SystemExit` propagate.

## Limitations

The ledger is frozen: there is no fuel consumption, payload change, mass
evolution, uncertainty propagation, or mass inference from geometry. Ledger
inertia is reported and checked but unused by the mission solve. The separately
declared `thermal_body.mass_kg` is unchanged; it is not replaced by total ledger
mass. Constant-property lumped thermal screening has no temperature feedback
into the point models.

All accepted V99 static point, DC-equivalent motor, loss-allocation, energy,
and thermal limitations apply. Physical validation, numerical qualification,
and runtime identity remain `NOT_ESTABLISHED`; evidence is `unverified` and
`feasibility`/`aircraft_status` remain null. Computed residuals, declared limits,
and energy/thermal screens establish no aircraft, flight, continuous-rating,
battery, ESC, or installed-system qualification.
