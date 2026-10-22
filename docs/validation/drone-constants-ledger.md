# Drone constants and numerical safeguards

Internal source review, 22 October 2026. Baseline: `5477f94a0c467f1a01e9691a1f9c53613eeffa67`.
Task: SLICE-001. Reviewer: Codex, primary agent; no independent or qualified
scientific approval. Source values and tolerances are unchanged.

This ledger makes the assumptions behind a payload result inspectable. It
covers all five named modules, including atmosphere helpers that are not used
by the restricted payload calculation. It does not establish aircraft accuracy.

## How to read it

- **PHYSICAL / UNVERIFIED:** a physical model parameter whose exact primary
  provenance, applicable range or project approval is incomplete.
- **DEFINITION:** a unit conversion, geometric identity or explicit convention;
  it is not a measured aircraft property.
- **POLICY:** an existing numerical or eligibility choice. Observed code and
  design rationale do not establish an engineering error allowance.
- **INPUT:** a supplied dataset/configuration value; this ledger records where
  it is used, not that its source or approval is authenticated.
- **STRUCTURE:** dimensions, indices and bookkeeping, excluded from the physical
  parameter list but included in the numeric-literal inventory.

Line links below refer to this baseline. Each row ID also maps the numeric
occurrences in the [source inventory](../../.physicore/evidence/SLICE-001-inventory.json).
That inventory retains file hashes and excluded literals. Coverage means every
numeric occurrence has a disposition and the nonnumeric guards were read;
it does not mean all physics has been verified.

## Atmosphere

Source: [atmosphere.py](../../src/physimesh/drone/atmosphere.py).
The local trim path uses `R_AIR` and `G0`; it derives density from supplied
absolute pressure and temperature. ISA, viscosity, sound-speed and Mach helpers
have separate scope and do not add aircraft evidence to a payload result.

| ID | Value or guard and location | Units | Classification, source and limitation |
|---|---|---|---|
| A01 | [R_AIR = 287.05, line 9](../../src/physimesh/drone/atmosphere.py#L9) | J/(kg K) | PHYSICAL / UNVERIFIED primary derivation and composition/range. Explicitly prescribed by historical [manifest section 4](../source/manifest_v1.0_extracted.md); not a universal gas constant or a humidity model. |
| A02 | [G0 = 9.80665, line 10](../../src/physimesh/drone/atmosphere.py#L10) | m/s² | DEFINITION of conventional standard gravity; [DR-01 section 8](../../specs/drone-hover-payload-baseline.md) retains a NIST reference. Use as actual site gravity remains UNVERIFIED and unapproved. This review did not recheck that reference. |
| A03 | [ISA_T0 = 288.15, ISA_P0 = 101325, ISA_LAPSE = 0.0065, ISA_TROPOPAUSE_M = 11000, lines 11-14](../../src/physimesh/drone/atmosphere.py#L11) | K; Pa; K/m; m | PHYSICAL reference-atmosphere parameters / UNVERIFIED exact primary derivation in this review. Code only labels STD. A primary NOAA standard was located but full text could not be fetched; do not mark it checked. A reference atmosphere is not a weather observation. |
| A04 | [mu_ref = 1.716e-5, t_ref = 273.15, s = 110.4, lines 17-20](../../src/physimesh/drone/atmosphere.py#L17) | Pa s; K; K | PHYSICAL / UNVERIFIED provenance of this exact Sutherland triplet. [COMSOL table 5-2](https://doc.comsol.com/6.4/doc/com.comsol.help.cfd/cfd_ug_fluidflow_high_mach.08.46.html) lists air as 1.716e-5, 273 K, 111 K, so it does not verify the full code triplet. No replacement or equivalence is inferred. |
| A05 | [Exponent 1.5 in viscosity law, line 20](../../src/physimesh/drone/atmosphere.py#L20) | 1 | PHYSICAL model form, not a fitted value in this file. Code uses mu_ref*(T/t_ref)^1.5*(t_ref+s)/(T+s). The direct helper has no finite/positive argument guard; make_atmosphere checks its returned viscosity. Supported temperature/pressure range for the exact triplet remains UNVERIFIED. |
| A06 | [gamma default 1.4, line 50](../../src/physimesh/drone/atmosphere.py#L50) | 1 | PHYSICAL / UNVERIFIED primary provenance and applicability. Historical manifest permits an ideal dry-air approximation only when appropriate; code does not model humidity or temperature-dependent gamma. |
| A07 | [make_atmosphere, lines 52-68](../../src/physimesh/drone/atmosphere.py#L52) | Pa; K; Pa s; 1 | POLICY: supplied p, T, gamma finite and >0; exactly one viscosity value/law; only named sutherland law accepted; returned mu finite and >0. These mathematical input domains do not prove the model valid at every positive value. |
| A08 | [ISA altitude 0 <= altitude <= 11000, lines 71-80](../../src/physimesh/drone/atmosphere.py#L71) | m | POLICY / MODEL DOMAIN: only one lapse-rate layer; p = P0*(T/T0)^(G0/(L*R)). Geometric versus geopotential altitude convention is not explicit in the API. Exact ISA-table equivalence is UNVERIFIED; docstring notes rounded R. |
| A09 | [pressure consistency, lines 83-91](../../src/physimesh/drone/atmosphere.py#L83) | Pa; 1 | INPUT rel_tol, no default: finite >=0, finite p>0; discrepancy <=rel_tol*p_ISA. It is a caller choice, not an atmospheric uncertainty measurement. |
| A10 | [density/sound speed/viscosity and Re/Mach, lines 35-46, 94-107](../../src/physimesh/drone/atmosphere.py#L35) | kg/m³; m/s; m²/s; 1 | MODEL identities as documented in historical M-E03/M-E04: rho=p/(RT), a=sqrt(gamma RT), nu=mu/rho, Re=rho*V*c/mu, M=V/a. Tip speed combines orthogonal rotation/axial terms with exponent 2. Axial screening only, not forward-flight blade velocities. These helpers do not independently validate supplied lengths/speeds. |

## Retained rotor maps

Source: [performance.py](../../src/physimesh/drone/performance.py).
Design rationale: [ADR-0003](../decisions/ADR-0003-static-hover-profile.md).

| ID | Value or guard and location | Units | Classification, source and limitation |
|---|---|---|---|
| P01 | [positive/nonnegative types and efficiency, lines 13-40](../../src/physimesh/drone/performance.py#L13) | Native field units; efficiency 1 | POLICY / INPUT: rpm, thrust N, absorbed torque N m, power W >=0; density and continuous duration >0; declared efficiency 0<eta<=1. Physical efficiency and duty must come from sources. Shaft maps require a nonblank efficiency source; electrical maps forbid applying efficiency again. |
| P02 | [description length 1-2000, intervals 1-32, samples 2-64, lines 29-40](../../src/physimesh/drone/performance.py#L29) | Characters; counts | POLICY: schema/resource bounds, not physical operating limits. Primary engineering rationale for these counts is UNVERIFIED; two samples are the interpolation minimum here. |
| P03 | [Q*RPM*2*pi/60, lines 53, 88](../../src/physimesh/drone/performance.py#L53) | W | DEFINITION of rad/s conversion and shaft mechanical power. 60 s/min is exact; pi is the library's floating approximation. [DR-01 section 8](../../specs/drone-hover-payload-baseline.md) retains the NIST conversion reference. |
| P04 | [power consistency, lines 54-57, 91-92](../../src/physimesh/drone/performance.py#L54) | W; relative 1 | POLICY: electrical watts +1e-9*max(1 W, absorbed shaft W) must not be smaller than shaft demand. Shaft sample isclose uses rel_tol=1e-9 and abs_tol=1e-9 W. Historical arithmetic guard; justification of these magnitudes is UNVERIFIED, not efficiency or measurement error. |
| P05 | [coverage and queries, lines 44-80](../../src/physimesh/drone/performance.py#L44) | RPM; kg/m³; m/s; degrees | POLICY: RPM samples strictly increasing; intervals inside samples, endpoints retained, low<high, no overlapping intervals. Finite numeric queries; covered RPM only. Density match rel_tol=1e-9, abs_tol=0 kg/m³; inflow and pitch rel_tol=0, abs_tol=1e-9 m/s and degrees. Source-match precision, not physical uncertainty. |
| P06 | [profile eligibility, lines 98-120](../../src/physimesh/drone/performance.py#L98) | N; N m; W; W/N; m | POLICY / MODEL DOMAIN: one full covered interval, strictly increasing thrust, nonnegative power slopes, successive power-slope differences >=-1e-10 W/N. Constant shaft torque and affine torque use np.allclose rtol=1e-10, atol=1e-10 N m. Torque slope >=0; its unit is N m/N = m. ADR-0003 explains LP eligibility, not the numeric tolerance selection. Magnitude rationale UNVERIFIED; no noise or conditioning allowance implied. |
| P07 | [interpolation and coefficient construction, lines 83-124](../../src/physimesh/drone/performance.py#L83) | N; N m; W; RPM; m; W/N | INPUT / MODEL: np.interp within coverage; derive slopes/offsets from retained points. Shaft power recomputed Q*omega and eta used once. No imported map is a universal constant. Dataset hash, configuration, conditions, duty and uncertainty evidence are external to these values. |

`1e-10 W/N` on differences of slopes and `1e-10 N m` on torque are
different dimensional policies even though the source literal is the same.
Neither establishes a relative percentage error on aircraft payload.

## Static/axial trim

Source: [trim.py](../../src/physimesh/drone/trim.py).
The v1 and v2 model tags are eligibility/version contracts, not accuracy levels.
See [ADR-0003](../decisions/ADR-0003-static-hover-profile.md),
[ADR-0005](../decisions/ADR-0005-conditioned-axial-profile.md) and the
[pending DR-01 baseline spec](../../specs/drone-hover-payload-baseline.md).

| ID | Value or guard and location | Units | Classification, source and limitation |
|---|---|---|---|
| T01 | [RESIDUAL_REL=1e-8, ABS_N=1e-7, ABS_NM=1e-7, lines 21-23](../../src/physimesh/drone/trim.py#L21) | 1; N; N m | POLICY. Componentwise recomputed wrench thresholds. DR-01 proposes retaining historical arithmetic policy; qualified acceptance and numerical magnitude rationale remain UNVERIFIED. |
| T02 | [number/vector, lines 26-38](../../src/physimesh/drone/trim.py#L26) | Input field units | POLICY: finite nonboolean numbers; scalar nonnegative or explicitly positive; vectors exactly three finite components. Vector entries need not be positive. Three components are STRUCTURE, not a physical coefficient. |
| T03 | [model/case/frame eligibility, lines 69-113](../../src/physimesh/drone/trim.py#L69) | Degrees; m/s; m/s²; rad/s; rad/s² | POLICY / DEFINITION: supported version, no undeclared extended settings, no unsupported case keys/clearance/mass_state, z-up frames, exactly zero attitude/accelerations/angular rates. Hover velocity/inflow exactly zero; v2 climb world velocity (0,0,V), relative air (0,0,-V), explicit V>0. Source/load notes and fixture/client_unvalidated scope required. Exact comparisons define coverage, not a tolerance for maneuvers. |
| T04 | [payload bounds/position and pack, lines 114-141](../../src/physimesh/drone/trim.py#L114) | kg; m; V; A; W; s; Pa; K | INPUT / POLICY: finite ordered nonnegative payload bounds, exactly one position, complete candidate mass at zero replacement payload, consistent fixed pack and constant bus. Pack limit=min(declared W,V*declared A); positive duration/p/T; source required. Density uses A01. Pack usable energy comes from screening_scope.pack_consistency, not a constant here. |
| T05 | [rotor count/identity, lines 143-155](../../src/physimesh/drone/trim.py#L143) | Count; identifier | POLICY: 1-16 rotors, unique IDs matching regex (1-80 characters), failed IDs unique subset, overrides subset of declared IDs. Resource/schema bounds, not proof of supported real rotor layouts. |
| T06 | [axis and rotation, lines 158-165](../../src/physimesh/drone/trim.py#L158) | 1 | POLICY / DEFINITION: axis norm isclose(1, rel_tol=0, abs_tol=1e-9); integer sign exactly -1 or +1. Climb axes exactly (0,0,1). Opposite sign gives airframe reaction. Norm tolerance magnitude is UNVERIFIED numerical policy; signs/axes are declared conventions. |
| T07 | [failed rotors, lines 169-174, 335-338](../../src/physimesh/drone/trim.py#L169) | N; N m; W; RPM | MODEL: failed command, power and thrust bounds exactly zero. Internal [0,1] thrust/RPM arrays form a dummy interpolation profile; 1 is not an allowed failed-rotor command. Hardware mass remains external mass-ledger input. No drag, autorotation or transient failure model is inferred. |
| T08 | [source/duty/limits, lines 166-193](../../src/physimesh/drone/trim.py#L166) | RPM; W; A; s; N | INPUT / POLICY: matching retained configuration; conditioned map only in v2; source-query conditions must match; duration<=map duty; maximum RPM=min(declared max,map endpoint), not below retained minimum; rotor power limit=min(declared W,V*A). Thrust bounds evaluated from map. No extrapolation or implicit duty margin. |
| T09 | [torque uncertainty, lines 195-204, 349-355](../../src/physimesh/drone/trim.py#L195) | N m | INPUT / POLICY: sum abs(axis)*rotor torque error bound per component, default error bound 0 when absent; if any band positive require finite sourced nonnegative allowances. Preliminary band<=allowance+1e-10 N m. ADR-0005 explains interval rule, not slack magnitude. Absent bound is not zero physical uncertainty. |
| T10 | [constraint construction, lines 212-239](../../src/physimesh/drone/trim.py#L212) | N; N m; W; kg | MODEL / DEFINITION: 3 force+3 moment equalities; thrust/power epigraph variables and payload; gravity (0,0,-G0); opposite reaction sign. Convex affine power segment inequalities; sum rotor W<=pack W-aux and <=usable J/duration-aux. Power epigraph lower bound 0 W; payload fixed to candidate when requested. Coefficients 0/1/-1 are algebra, not fitted constants. |
| T11 | [bound origins and source gaps, lines 242-296](../../src/physimesh/drone/trim.py#L242) | N; kg; RPM; scaled rows | POLICY: zero lower bound classified physical; nonzero retained lower bounds coverage; payload upper analyst domain; source coverage gaps or conditioned surrogate force unsupported rather than physical-infeasible. Fixed candidate distinct from analyst domain. Positive multiplier / residual-contribution checks use exact >0 and stored rounding_guard; no extra hidden epsilon here. |
| T12 | [certificate scaling/solve, lines 299-325](../../src/physimesh/drone/trim.py#L299) | Scaled numeric rows; s; iterations | POLICY: each row divided by max(1, max abs coefficients, abs RHS), nonnegative multiplier solve with combined RHS -1, HiGHS time_limit=1 s, maxiter=10000; clamp candidate multipliers to >=0 then independently recompute contradiction gap over finite bounds. This scales mixed native-unit numbers, not a dimensionally normalized physical residual or uncertainty. |
| T13 | [certificate rounding_guard, lines 316-325](../../src/physimesh/drone/trim.py#L316) | Scaled contradiction quantity | POLICY: 1e-7*max(1, sum abs(multiplier*b), abs(minimum)); finite gap must be strictly greater. Magnitude rationale UNVERIFIED; not newtons, joules or measurement uncertainty. Source/domain classification T11 still required. |
| T14 | [recompute, lines 328-356](../../src/physimesh/drone/trim.py#L328) | kg; m; N; N m; W; A; J | MODEL / INPUT: candidate mass/CG, independently reevaluate map thrust/torque/watts, moments about CG, current=P/V, E=P*duration; initialize rotor sum with declared auxiliary watts once. Imported map bounds and A01/A02 apply. This is recomputation by code, not an independent reviewer. |
| T15 | [hover solve and bounds, lines 359-391](../../src/physimesh/drone/trim.py#L359) | kg; N; W; s; iterations | POLICY: candidate within declared payload domain; maximize payload (objective -1) or minimize total rotor power (coefficients +1) at fixed payload; HiGHS 1 s/10000 iterations. Status 2 only triggers certificate attempt; other failures unresolved. Nonfinite/out-of-bounds commands rejected with exact comparisons, no clamping. |
| T16 | [residual scales, lines 392-405](../../src/physimesh/drone/trim.py#L392) | N; m; N m | POLICY: F*=max(1 N,m*G0,norm(body force)); L*=max(1 m,largest rotor-CG distance). Force tol=max(1e-7 N,1e-8*F*), moment tol=max(1e-7 N m,1e-8*F*L*); each component must pass. Torque interval edges must fit sourced allowance+moment_tol. Scale floors are historical numeric policy, not measured geometry or forces. |
| T17 | [power/RPM recheck, lines 407-413](../../src/physimesh/drone/trim.py#L407) | W; RPM | POLICY: recomputed pack/energy-equivalent power and each rotor power <=limit+1e-7 W; RPM<=declared maximum exactly. Absolute slack magnitude UNVERIFIED as a scientific criterion. |
| T18 | [active constraints, lines 417-430](../../src/physimesh/drone/trim.py#L417) | W; J; kg; N | POLICY, display classification: strict abs difference <1e-6 W for pack/rotor power, <1e-4 J for case energy, <1e-6 kg for upper payload, <1e-6 N for upper thrust. These label near-binding constraints; they are not the feasibility tolerances. Magnitude rationale UNVERIFIED. |

HiGHS is a numerical method choice. Its [official interface documentation](https://docs.scipy.org/doc/scipy/reference/optimize.linprog-highs.html)
defines time_limit in seconds, maxiter as an iteration bound, and status 2 as an
infeasibility report. The repository adds the certificate/recompute checks.
Solver defaults not explicitly supplied here remain library-version dependent;
this review does not certify them or the selected algorithm's physical validity.

## Case aggregation

Source: [capacity.py](../../src/physimesh/drone/capacity.py).

| ID | Value or guard and location | Units | Classification, source and limitation |
|---|---|---|---|
| C01 | [eligibility, lines 21-58, 69-85](../../src/physimesh/drone/capacity.py#L21) | Counts; identifiers | POLICY: 1-8 explicit cases, unique regex IDs of 1-80 characters, boolean required flag (default True), at least one required case. Optional failure does not erase a required case; sequence references get eligibility checks too. Numeric counts are software bounds, not uncertainty samples. |
| C02 | [aggregation and common candidate, lines 86-164](../../src/physimesh/drone/capacity.py#L86) | kg; J | MODEL / POLICY: required failure withholds headline; min individual payload is re-solved at a common candidate. With sequence, energy binding uses abs(remaining J)<=retained energy_tolerance_j (S05). Joint payload may not exceed independently attained case bound by >1e-7 kg; if energy does not bind it must agree within 1e-7 kg. Numerical agreement policy, magnitude rationale UNVERIFIED. Minimum of separate case maxima alone does not prove common feasibility. |
| C03 | [model/scenario delegation and qualifications, lines 61-66, 97-114](../../src/physimesh/drone/capacity.py#L61) | Contract labels | POLICY: v1/v2 versions route behavior; v2 scenario/cap equations live in scenarios.py and conditioning.py, outside this five-module inventory. Engineering status remains pending, synthetic source kind retained. No new scenario/physical accuracy claim. |

## Chronological fixed-pack mission

Source: [mission_capacity.py](../../src/physimesh/drone/mission_capacity.py).
Energy-accounting rationale is in [local hover/energy](local-hover-and-energy.md).

| ID | Value or guard and location | Units | Classification, source and limitation |
|---|---|---|---|
| S01 | [case selection and sequence eligibility, lines 24-76](../../src/physimesh/drone/mission_capacity.py#L24) | s; counts | INPUT / POLICY: 1-32 ordered segments; exact segment fields, nonblank unique IDs, eligible case, constant power profile and source note; positive segment duration<=case duration. Optional case uses max referenced segment duration for preparation. Total sequence duration<=every active participating source duty; failed rotor duty skipped, no cooling reset. No invented duty default. |
| S02 | [joint constraints, lines 79-104](../../src/physimesh/drone/mission_capacity.py#L79) | W s=J; kg | MODEL: share one payload across per-case allocations, intersect declared payload domains; refuse empty intersection. Sum duration*electrical epigraph plus auxiliary J within min(case usable J). Auxiliary starts at 0 J and is counted for each segment once; local case energy constraints remain. No timestep, quadrature tolerance or battery dynamics here. |
| S03 | [joint solver, lines 107-124](../../src/physimesh/drone/mission_capacity.py#L107) | s; iterations | POLICY: maximize shared payload (-1 objective), HiGHS 2 s/10000 iterations. Status 2 attempts T12/T13 certificate with physical/analyst bound origins; gaps force unsupported. Zero lower payload classification follows T11. Computational budget is not physical convergence. |
| S04 | [candidate checks and integration, lines 125-139](../../src/physimesh/drone/mission_capacity.py#L125) | kg; W; s; J | POLICY / MODEL: finite commands within exact bounds; independently solve each case at common payload; E_segment=P_case*duration, cumulative consumed starts at 0 J, remaining=usable-consumed. Constant-power integration only. This does not simulate SOC, sag, thermal behavior, recharge or control transients. |
| S05 | [energy_tolerance, lines 140-149](../../src/physimesh/drone/mission_capacity.py#L140) | J | POLICY: 1e-7*max(1 J,usable J); consumed<=usable+tolerance. Same retained tolerance is used by C02 for binding status. Source of magnitude is historical software policy, not battery energy uncertainty; approval remains UNVERIFIED. Reserve already held in supplied usable J and is not applied again. |

## Exclusions and evidence limits

Every numeric AST literal in these five files is retained in the inventory,
including duplicate occurrences. Unlisted source indices/slices (0, 1, -1),
three-vector/six-wrench dimensions, `2*n+1` variable layout, empty-sum zeros and
matrix coefficients are **STRUCTURE**, not additional empirical constants.
Negative numbers are represented by an AST unary sign plus literal; the evidence
keeps the signed source text as well. Identifier regex limits occur inside
strings, so T05/C01 document them manually. Model/schema strings, booleans and
None are not numeric constants; their eligibility effect is recorded above.

There are no retained-data numeric coefficients embedded in these five modules
beyond the values listed here. Rotor curves, efficiency, pitch/inflow, masses,
CG, body loads, pack fractions/energy, continuous limits, declared allowances
and uncertainty policies are supplied or imported. Their absence from the
literal list does not verify them. Imported pack, conditioning, scenario,
mass and frame implementations require a separate scoped inventory. In
particular, Wh-to-J conversion and held-reserve derivation are outside these
five modules; no full dependency-closure coverage is claimed.

Read [test_hover_pilot.py](../../tests/drone/test_hover_pilot.py) and located
atmosphere helper coverage in [test_wp02_foundations.py](../../tests/drone/test_wp02_foundations.py).
They are software
fixtures, not parameter provenance. No tests, solver studies or experiments were
executed for this documentation task. The bounded checks cover source hashes,
numeric-occurrence dispositions, local links and unchanged source only.

## Evidence gaps and next work

1. Exact primary provenance and applicable ranges remain missing for R_AIR,
   gamma, the full Sutherland triplet and ISA altitude interpretation. The
   [NOAA standard-atmosphere PDF](https://www.ngdc.noaa.gov/stp/space-weather/online-publications/miscellaneous/us-standard-atmosphere-1976/us-standard-atmosphere_st76-1562_noaa.pdf)
   fetch failed because of size; this is a research lead, not verified content.
2. Historical numeric tolerances have code provenance, not approved physical
   error budgets. Keep [SCI002/SCI003 pending](../../.physicore/ops/APPROVALS.md).
   Do not fold rounding slack into measurement or installation uncertainty.
3. Measured maps, installed aircraft comparison, intended-use accuracy and a
   qualified reviewer remain missing. A finite residual does not close them.
4. Next safe documentation slice: extend traceability to imported pack energy,
   mass/frames, conditioning and scenario inputs before proposing any equation
   or parameter change. Scientific promotion remains a separate decision.

External lookup date: 22 October 2026. COMSOL and SciPy are primary vendor
documentation used only for the narrow comparisons stated above. The unresolved
sources remain unresolved; this report does not claim independent validation.
