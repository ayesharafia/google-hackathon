# V140 private stable section implementation contract
Final private implementation candidate, pending independent owner review and acceptance.
Implementation authorization is not physical validation or numerical/resource qualification.
Only new pure modules/tests/docs; existing models remain exact bytes. No API/UI/rotor/fallback.
Residual identity: stable_section_residual_experimental / stable_section_residual_v1.
Solve identity: stable_section_solve_experimental / stable_section_solve_v1.
Exact root policy dictionary: {"id":"stable_deficit_binary64_v1","f_min":2**-20,"f_max":512}.
Policy native types are str, float, int respectively; reject alternate types, keys, values or policies.
Residual request exact keys: evaluation, numerical_policy, polar, section.
Section exact keys: imposed_axial_velocity_m_s, imposed_tangential_velocity_m_s, psi_rad,
tip_radius_m, chord_m, radius_m, density_kg_m3, dynamic_viscosity_pa_s,
speed_of_sound_m_s, pitch_rad, blade_count; same static positive branch as actual V134.
Polar and actual V133 child request/result remain the accepted V133/V132 contracts.
Solve request exact keys: evaluation, numerical_policy, residual_template, solve.
Template is exact residual request with psi_rad absent; both policies must equal the frozen policy.
Solve exact keys: psi_lower_rad, psi_upper_rad, angle_tolerance_rad,
residual_tolerance_m2_s, max_evaluations; positive normal int/float tolerances, int budget 2..32.
Responses carry evaluation, schema_version, numerical_policy, status, reasons, outputs, output_units,
diagnostics_complete, request_sha256, evaluation_sha256, limits, limitations, source_urls,
physical_validation, numerical_qualification, runtime_identity, aircraft_status, feasibility,
evidence_level, source_classification, mach_interval_status, plus accepted child counts.
Qualification/identity fields remain NOT_ESTABLISHED; aircraft_status/feasibility null.
Residual counts: load_result_count=lookup_result_count, exact int 0..1.
Residual outputs exact keys: kinematics, actual_load_request, actual_load_result, residual_state,
closure, factor_representation, residual_m2_s; actual child retained only after full V133 guard.
Closure exact keys: radius_ratio, tip_gap, local_wake_lambda, geometry_argument, geometry_factor,
circulation_scale_m, gamma_lift_m2_s, gamma_induced_m2_s; no legacy F/acos angle fields.
factor_representation exact keys: policy_id, f_domain_min, f_domain_max, f, exp_minus_f, deficit,
log_deficit, factor_rounded, representation_state, prefactor_m2_s, correction_m2_s,
correction_rounds_away, tip_rounding_effect_bound_m2_s.
Derived scalars are floats; policy endpoints retain frozen native types; labels str; diagnostic bool.
Velocity/wake/geometry operation order matches actual V134 with checked normal-or-zero arithmetic.
f=((float(B)*0.5)*(1-r/R))/((r/R)*(Wa/Wt)); accepted computed domain [2**-20,512].
Outside domain: NUMERICAL_POLICY_REFUSED / F_OUTSIDE_NUMERICAL_POLICY, zero calls/counts/payload.
x=exp(-f); deficit=(2/pi)*asin(x); log_deficit=log(deficit); factor_rounded=1-deficit.
x, deficit, K, correction, gamma must be positive NORMAL; 0<x,deficit<1; 0<factor_rounded<=1.
K=((vt*((4*pi*r)/B))*geometry); correction=K*deficit; gamma=fsum([K,-correction]).
gamma_lift=((0.5*actual_V133_speed)*chord)*actual_V133_Cl; residual=fsum([gamma,-gamma_lift]).
State ROUNDED_ONE_WITH_POSITIVE_DEFICIT iff factor_rounded==1, else INTERIOR_SCALAR.
correction_rounds_away iff emitted gamma==emitted K with positive retained correction; no history proof.
Bound fixes emitted K,f as exact reals: K*2**(-floor(f)) for f>=1, else K; nextafter(product,+inf).
Overflow refuses; ONLY tip_rounding_effect_bound_m2_s permits positive finite SUBNORMAL.
Separate bound guard/unit-schema exception permits product underflow followed by outward nextafter(0,+inf).
This bound covers replacing the exact real factor by one at fixed emitted K,f, not libm/geometry/error/CI.
Units: velocities m/s, angles rad, lengths m, gamma/residual/prefactor/correction/bound m^2/s;
dimensionless geometry/f/exp/deficit/log/factor/domain values 1; policy/state label; rounds-away boolean.
OOD: COMPUTED_EXPERIMENTAL, NOT_RUN_OUT_OF_POLAR_DOMAIN, closure/factor/residual null and units not_applicable.
Invalid/unsupported: MODEL_INAPPLICABLE/INVALID_REQUEST or SOLVER_UNSUPPORTED/UNSUPPORTED_EVALUATION;
zero counts, empty outputs/units, null hashes. Arithmetic/export: EXECUTION_FAILED, sanitized reason.
Residual LOAD_BOUNDARY_FAILED has count0; post-child arithmetic/export failure count1, empty payload.
Solve independently reconstructs velocity/closure/factor from guarded actual V133; no new producer math oracle.
Solve counts residual_result_count=load_result_count=lookup_result_count=number of fully guarded rows 0..32.
Solve outputs exact keys: evaluations, solve_state, final_bracket, solution; rows ordered unique actual calls.
Row exact keys: psi_rad (native endpoint or float midpoint), request_sha256, result (full guarded residual).
Bracket: lower_evaluation_index, upper_evaluation_index (int), angle_width_rad (float); solution:
evaluation_index (int), psi_rad, residual_m2_s; absent bracket/solution null, matching not_applicable units.
Deterministic endpoints then bisection; BOTH width and residual criteria; zero collapses; no retries/extrapolation.
States: CONVERGED, NOT_BRACKETED, NOT_RUN_OUT_OF_POLAR_DOMAIN, EVALUATION_BUDGET_EXHAUSTED, FLOAT_STAGNATION.
Solve boundary/arithmetic failure retains only prior guarded rows, state EXECUTION_FAILED, null bracket/solution;
bad child is never counted/retained; persistent export/hash failure clears payload/hashes but keeps valid count.
Native JSON limits nodes/depth: residual input32768/16 output131072/28; solve input65536/18 output4194304/36.
All containers<=256, strings<=2000 Unicode chars strict UTF8, ints<=1023bits; bound before copy/hash/calls.
Streaming compact UTF8 serialized byte caps: residual input1MiB/output4MiB; solve input2MiB/output128MiB.
Max32 nested actual results; actual maximum-budget probe and resource proof required before candidate acceptance.
SHA256 domains: sorted compact UTF8 ensure_ascii=False allow_nan=False full native validated request including policy;
full response excluding only evaluation_sha256, including policy/units/counts/nulls; no authenticity claim.
Ordinary Exception sanitized; BaseException propagates; catalog is fresh metadata with policy, limits and units.
Reference80/120-digit comparisons and historical16-budget outcomes are numerical evidence, not physical qualification.

Final verification:123 new tests and252 unchanged legacy V133/V134/V135 tests passed together
(375 passed in8.39s). New coverage includes exact policy/native types and hashes; all factor fields,
units, metadata, kinematics and V133 child tampering with resealed hashes; producer-oracle independence;
32 actual guarded calls; BOTH convergence criteria; OOD; actual NOT_BRACKETED; atomic prior traces;
native node/depth/container/string/integer/UTF8/circular/serialized-byte refusals before untrusted
request copy/hash/model calls; output-bound and persistent-hash failures; ordinary Exception
sanitization and BaseException propagation. Trusted refusal-metadata copies still occur after rejection.
Zero collapse and float stagnation have explicitly synthetic unit-bisection coverage, not actual
integrated-child proof. Input/output units and null states are checked; this is not exhaustive schema fuzzing.
Measured baseline and maximum admitted 8-table/256-row probes each retained32 actual guarded results;
see stable-section-resource-audit.md and both JSON reports. Resource caps remain proposed, with
numeric-payload and worst-case allocation qualification outstanding. No extra full resource run was needed.
The375-test run verifies the existing pure section suites; no separate historical benchmark replay is claimed.
No automatic rotor/API/UI integration, fallback, physical validation, publication or external sending.
