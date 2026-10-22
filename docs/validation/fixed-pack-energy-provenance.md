# Fixed-pack energy and reserve provenance

Internal source review, 22 October 2026. Task DOC-002; source baseline
`5477f94a0c467f1a01e9691a1f9c53613eeffa67`. Author/reviewer: Codex, primary
agent. This is documentation of existing code, without an independent review,
test execution, battery measurement or qualified scientific approval.

## What the designer's energy number means

The local payload solver uses a fixed installed battery. It calculates an
available mission budget from selected battery mass and declared specific
energy, reduces that budget by a usable fraction and held reserve, then compares
electrical demand against it. It does not estimate an actual battery's capacity
from its geometry or simulate discharge, voltage sag or temperature.

The code's variable `density` in `pack_consistency` means **specific energy in
Wh/kg**, not atmospheric density, material density or volumetric energy density.
The output `pack_mass_kg` is the selected battery mass, not total aircraft mass.

## Derivation and units

Observed formula in [screening_scope.py, line 37](../../src/physimesh/drone/screening_scope.py#L37):

```text
m_pack = sum(mass_kg of explicitly named energy-category items)
E_available_J = m_pack_kg * pack_Wh_per_kg * usable_fraction
                * (1 - held_reserve_fraction) * 3600_J_per_Wh
```

The dimensional product is kg * Wh/kg * 1 * 1 * J/Wh = J. The conversion
3600 J/Wh is exact unit bookkeeping: watt is joule per second and an hour is
3600 seconds. [NIST SP 811, chapter 5, table 6](https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-5-units-outside-si)
provides the hour conversion. This unit definition does not validate the
declared Wh/kg or the two fractions.

`usable_fraction` is applied first. Reserve is a fraction of that already
usable energy, not a fraction added to demand or a separate absolute joule
quantity. `usable_energy_j` supplied by the caller must already have both
reductions included; a pre-reserve value will generally fail consistency.

## Inputs, guards and provenance

All input fields below are relative to the frozen design snapshot. No real
aircraft value is supplied or approved by this document.

| ID | Field / source location | Units and existing guard | Provenance or limitation |
|---|---|---|---|
| E01 | [mission.energy_system, mission.reserve_policy, masses.items, lines 16-20](../../src/physimesh/drone/screening_scope.py#L16) | Records and ledger items must be available for extraction. | INPUT. Root manifest template leaves energy/reserve null and mass items empty. No implicit battery or reserve value is generated here. |
| E02 | [energy_system.pack_mass_item_names, lines 18-25](../../src/physimesh/drone/screening_scope.py#L18) | Nonempty list of unique strings; every name exists and refers to category energy. Duplicate names anywhere in the mass ledger refuse. Selected masses summed with math.fsum, in kg. | INPUT / POLICY. Selection is explicit; no STL-derived mass and no automatic sum of all aircraft mass. Not all energy-category items are necessarily selected. Physical completeness of the selection is not authenticated. |
| E03 | [mass items and candidate mass](../../src/physimesh/drone/authoring.py#L11) | Authoring requires meaningful unique item names; numeric nonboolean item masses. [mass.summarize, lines 58-98](../../src/physimesh/drone/mass.py#L58) checks finite nonnegative masses, required categories, CG and positive total mass. | INPUT / POLICY. candidate_mass replaces payload entries only, leaving installed battery mass in the ledger. Batteries are not added again as a separate mass in trim. Physical measurements, pack hardware coverage and mass uncertainties remain UNVERIFIED. |
| E04 | [energy_system.pack_wh_per_kg, lines 26-36](../../src/physimesh/drone/screening_scope.py#L26) | Wh/kg; extracted specific energy must be finite nonboolean numeric and >0. | INPUT. No default, measured provenance field, chemistry, rate, temperature, age or uncertainty is enforced by this helper. Caller-entered specific energy is not measured pack qualification. |
| E05 | [energy_system.usable_fraction, lines 26-36](../../src/physimesh/drone/screening_scope.py#L26) | Dimensionless; finite nonboolean numeric, 0<f<=1. | INPUT. No default or validated discharge window follows from this range check. Whether Wh/kg already includes the same reduction is outside the helper's knowledge. |
| E06 | [reserve_policy.kind/convention/value, lines 27-36](../../src/physimesh/drone/screening_scope.py#L27) | kind exactly fraction; convention exactly held_usable_energy_fraction when supplied; absent convention has that historical default. Value r finite nonboolean numeric, 0<=r<1. | INPUT / POLICY. Missing value refuses. Missing convention retains one specific legacy meaning; it does not authorize other reserve interpretations. A source label or valid fraction is not operational reserve approval. |
| E07 | [energy_system.usable_energy_j and aggregate mass, lines 25-36](../../src/physimesh/drone/screening_scope.py#L25) | J and kg; declared E and summed mass finite nonboolean numeric and >0. | INPUT / POLICY. This helper checks summed mass, not each selected mass before summation. It is not a replacement for the authoring/mass validation in E03. |
| E08 | [derived energy, lines 37-39](../../src/physimesh/drone/screening_scope.py#L37) | J; finite and >0 after multiplication. | DEFINITION / POLICY. Reject overflow/underflow or nonpositive result. The factor (1-r) is the held-reserve model convention. No fitted coefficient or empirical uncertainty allowance is added. |
| E09 | [consistency, lines 42-45](../../src/physimesh/drone/screening_scope.py#L42) | Relative tolerance 1e-9, absolute tolerance 0 J. For positive finite inputs, abs(E_declared-E_derived)<=1e-9*max(E_declared,E_derived). | POLICY. Python math.isclose semantics as explicitly configured. Historical numerical agreement only; no primary scientific rationale or qualified approval for this magnitude is established. It is not a battery accuracy percentage. |
| E10 | [outcomes and receipt, lines 40-48](../../src/physimesh/drone/screening_scope.py#L40) | Extraction/domain errors return inputs_incomplete / pack_inputs_unresolved and detail. Valid formula inputs return consistent or inconsistent / pack_energy_consistency. | POLICY. Receipt includes selected names, mass, declared/derived J, tolerance, formula and convention. It does not embed measured source hashes or attestations for each battery parameter. Unknown extra keys are not rejected by this helper. |

Boundary E07 matters: `math.fsum` precedes the aggregate numeric guard. A
`consistent` pack receipt alone does not prove that individual masses, CGs or
the rest of the aircraft ledger are valid. The local trim path calls
[candidate_mass and checks completeness before pack consistency](../../src/physimesh/drone/trim.py#L122).
[inspect_inputs](../../src/physimesh/drone/authoring.py#L46) exposes mass and pack
reports separately. Whether all callers preserve that distinction is a useful
next source-audit question; no failing runtime case is claimed here.

## Schema boundaries and reserve conventions

The [legacy YAML template](../../src/physimesh/drone/schema/drone_manifest_v1.yaml#L15)
is reconstructed, with energy_system/reserve_policy null. Its general
[feasibility readiness check](../../src/physimesh/drone/models.py#L346) requires
those records but is not the specialized fixed-pack consistency check.

The broader [MissionDefinitionV1](../../src/physimesh/projects/contracts.py#L163)
can represent three reserve conventions and fixed/sized pack modes. That schema
expressiveness does not establish solver support:

| Convention | Typed value units / legacy kind | Fixed-pack helper behavior |
|---|---|---|
| held_usable_energy_fraction | Dimensionless, [0,1); fraction | Supported meaning; held once in E_available. |
| held_energy_j | J, nonnegative; energy_j | Refused by this helper. No absolute-reserve conversion is implemented here. |
| additional_mission_demand | Dimensionless, nonnegative; additional_mission_demand_fraction | Refused by this helper. Do not reinterpret as a held fraction. |

[bound_mission, lines 213-224](../../src/physimesh/projects/contracts.py#L213)
requires explicit typed/legacy reserve convention, kind and value agreement, plus
energy_system.pack_mode agreement, for approved-design binding. In contrast,
the [local trim eligibility](../../src/physimesh/drone/trim.py#L128) checks
energy_system.mode=fixed and voltage_model=declared_constant_bus. `pack_mode`
and `mode` belong to different contract paths; this review performs no migration
or automatic substitution. Typed screening approval also restricts the reserve
convention to held usable-energy fraction. See the existing
[production-data contract](../contracts/production-data.md).

## Where reserve stops being applied

1. [prepare_hover](../../src/physimesh/drone/trim.py#L125) requires pack status
   consistent and passes **derived** available J into HoverInputs at
   [line 208](../../src/physimesh/drone/trim.py#L208). Declared power/current limits
   and constant bus voltage are separate power gates, not energy coefficients.
2. [per-case constraints](../../src/physimesh/drone/trim.py#L232) enforce rotor
   power plus declared auxiliary power within available J/duration as well as
   pack watts/current limits. No second multiplication by (1-r) occurs there.
3. [joint_constraints](../../src/physimesh/drone/mission_capacity.py#L79) sums
   case electrical demand weighted by segment durations, adds auxiliary J once
   per segment, and uses min(case.usable_j). With ordinary cases these budgets
   derive from the same snapshot pack. It does not sum independent batteries or
   reset available energy between segments.
4. [solve_sequence, lines 134-149](../../src/physimesh/drone/mission_capacity.py#L134)
   recomputes constant-power E=P*t in J, tracks cumulative consumption and
   remaining J, and labels reserve held_usable_energy_fraction_applied_once.
   Its energy slack is 1e-7*max(1 J,available J), distinct from E09. See the
   [constants ledger](drone-constants-ledger.md) for the other numerical policies.
5. [SequenceEvidence](../../src/physimesh/drone/local_results.py#L115) checks
   each P*t, remaining-energy step, total and budget using the retained positive
   energy_tolerance_j. It binds the applied-once convention and exact-constant-
   power integration label. Typed consistency cannot authenticate battery data
   or prove that a forged caller-selected tolerance is scientifically acceptable.

The [mission-capacity contract](../contracts/mission-capacity.md),
[ADR-0003](../decisions/ADR-0003-static-hover-profile.md) and
[earlier hover/energy receipt](local-hover-and-energy.md) document this scope.
The energy arithmetic has no timestep or quadrature refinement; it is not a
time-dependent battery model or installed-aircraft conservation experiment.

## Existing fixture evidence, inspected without execution

| Source | Declared synthetic values / assertions read | Claim limit |
|---|---|---|
| [test_screening_scope.py, lines 14-36](../../tests/drone/test_screening_scope.py#L14) and [demo_screening.py](../../src/physimesh/drone/demo_screening.py#L19) | 20 kg, 250 Wh/kg, f=.8, r=.2; assertion 11,520,000 J. Pre-reserve declared J refuses; 10 kg case asserts 5,760,000 J and inconsistency with old declared J. Invalid fraction/specific-energy/selection cases are present. | These numbers are fixture definitions and assertions, not newly observed outputs or recommended battery specifications. |
| [test_screening_scope.py, lines 73-83](../../tests/drone/test_screening_scope.py#L73) | Malformed selection produces a structured refusal; explicit conflicting reserve conventions refuse. | Presence of a test does not prove every malformed raw mass is checked by every caller. |
| [test_hover_pilot.py, lines 23-28](../../tests/drone/test_hover_pilot.py#L23) and [lines 154-175](../../tests/drone/test_hover_pilot.py#L154) | 2 kg, 100 Wh/kg, f=.8, r=.2 with declared 460800 J; shared-sequence budget and reserve-removal assertion with 576000 J. | Synthetic LP/energy fixtures; not measured discharge, duty or operational reserve evidence. |

No tests, project/demo functions, solver calls or experimental campaigns were
executed for DOC-002. Static source/hash/link/whitespace checks are recorded in
[DOC-002 evidence](../../.physicore/evidence/DOC-002-static.json); these checks do
not evaluate the above energy calculation or assert physical correctness.

## Remaining evidence and next step

- Measured installed battery mass, source Wh/kg with test conditions, electrical
  limits, usable-window definition, reserve owner/rationale and uncertainty are
  missing for the real aircraft. Fractions may double-discount already-derated
  source data unless their meanings are established outside this helper.
- No rate, temperature, aging, SOC, sag, conversion-loss, transient-power or
  cooling/reset behavior is established by this formula. Rotor/map duty coverage
  is separate from a measured battery duty envelope.
- SCI001-SCI003 and DATA001 in [approvals](../../.physicore/ops/APPROVALS.md)
  remain pending. This document changes no equations, default inputs, tolerances
  or acceptance status.
- Next safe task: audit the raw pack-input validation boundary and its callers,
  particularly individual selected masses and how separate mass/pack outcomes
  reach the app. Document any concrete gap before proposing a behavior change.
