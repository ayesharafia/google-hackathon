# Solved DC electrothermal mission (experimental)

Public entry point:
`physimesh.drone.solved_dc_electrothermal.evaluate_solved_dc_electrothermal(request)`.
This research computation remains scientifically unqualified. Results carry
`evidence_level="unverified"`, `physical_validation`, `numerical_qualification`,
and `runtime_identity` set to `"NOT_ESTABLISHED"`, and null `feasibility` and
`aircraft_status`. Numeric reconstruction does not establish physical validation.

## Exact request schema

```text
{
  evaluation: "solved_dc_electrothermal_mission_experimental",
  usable_energy_j: number,
  reserve_fraction: number,
  thermal_body: {
    mass_kg: number,
    specific_heat_j_kg_k: number,
    initial_temperature_k: number,
    lumped_biot_number: number,
    property_source: string
  },
  segments: [
    {
      id: string,
      duration_s: number,
      point: {
        evaluation: "solved_static_wrench_dc_power_experimental",
        solve: complete accepted V96 solve request,
        motors: complete accepted V96 ordered motor declarations,
        auxiliary: complete accepted V96 auxiliary declaration
      },
      thermal: {
        ambient_temperature_k: number,
        conductance_w_k: number
      }
    }
  ]
}
```

Every shown object has exactly the listed keys. `point` is the full accepted
V96 request, including its existing solve, motor parameters, declared limits,
motor-loss capture fractions/sources, and auxiliary power/heat declarations.
The wrapper adds no caller heat override, electrical-input heat fraction, or
duplicate speed/torque inputs. Segment order defines chronology.

## Preflight and bounds

Before deepcopy, a mission-specific strict builtin JSON walk enforces a global
65,536-node budget, maximum depth 12, at most 256 items per container, strings
of at most 2,000 characters, and integers of at most 1,023 bits. Dictionary
keys must be exact builtin strings; nonfinite floats and nonbuiltin values are
rejected. Depth counts the root as 1. This wrapper-specific depth bound permits
the actual nested mission request reaching depth 11 without flattening `point`.

Every point still passes accepted V96 `_preflight`; its inherited depth-10,
49,152-node point guard and 4,096-node motor guard remain unchanged.
All segments are checked before any point/model execution, including segments
that would follow an unmet solve. There are 1–16 segments, and one global bound:

```text
sum(segment_annuli * (segment_max_evaluations + 1)) <= 32768
```

Numbers must be finite normal builtin integers/floats; booleans are rejected
as numbers. Zero remains valid where declared: reserve, Biot number,
conductance, and inherited V96 zero-valued power/loss/fraction parameters.
Usable energy, duration, mass, specific heat, and absolute temperatures must
be positive. Reserve is in `[0,1)`, Biot in `[0,0.1]`, and conductance is
nonnegative. IDs are unique nonblank strings up to 64 characters; property
and inherited source notes are nonblank strings up to 2,000 characters.
Preflight also checks thermal capacity, reserve arithmetic, and elapsed-time
accumulation for overflow, underflow, subnormal results, or absorbed increments.
A positive reserve must produce a positive representable held reserve.

## Execution and accounting

Each reached segment calls actual V96 DC power evaluation once. At a residual-met
point, electrical power `P` is `total_electrical_power_w`, and captured heat `H`
is independently `total_allocated_heat_w`. Electrical consumption is `P * dt`;
heat is never an additional electrical charge. Auxiliary power and heat are
already included once. Full point power rows retain motor loss and unallocated
motor loss diagnostics.

After every point meets its residual, exactly one chronological thermal request
uses the declared body and segment `heat_input_w=H`, ambient, duration, and
conductance. There is no synthesized `H/P` fraction. Thermal temperature evolves
between segments without feeding back into the point models.

Mission budget is `usable_energy_j * (1 - reserve_fraction)`; held reserve is
usable energy minus that budget. Reserve is withheld once. Checked products,
differences, and nonloss sums support segment/cumulative energy, elapsed time,
joules/Wh, and remaining budget. Negative remaining budget is retained with
`EXCEEDS_DECLARED_ENERGY`; it is a declared-energy screen, not feasibility.

Arithmetic anchor only, independent of the solver fixture: `318.2 W` electrical
and `34.55 W` captured heat for `10 s` give `3182 J` electrical consumption and
`345.5 J` thermal input.

## Validation, provenance, and failure behavior

Point validation checks the actual V96 envelope and request hash, selected solve,
ordered nodes/speeds, DC motor reconstruction at selected speed and row torque,
shaft power and assembly reaction torque, allocations, totals, units, stages,
and transfers. Recursive typed comparisons prevent boolean/numeric equality
from admitting forged values. No point evaluator is rerun by validation.

Thermal validation first applies the accepted structural/conservation checks,
then reconstructs each segment equation with declared mass, specific heat,
conductance, ambient, heat, and duration. It binds chronological temperatures,
elapsed time, maxima, and totals to deterministic accepted arithmetic without
a second thermal evaluator call. Coherent results from a different thermal
body or conductance are rejected. Numeric agreement is not physical proof.

Stages hash actual requests/results and retain actual nested point stages.
Nested result digests remain opaque provenance; their contents are not
independently reconstructed evidence or runtime identity.

Successful outputs are `mission_state`, `power_segments`, `energy`, and `thermal`,
with parallel units. The first unmet solve stops point execution immediately,
retains the reached prefix including that segment, and returns
`STOPPED_AT_UNMET_SEGMENT` with null energy/thermal and their units, and empty
mission transfers. All-met execution uses `COMPUTED_FROM_RESIDUAL_MET_SEGMENTS`.
Preflight failure returns `GRAPH_INVALID` before model calls. Runtime exceptions
return atomic `EXECUTION_FAILED` with empty stages/transfers/outputs/units and
no private exception detail. `BaseException` propagates. Returned data is copied.

## Scope and verification

Accepted V94 behavior is unchanged. DC-equivalent parameters, declared heat
capture, lumped properties, and motor limits remain caller assumptions, not
continuous ratings or thermal adequacy. There is no ESC, bus-current, battery,
SOC, regeneration, installed-flight, or actual aircraft validation. No production,
80% capability, or discovery claim is established.

Current local verification: 86 focused tests passed; Ruff passed on the two new
source/test files. Full drone regression: 4,740 passed, 5 skipped, and 359 subtests
in 63.34 s. An independent Decimal precision-80 grid covered 48 actual two-segment
cases and 768 comparisons. Independent acceptance and physical validation remain
gates. These local results do not establish CI-green status.
