# Physics Spec: Existing static-hover payload and fixed-pack energy baseline

Status: AWAITING SCIENTIST
Domain: drone
Author: Codex, spec-writer role   Reviewer: UNASSIGNED   Date: 2026-10-22

## 1. What this feature does (plain language, 3 lines max)

Qualify the existing `convex_static_hover_v1` model that finds a bounded payload compatible with every required static-hover case.
For an ordered mission of constant conditions, check that the same payload fits one fixed battery energy budget with reserve held once.
Deliver comparison plots and an evidence report that distinguish software checks from measured aircraft accuracy.

## 2. Why the product needs it

The confirmed product goal is payload across the required mission, with the limiting condition and evidence visible. Before extending mission or battery physics, the existing equations, restrictions and acceptance gaps need a reviewable baseline. Geometry by itself supplies neither aircraft mass nor propulsion capability.

This spec qualifies existing behavior described in [ADR-0003](../docs/decisions/ADR-0003-static-hover-profile.md) and [local hover/energy verification](../docs/validation/local-hover-and-energy.md). It authorizes no solver, test, source-data or tolerance change. The broader `convex_axial_capacity_v2`, source conditioning, failure scenarios, axial climb, variable power, battery sag, SOC and thermal models require their own scopes. Existing evidence keeps its original scope; this document does not retroactively approve it.

Customer-approved accuracy: **UNKNOWN**. Scientist-identified main weakness: **UNKNOWN**. The spec-writer's proposed risk is insufficient measured source, installation and duty coverage for an aircraft payload claim. A scientist and named client engineering owner remain unassigned; an agent cannot supply their approval.

## 3. Governing equations

All vectors use the body frame, x forward, y left, z up; the zero-attitude world frame is ENU, z up. Positions and declared body moments refer to the same body origin O. Index i denotes a rotor, j an ordered segment and k a non-payload mass-ledger item. The following are the existing model equations, not new fitted correlations.

\[
m=m_p+\sum_k m_k,\qquad
\mathbf c=\frac{m_p\mathbf r_p+\sum_k m_k\mathbf r_k}{m}.
\]
Plain English: replace the ledger's payload with the candidate mass, count the installed battery once, and calculate the combined center of gravity.

\[
\rho=\frac{p_{abs}}{R_{air}T_{air}},\qquad
\omega_i=\frac{2\pi}{60}N_i.
\]
Plain English: derive the query density from absolute pressure and temperature, and convert the retained RPM command to radians per second.

\[
\mathbf F_i=T_i\mathbf a_i,\qquad
\boldsymbol\tau_i=-s_i Q_i\mathbf a_i.
\]
Plain English: thrust follows the unit rotor axis, and the airframe reaction opposes the declared right-hand shaft rotation sign.

\[
\mathbf R_F=\sum_i\mathbf F_i+\mathbf F_b-mg_0\hat{\mathbf z}=\mathbf0.
\]
Plain English: all three force components must balance at zero translational acceleration.

\[
\mathbf R_M=\sum_i[(\mathbf r_i-\mathbf c)\times\mathbf F_i+\boldsymbol\tau_i]
+\mathbf M_{b,O}-\mathbf c\times\mathbf F_b=\mathbf0.
\]
Plain English: all three moments must balance about the candidate center of gravity; translate the declared body-load moment from O, while gravity has zero lever arm there.

The zero-acceleration force balance is consistent with [MIT's quadrotor equations](https://underactuated.mit.edu/acrobot.html); the vector moment translation and sign convention above are the repository's explicit formulation in ADR-0003 and `trim.recompute`. MIT's reduced model is an equation reference, not validation of this aircraft or these maps.

\[
P_{shaft,i}=Q_i\omega_i,\qquad
P_{DC,i}=\begin{cases}P_{map,i},&\text{electrical map},\\P_{shaft,i}/\eta_i,&\text{eligible shaft map},\end{cases}
\qquad P=P_{aux}+\sum_iP_{DC,i}.
\]
Plain English: use measured electrical watts directly, or convert shaft watts through one explicitly sourced efficiency, then add auxiliaries once.

\[
P_{DC,i}\le\min(P_{i,cont},V_{bus}I_{i,DC,max}),\qquad
P\le\min(P_{pack,cont},V_{bus}I_{pack,DC,max}).
\]
Plain English: each rotor and the pack must respect both declared continuous power and DC input-current limits at the fixed bus voltage.

\[
E_u=m_{pack}e_{Wh/kg}\,3600\,f_u(1-f_r),\qquad
E_{mission}=\sum_jP_j\Delta t_j,\qquad
E_{remaining,j}=E_u-\sum_{\ell\le j}P_\ell\Delta t_\ell\ge0.
\]
Plain English: form one usable pack budget after reserve, then carry the remaining energy through constant-power segments without applying reserve again.

\[
Q_i(T_i)=q_{0i}+q_{1i}T_i,\qquad
P_{DC,i}(T_i)=\max_\ell(a_{i\ell}T_i+b_{i\ell}),\qquad
p_{max}=\max_{\mathcal F}m_p.
\]
Plain English: the eligible affine torque and convex piecewise-linear power maps make the bounded static feasible set a linear program; its optimum is only a model-domain bound.

The feasible set includes every required case, common payload and payload position, finite source/analyst bounds, per-case energy limits and any declared sequence budget. A mission headline is accepted only after a fixed-payload recomputation passes all participating cases. It is not obtained by combining incompatible per-case rotor commands into one fictional operating point.

## 4. Assumptions (scientist checks this section hardest)

| # | Assumption | Why it is OK | When it breaks |
|---|---|---|---|
| A1 | Rigid aircraft, fixed rotor centers/axes and one explicit payload position; complete non-payload ledger | Defines the existing bounded equilibrium problem; review pending | Flexibility, moving payload, missing masses, uncertain installation geometry |
| A2 | Zero attitude, translational velocity, angular rates and accelerations; explicitly sourced constant body loads | Makes static force/moment balance applicable | Maneuvers, forward flight, climb, wind-dependent or transient loads |
| A3 | Isolated rotor maps apply only at the retained density, zero inflow, pitch and configuration, within one complete covered RPM interval | Refusal prevents unsupported extrapolation; physical installation applicability remains unproven | Rotor interference, ground effect, other atmosphere, blade changes or missing intervals |
| A4 | Thrust strictly increases with RPM; torque is nondecreasing affine in thrust; electrical power is convex and nondecreasing in thrust | Existing LP eligibility checks enforce this restricted function class | Noisy/nonconvex data or varying-torque shaft curves; do not condition data silently to force eligibility |
| A5 | A shaft map uses one sourced constant conversion efficiency; baseline LP shaft maps have constant torque | Preserves the existing product-of-torque-and-speed interpolation and linear allocation | RPM/load-dependent efficiency, unsupported varying shaft torque, double efficiency conversion |
| A6 | Fixed pack mass, constant bus voltage, declared usable fraction and reserve; auxiliaries included once | Defines the existing energy accounting exercise | Sag, SOC/temperature/rate effects, pack resizing, transient loads or unmeasured duty limits |
| A7 | No cooling/reset between chronological segments; map continuous-duty coverage spans the entire active mission duration | Conservative existing coverage rule when reset evidence is absent | Claiming duty from isolated short runs, unsupported cooling or changing hardware limits |
| A8 | Required cases are mandatory and sequence segments share one payload and one energy budget | Matches the product question and avoids selecting only favorable cases | Missing required case, mutually inconsistent inputs or undeclared mission chronology |
| A9 | Historical numerical tolerances establish arithmetic acceptance only | Separates software roundoff from physical discrepancy | Using a tiny residual as a flight margin or claiming measured accuracy from synthetic agreement |
| A10 | No spatial/time discretization exists in this static algebraic model; proposed L3 substitute requires approval | A mesh GCI would describe no implemented operation | Adding time-varying battery/flight or spatial flow physics without a new convergence protocol |

## 5. Inputs, outputs, units (SI)

| Quantity | Symbol | Unit | Typical range | Source |
|---|---|---|---|---|
| Ledger and payload masses | m_k, m_p | kg | Nonnegative; finite declared payload domain; real range UNKNOWN | Retained snapshot and approved mass ledger, real approval missing |
| CGs, payload/rotor positions | c, r_k, r_p, r_i | m | Finite 3-vectors; real envelope UNKNOWN | Snapshot, installation/mass evidence |
| Rotor axis and rotation sign | a_i, s_i | 1 | Unit vector; sign +1 or -1 | Explicit installation and frame declaration |
| Pressure, temperature, derived density | p_abs, T_air, rho | Pa, K, kg/m³ | Positive; density must match map; real range UNKNOWN | Case atmosphere and retained source |
| Rotor speed, thrust, torque | omega_i, T_i, Q_i | rad/s, N, N m | Retained covered interval and declared sustained limits | Map bytes/metadata; schema retains RPM N at input boundary |
| Pitch and inflow | theta_i, v_ax | rad, m/s | Fixed retained pitch; baseline inflow 0 | Map/case; schema pitch is degrees at boundary |
| Body force and moment at O | F_b, M_b,O | N, N m | Finite explicitly sourced vectors, including declared zero | Case `body_load_source` |
| DC power, voltage, current; efficiency | P, V_bus, I_DC, eta | W, V, A, 1 | Positive voltage/limits; 0 < eta <= 1 when applicable | Pack, motor/ESC and map provenance; no phase-current inference |
| Pack specific energy, fractions | e, f_u, f_r | J/kg, 1, 1 | e > 0; 0 < f_u <= 1; 0 <= f_r < 1 | Snapshot stores Wh/kg, converted once; source/approval required |
| Case/segment duration | Delta t | s | Positive; within source continuous duty; 1-32 sequence segments | Required mission declaration, not guessed duty |
| Payload bound/status and governing constraints | p_max | kg | Within declared common domain | Retained result and fixed-candidate checks |
| Balance residuals and energy ledger | R_F, R_M, E | N, N m, J | Signed components and remaining energy reported | Independent candidate recomputation, not optimizer status |

Real client ranges remain unknown. Synthetic values in section 10 are test inputs, not recommended aircraft design values. Retain the model version, snapshot hash, original map bytes/hash, source/license, configuration, condition metadata, power basis, efficiency source, duty, software versions and tolerance policy with each result.

## 6. Boundary and initial conditions

There is no CFD domain, mesh boundary, initial dynamic state or imposed flow solution in this scope. Set attitude, velocity, acceleration, angular velocity and angular acceleration explicitly to zero; use the declared z-up frames. Each rotor has one fixed center, unit axis, rotation sign, pitch and sustained RPM/DC bounds. Static body loads include their source and origin convention. Absolute pressure and temperature define the case density; no implicit density correction of a map is allowed.

The pack is installed once in the mass ledger. Its available energy starts at E_u after usable fraction and held reserve. Each ordered segment has constant conditions, duration and a source note. The sum of segment durations must fit continuous-duty source coverage. Case alternatives are not automatically chronological segments, and optional cases are not silently promoted into required cases.

## 7. Numerical method

Existing implementation: `src/physimesh/drone/{performance,trim,capacity,mission_capacity}.py`. Piecewise-linear interpolation is confined to retained RPM samples. Electrical maps interpolate retained electrical power; shaft queries recompute Q times omega and apply efficiency once. The baseline LP additionally requires constant-torque shaft curves, affine torque in thrust and a convex nondecreasing electrical-power curve over one full interval. Unsupported data are refused rather than extrapolated.

SciPy HiGHS solves the bounded linear allocation with thrust, power-epigraph and payload variables. Retain the actual SciPy/HiGHS runtime versions. Existing solver limits are 1 s/10,000 iterations per hover solve and 2 s/10,000 iterations per sequence solve; these are computational limits, not a stability or physics condition. Candidate values outside bounds are rejected, not clamped. Final source interpolation recomputes all six balance residuals, power, current and energy at the shared candidate payload.

`feasible` means a checked point within this bounded model. `infeasible` requires a checked contradiction certificate with physical-bound provenance. Source/analyst-domain limitations produce `unsupported`; numerical failure without a certificate produces `unresolved`. Do not interpret solver failure as proof that the real aircraft cannot fly, or a finite analyst upper bound as a physical maximum.

No timestep, CFL limit, spatial discretization order or mesh GCI exists. Constant-power integration is exact apart from floating-point arithmetic. Proposed L3 substitutes are segment subdivision invariance, redundant collinear map-knot invariance, and repeatability under documented LP scaling, with independent balance/energy recomputation. Scientist approval of this applicability exception is required; interpolation holdout error is a different check and cannot be called mesh convergence.

## 8. Constants and coefficients

| Name | Value | Unit | Source (paper/standard) | Verified? |
|---|---|---|---|---|
| Standard gravity g_0 | 9.80665 | m/s² | `atmosphere.G0`; [NIST reference, equation 30](https://www.nist.gov/system/files/documents/srd/jpcrd574.pdf) | External value checked; local-site gravity assumption approval pending |
| Dry-air gas constant R_air | 287.05 | J/(kg K) | `atmosphere.R_AIR`, historical manifest [M section 4] | UNVERIFIED primary provenance/configuration approval |
| Time conversions | 60 s/min; 3600 s/h | s/min; s/h | [NIST SI guide, chapter 5](https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-5-units-outside-si) | Exact unit conversion; schema boundary retained |
| Full-turn conversion | 2 pi | rad/revolution | Geometric definition; `math.pi` in existing shaft-power calculation | Definition, not fitted physics |
| Map q_0, q_1, a_l, b_l | Dataset-dependent | N m; m; W/N; W | Retained original map and explicit interpolation | Real values/uncertainty UNKNOWN; fixture values synthetic |
| Efficiency, usable and reserve fractions | Declared, never defaulted by this spec | 1 | Snapshot/map efficiency source and reserve policy | Real sources/approval UNKNOWN |
| Force arithmetic policy | max(10^-7 N, 10^-8 F_*) | N | `trim.RESIDUAL_ABS_N`, `RESIDUAL_REL`, `solve_hover` | Historical software policy; proposed retention only, scientist approval pending |
| Moment arithmetic policy | max(10^-7 N m, 10^-8 F_* L_*) | N m | `trim.RESIDUAL_ABS_NM`, `solve_hover` | Historical software policy; proposed retention only |
| Sequence energy arithmetic policy | 10^-7 max(1 J, E_u) | J | `mission_capacity.solve_sequence` | Historical software policy; proposed retention only |
| Density match / inflow and pitch match | Relative 10^-9 / absolute 10^-9 in declared schema units | 1 / m/s and degree | `performance.RotorMapV1.evaluate` | Historical source-matching guard, not measurement uncertainty |
| Profile eligibility comparisons | rtol and atol 10^-10 for affine torque/constant torque; reject negative power or torque slopes strictly below 0; reject successive power-slope differences below -10^-10 | Declared curve units, scale dependent | `performance.RotorMapV1.convex_static_profile` | Historical arithmetic guard; scientific conditioning tolerance UNVERIFIED |
| Synthetic fixture coefficients | Q = 0.02 T; P_DC = 10 T | m; W/N | `tests/drone/test_hover_pilot.py`, artificial curve | Verified as declared fixture inputs only; no measured provenance |

Here F_* is max(1 N, m g_0, norm(F_b)); L_* is max(1 m, largest rotor-to-candidate-CG distance). Use componentwise maximum absolute residuals, matching existing checks. Hover limit checks also retain the existing 10^-7 W slack and exact declared RPM-domain check. These arithmetic guards do not absorb modeling or measurement error.

**Traceability gap:** relevant constants and numerical guards are distributed across modules and tests, with historical source shorthand and no single complete versioned, scientist-approved configuration ledger. This spec records that gap; it does not silently centralize constants, revise thresholds, infer source uncertainty or approve them. Viscosity, sound speed, ISA and CFD constants are outside the baseline equations here; their presence elsewhere is not qualification under this spec.

## 9. Valid operating range

The supported mathematical range is the intersection of the complete finite mass/position declarations, baseline zero-motion hover conditions, exact source condition matches, one full covered map interval, eligible torque/power shapes, continuous hardware/source duty, electrical limits and declared payload domain. Outside it, withhold the payload headline and report the concrete unsupported or unresolved reason. A map's presence or successful import does not establish its LP eligibility.

The scientifically trusted installed-aircraft range is **not established**. Existing synthetic fixtures demonstrate equations and refusal behavior only. Even a measured isolated-propeller table does not establish motor efficiency, pack endurance, installed interference, structural allowable payload or operational safety. D04-D06 client geometry/source, mass/electrical and mission/acceptance records remain required. No L5 cross-code or L6 installed-aircraft validation is claimed.

## 10. Validation cases (from VALIDATION.md)

All tolerances below are **proposed, needs scientist approval**. They are a prereview protocol, not completed ladder gates. Historical checks in `tests/drone/test_hover_pilot.py` and the local verification note supply candidate cases; their recorded passes do not by themselves satisfy this newly adopted acceptance protocol. A separate validation-engineer must freeze references, metrics, tolerances and expected results before any subsequent solver change. A fresh auditor must review acceptance evidence.

| Level | Case | Reference | Metric | Tolerance |
|---|---|---|---|---|
| L0 | Units, source matching, finite complete ledger, one efficiency application, supported case declarations and source/bound refusal | Existing schema/map/hover fixtures; SI conversions in section 8 | Incorrectly accepted invalid inputs and unsupported cases; nonfinite reported values | 0 false acceptances and 0 nonfinite accepted values; proposed, needs scientist approval |
| L1 | Six-component static wrench and constant-power energy ledger at one common payload; reserve held once, auxiliaries once | Independent evaluation of section 3, not LP epigraph values | max absolute force/moment components; absolute energy-ledger discrepancy and budget overshoot | Existing force/moment policies in section 8; energy <= 10^-7 max(1 J, E_u); proposed, needs scientist approval |
| L2 | Symmetric quad; pack/auxiliary limit; long-hover case; 360 s shared-pack sequence; displaced payload/body moments/tilted axes | Synthetic analytic fixtures below and independent derivations | Absolute payload, CG, force/moment and energy errors; outcome classification | Payload <= max(10^-7 kg, 10^-8 times absolute reference payload); CG <= 10^-8 m; section 8 residual/energy criteria; 0 incorrect classifications; proposed, needs scientist approval |
| L3 | Algebraic-model exception with exact segment subdivision (1, 2, 4, 8 equal subsegments), redundant collinear map knots, documented LP scaling | Exact invariance of the same equations and source function; no mesh/time solver | Change in common payload and energy, plus independent balance checks | Same L2 payload and L1 energy/residual criteria for every variant; 0 support/status changes; proposed substitute, needs scientist approval |
| L4 | Preregistered published isolated-propeller static holdout, source/conversion/interpolation pipeline only | Current corrected [UIUC Volume 1 online tables](https://m-selig.ae.illinois.edu/props/volume-1/propDB-volume-1.html); exact dataset not selected | Thrust/torque error vs RPM, absolute and normalized errors, coverage and standardized discrepancy for each omitted interior point | max absolute discrepancy / approved combined expanded comparison band <= 1.0, with 100% retained holdout coverage; bands, source and criterion approval pending; no pass if bands/metadata absent |

L2 fixture: four vertical rotors at (plus/minus 1, plus/minus 1, 0) m with balanced alternating rotation signs; empty mass 12 kg including a 2 kg pack; each map covers 0-1000 RPM and 0-100 N, with Q = 0.02 T and P_DC = 10 T. Pack specific energy 100 Wh/kg, usable fraction 0.8 and held reserve 0.2 give 460800 J. These are artificial inputs. The independent symmetric thrust-limit answer is:

\[
m_{p,T}=400/g_0-12\;\mathrm{kg}.
\]
Plain English: total rotor lift supports total mass, then subtract the declared empty aircraft mass.

For a 3000 W pack limit and 100 W auxiliaries, the answer is:

\[
m_{p,P}=290/g_0-12\;\mathrm{kg},\qquad
m_{p,E,300s}=\frac{460800/300-100}{10g_0}-12\;\mathrm{kg}.
\]
Plain English: first subtract auxiliary demand, convert the remaining power into thrust using the fixture curve, and subtract empty mass; the 300 s case also respects its available energy.

For 150 + 150 + 60 s segments with no auxiliaries, the answer is:

\[
m_{p,E,360s}=\frac{460800}{360\,10g_0}-12\;\mathrm{kg}.
\]
Plain English: all 360 seconds share the same reserved battery budget; checking each segment with a fresh battery would give the wrong result.

The proposed L2 payload/CG criteria target arithmetic agreement on small synthetic fixtures, using the order of existing 10^-7 absolute/10^-8 relative wrench guards as a starting rationale. They are new explicit comparison proposals, not historical customer accuracy or a statement that all old test assertions use these numbers. The L3 substitute checks implementation invariants only; it does not estimate unmodeled physical error or create a GCI.

**L4 protocol before looking at errors:** select and retain an exact source file URL, retrieval date, unmodified bytes, hash, revision, rights and run identifiers. Use the newest corrected online tables rather than older thesis tables. Preregister the retained/holdout row split by index (retain both RPM endpoints, withhold selected interior rows), operating conditions, comparison quantities, conversion, scales, near-zero handling and uncertainty/allowance derivation. Do not tune map points, efficiency, split or acceptance bands after observing discrepancies. At least two retained bracketing points and one interior holdout are required; report every withheld row, not only the best one.

[UIUC's Volume 1 documentation](https://m-selig.ae.illinois.edu/props/volume-1/propDB-volume-1.html) identifies static RPM sweeps and corrected online data; its power coefficients are derived from measured torque, so power and torque are not independent experimental validations. This is a proposed source, not retained L4 evidence. The [UIUC database entry point](https://m-selig.ae.illinois.edu/props/propDB.html) records the collection.

The combined expanded comparison band must be derived and approved before comparison from documented source uncertainty plus a separately justified interpolation allowance, with dependence treated explicitly. No numeric measurement uncertainty or physical percentage allowance is currently known, so L4 acceptance is blocked. Report raw percent errors where reference magnitude permits, but do not default to 5% or infer physical accuracy from the proposed normalized criterion.

Density and coefficient definitions/diameter are needed for any dimensional conversion; RPM, inflow, pitch/configuration and uncertainty metadata must be auditable. Never invent density from an unlabeled standard-atmosphere guess. UIUC shaft data alone do not supply electrical efficiency or continuous-duty qualification. Missing efficiency, duration or LP eligibility blocks promotion into a production payload map even if a standalone coefficient/interpolation comparison is possible. This limited L4 study can qualify only the source/interpolation pipeline. It cannot close installed-aircraft payload acceptance or confer L4 on all trim/mission physics; that scope needs an approved relevant published/system benchmark or an explicit scientist-approved exception and remaining evidence plan.

Each campaign must retain numeric errors, tolerances/approval IDs, all six balance residuals, energy discrepancy, source coverage, solver/certificate diagnostics, input/reference hashes and runtime versions. Required plots: model vs reference thrust/torque against RPM with holdouts marked; analytic vs calculated payload over duration/power; force/moment components against their arithmetic bounds; cumulative used and remaining mission energy. Axes carry SI units and distinguish synthetic from published measurements. No such new campaign or plots are claimed by this spec-writing task.

## 11. Questions for the scientist

1. **Yes/no:** approve A1-A9 and the restriction to baseline static-hover/fixed-pack claims, with installed-aircraft acceptance withheld?
2. **Pick one:** retain the proposed L0-L2 arithmetic criteria for this fixture campaign, or provide replacement quantity-specific criteria with rationale before tests are frozen?
3. **Yes/no:** approve the L3 algebraic applicability exception and invariance substitute in section 10, without a mesh GCI claim?
4. **Pick one:** approve a separately scoped UIUC holdout protocol after its source metadata and comparison bands are supplied, or require another published source? Neither choice approves aircraft payload accuracy.
5. **Pick one:** supply a named human reviewer/client engineering owner and approved real-aircraft acceptance quantities, or keep real-aircraft acceptance blocked while fixture preparation continues?

## 12. Scientist sign-off

Approved: no   Changes requested: Awaiting scientist review; no human physics approval recorded.

Reviewer: UNASSIGNED. Review date: not supplied. Customer accuracy: UNKNOWN. Approved physical tolerances: none supplied. Lead release acceptance: not recorded. Codex authored this specification only; it did not act as the scientist, validation-engineer, solver-builder or independent acceptance auditor for this specification.
