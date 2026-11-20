# Claude first independent local-hover review

Exact candidate: `07b9f192d55fd79c0cb209ece063bd029ce3d93e`. Text-only source review through the locally installed Claude CLI, with tools disabled. No test execution or measured validation. Initial verdict FAIL is retained; corrections and another exact-candidate review are required before merge.

# Independent review: candidate `07b9f192d55fd79c0cb209ece063bd029ce3d93e`

**Verdict: FAIL**

This is a textual review of the supplied packet only. I did not execute anything, and it is not measured validation.

The core feasible-path physics is correct: signs, couples, efficiency, epigraph, energy and reserve, and the recomputation. The FAIL is for outcome and evidence meaning, which is in the requested scope:

- **M1:** A certified `infeasible` outcome can rest only on map-coverage or declared payload-domain bounds. The contract says uncovered data is `unsupported`, so these outcomes claim more than the evidence supports.
- **M2:** In the sequence path, `limiting_case_id` can name the wrong case, and the V2 contract accepts it.

Neither defect publishes a wrong payload number. Both misstate what a retained record means. Both look like small, local fixes. After those fixes and a re-review I would expect PASS_BOUNDED_LOCAL.

---

## Verified correct (within the restricted model)

| Check | Location | Result |
|---|---|---|
| Force balance | `trim.py` `constraints` | `Σ axis_i·T_i + p·g = −F_body − m_e·g`, with g = (0,0,−G0) in the z-up body at zero attitude. Correct. |
| Origin moments | `constraints` | Thrust term: `cross(c_i, axis_i)·T_i`. Reaction term: `−s_i·axis_i·(k_Q·T_i + Q_0)`, with the affine offset moved to the RHS. Payload term: `cross(p_pos, g)·p`. Empty-aircraft term `cross(m_e·cg_e, g)` is on the RHS. `body_moment` is taken as already about the origin, so there is no extra cross term. Correct. |
| CG moments in recompute | `recompute` | `M_CG = M_O − CG×F_total` expands to `Σ(r_i−CG)×F_i + reactions + M_body,O − CG×F_body`. Gravity acts at the CG and drops out. Correct. |
| Reaction sign | `constraints`, `recompute` | The motor drives the rotor with `+s·axis·Q`, so the airframe receives `−s·axis·Q`. This is consistent in both places. |
| Torque affine in thrust | `performance.py` `convex_static_profile` | T, Q and P are all linear in RPM on the same knots. Affinity at the knots therefore implies affinity everywhere. A negative slope is refused. |
| Q·ω and efficiency applied once | `RotorMapV1.consistency`, `evaluate`, `convex_static_profile` | Shaft watts must equal Q·ω at the knots. `evaluate` forms the product at the query point, then divides by η once. The profile divides knot power by η once. An electrical map with an efficiency is refused. With constant Q, Q·ω is linear in RPM, so the LP and the query agree exactly. |
| Electrical ≥ shaft between knots | `evaluate` | Q is nondecreasing in RPM, so Q(ω)·ω is convex on each segment and lies below its chord. The knot checks are therefore sufficient. |
| Convex epigraph | `constraints` | P_i ≥ every affine piece, and every use of P_i is an upper bound (rotor, pack, energy). The projection is exact for convex PWL, and recompute uses the true map power. Minimising ΣP at fixed payload yields P_i = f(T_i). |
| Finite domain | `prepare_hover` | Thrust is bounded to [map floor, T(min(max_rpm, map max))]. Payload is bounded to the declared domain. No extrapolation is used. Density, inflow and pitch must match the map. One full covered interval is required. |
| Power/current, counted once | `prepare_hover`, `constraints`, `solve_hover` | Rotor limit is `min(P_max, V·I_max)` and pack limit is `min(P_max, V·I_max)`. Auxiliary power is subtracted once in the LP and added once in recompute. |
| Energy/reserve, counted once | `screening_scope.pack_consistency`, `mission_capacity` | `E = m·Wh/kg·f_u·(1−r)·3600` must match the declared value to 1e-9. It is not reduced again. The joint row is `Σ d_c·P_c + Σ d_c·P_aux ≤ E`. The ledger re-adds actual powers. |
| Joint → fixed-payload recheck | `solve_sequence` | Re-solving at fixed payload with min-ΣP gives recomputed power no greater than the LP's. The final budget check is therefore sound, not optimistic. |
| Common payload (alternatives) | `capacity_from_snapshot` | Each case's feasible payload set is an interval. The minimum of the maxima, rechecked in every required case, is the intersection maximum when one exists. Otherwise the result is `unresolved`. |
| Certificate algebra | `infeasibility_certificate` | This is a Farkas system with equalities as ± rows and finite boxes. The verified condition is: minimum over the box of `yᵀA·x` exceeds `yᵀb`. That is a valid proof of LP infeasibility, up to the floating-point guard. |
| Solver status | `solve_hover`, `solve_sequence` | Success alone never gives `feasible`. Time limits and other statuses give `unresolved`. Out-of-bounds or nonfinite results are rejected rather than clamped. |

---

## Findings

### Medium

**M1. `infeasible` can be certified by coverage or analyst-domain bounds, not physics.**

- **Where the bounds come from:** `src/physimesh/drone/trim.py`:
  - `prepare_hover`, `bounds.append((model.points[0].thrust_n, …evaluate(min(max_rpm, map max))…))`
  - `constraints`, `bounds.append(inputs.payload_bounds …)`
- **Where they are used:** `infeasibility_certificate` takes its box minimum over all bounds. `solve_hover` then returns `'infeasible' if certificate`. `capacity.py` propagates that to the study outcome.
- **What goes wrong:** The box mixes three kinds of bound:
  - physical bounds: payload ≥ 0, and thrust ≥ 0 at 0 RPM;
  - declared limits: rotor RPM, power and current;
  - data and analyst bounds: the map's first and last thrust knots, and `payload_domain_kg`.
  
  The certificate does not record which kind it relied on.
- **Concrete case 1:** Take the `test_zero_payload…` design, which needs p ≥ 4 kg, and set `payload_domain_kg = [0, 3]`. The result is `infeasible` with a valid certificate, yet the aircraft can carry 4 kg.
- **Concrete case 2:** Declare `max_rpm` above the map's top RPM, and let the weight exceed the map's maximum total thrust. The result is `infeasible`, but the real limitation is the uncovered map.
- **Why it matters:** This contradicts `mission-capacity.md` ("Missing or uncovered physics/data is `unsupported`") and ADR-0003 ("Physical infeasibility requires…").
- **Fix direction:** Tag each bound with its provenance. Downgrade to `unsupported` (or a distinct label) when either of these holds:
  - a coverage or domain bound row has a positive multiplier;
  - the box minimum takes a coverage or domain endpoint with a nonzero combined coefficient.

**M2. Sequence-path `limiting_case_id` can be wrong, and the contract accepts it.**

- **Where:** `src/physimesh/drone/capacity.py`, sequence branch. The relevant line is `individual = min(needed, key=…)`, and the binding decision is `aggregate_binds = abs(remaining) <= energy_tolerance_j`.
- **Problem 1:** `needed` contains only required cases. However, `selected`, and therefore the joint LP, also contains non-required cases referenced by the sequence.
- **Concrete case:** A non-required case B has a downward `body_force_body_n`, so its individual maximum is lower. B is used in a short segment and energy does not bind. The joint headline then equals B's limit, but `limiting_case_id` names a required case A whose individual bound is higher.
- **Problem 2:** Attribution uses the energy-tolerance test instead of checking that the attributed case's individual payload equals the headline. Near the tolerance, the case named can disagree with the headline.
- **Why the contract does not catch it:** `local_results.py` `LocalCapacityV2.headline` only checks `limiting_case_id in required`.
- **Fix direction:**
  - Attribute over every case in the joint program.
  - Require the attributed case's individual `candidate.payload_kg` to equal the headline within a stated tolerance; otherwise use `limiting_case_id=null`.
  - Validate the same condition in the contract.

### Low

**L1. Non-required sequence cases import their standalone endurance row.**

`joint_constraints` calls `constraints(case)`, which includes `case_energy: ΣP ≤ E/case.duration_s − P_aux`. `solve_sequence` then rechecks with `solve_hover`, which applies the same row. A non-required case's own `duration_s` therefore becomes a binding requirement. This is conservative, but it is not the stated semantics.

**L2. Results are nondeterministic for identical frozen inputs.**

HiGHS `time_limit` (1 s, or 2 s for the joint program) is wall-clock time. Under load, the same `study_sha256` could be retained as `unresolved` instead of `feasible`. "First winner retained" then fixes that outcome, and neither the spec nor the record captures it.

**L3. The solver-output bound check has no tolerance.**

`solve_hover` and `solve_sequence` use `value < lo or value > hi`. HiGHS returns values within its feasibility tolerance, so a value like −1e-12 at a zero thrust floor becomes a spurious `unresolved`. This only costs availability; it never makes a result optimistic.

**L4. `LocalCapacityV2` has consistency gaps.** None of these change produced results, but altered or hand-made records would pass:
- A top-level `outcome='infeasible'` from the sequence path is accepted with no `certificate`.
- `outcome='feasible'` does not require each required entry in `cases` to be feasible.
- `aggregate_limit='sequence_energy'` is accepted without remaining energy ≈ 0, and can coexist with a non-null `limiting_case_id`.
- Residual tolerances are self-declared by the record.
- There is no check that the headline is at or below each required case's individual bound.

**L5. Unhandled `AttributeError` (conditional on the snapshot schema, which was not supplied).**

`prepare_hover` calls `rotor.get('sustained_limits', {}).get`, `snapshot['fidelity'].get` and `frames.get`. A null or non-mapping value raises `AttributeError`. The `except` tuples in `capacity.py` do not include `AttributeError`, so this becomes a server error instead of `unsupported`.

**L6. Readiness disagrees with the run.**

`hover_readiness` prepares every case, including ineligible non-required ones, for the sequence check. This blocks readiness when `capacity_from_snapshot` would still proceed. It is conservative.

### Informational

- **Inconsistent active-constraint tolerances.** `case_energy` uses 1e-4 J absolute and the others use 1e-6 W. These affect labels only.
- **Sign convention undocumented.** `rotation_sign` means right-hand rotation about `axis_body` only by implication. The test asserts the same formula as the code, so a UI that maps CW/CCW "viewed from above" would not be caught.
- **Convexity tolerance.** The `−1e-10` tolerance admits slightly nonconvex maps. Their max-affine surrogate overestimates power, which is conservative for feasibility and negligible for certificates.
- **Measured maps are practically ineligible.** Affine torque at rtol/atol 1e-10, and constant torque for shaft maps, mean measured data will almost always refuse. Eligibility is effectively limited to idealised data. This is a limit, not a defect.

---

## What the supplied tests cannot establish

- **Untested model terms:**
  - nonzero `body_force` (the `−CG×F_body` term) and nonzero `body_moment`;
  - z-offset CG or rotors;
  - tilted axes;
  - a nonzero torque offset `Q_0` (all fixtures use Q = 0.02·T);
  - a power curve with more than one distinct slope (all fixtures use P = 10·T), so the multi-piece epigraph is untested.
- **Limits never binding:** the shaft-basis LP path (only `evaluate` is tested), and binding rotor power, rotor current or RPM limits below map maximum.
- **Sequence combinations:** auxiliary power with a sequence, multiple distinct cases in a sequence, non-required sequence cases, and required cases outside the sequence.
- **Domain and labelling:** a binding payload-domain upper bound, a nonzero domain lower bound, active-constraint labels, joint certificates with nonzero thrust floors, and HiGHS tolerance-edge outputs.
- **Defects above:** no test detects M1 or M2.
- **Independence:** The recompute shares geometry, sign convention and `candidate_mass` with the allocation. It independently checks the affine fit, the CG transfer and the map evaluation, but not the convention. Certificates prove infeasibility of the constructed LP, not of the aircraft.
- **Headline optimality:** The headline is a checked feasible point. No dual or upper bound is retained, so optimality is shown only by the analytic fixtures.
- **Measured reality:** Nothing establishes measured map accuracy, installation effects, motor/ESC/battery duty, sag, thermal behaviour or uncertainty.

## Precise reviewed limits

| Area | Limit |
|---|---|
| Code | Packet contents at `07b9f192`, read as text. `parse_snapshot`, `Record`, `canonical_json`/`sha256_record`, the artifact store, the API and the example-project fixture were not reviewed. |
| Model | Static hover: zero attitude, rates, velocity, acceleration and inflow. Fixed axes and positions. Sourced constant body loads about the origin. One payload position. |
| Rotor maps | Fixed-condition maps with one full covered RPM interval, strictly increasing thrust, affine nondecreasing torque, and convex nondecreasing PWL electrical power. Shaft basis only with constant torque and one declared efficiency. |
| Electrical and energy | Declared constant DC bus and fixed pack. Reserve held once. Constant-power segments only. Continuous duty is applied to the total flight, with no cooling. |
| Outputs | Feasible headlines and segment ledgers are internally consistent with this model. `infeasible` outcomes (M1) and sequence `limiting_case_id` (M2) are not accepted. |
| Not covered | No aircraft validation, operational payload allowance or flight release. Engineering approval remains pending. |