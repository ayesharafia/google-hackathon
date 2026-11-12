# V141 frozen private stable rotor authoring contract

Base: accepted V140. Authoring admitted; candidate code/science/resource acceptance is pending.
Only new files. No API, UI, legacy rotor change, fallback, publication or benchmark execution.
Identity: stable_polar_rotor_experimental / stable_polar_rotor_v1; new stable_polar_rotor.py.
Exact request keys: evaluation, numerical_policy, rotor, annuli.
Exact policy: {"id":"stable_deficit_binary64_v1","f_min":2**-20,"f_max":512}; str/float/int types.
Exact rotor keys: tip_radius_m, hub_radius_m, blade_count, angular_speed_rad_s,
imposed_axial_velocity_m_s, density_kg_m3, dynamic_viscosity_pa_s, speed_of_sound_m_s,
geometry_source, uncertainty_status. Same positive geometry/properties/branch and source rules as V136.
Exact annulus keys: radial_inner_m, radial_outer_m, chord_m, pitch_rad, polar, solve.
Exact solve keys: psi_lower_rad, psi_upper_rad, angle_tolerance_rad, residual_tolerance_m2_s,
max_evaluations. Budget is explicit builtin int2..32; 1..8 annuli; sum requested budgets<=256.
Native exact contiguous boundaries cover positive hub to tip. dr=fsum(outer,-inner),
r=fsum(inner,.5*dr) strict interior; Ut=Omega*r; unchanged caller polars and signed midpoint physics.
Actual child identity stable_section_solve_experimental / stable_section_solve_v1, with exact policy
in both root and stable residual template; no selectable/omitted/legacy child identity or policy.
All full derived requests and both endpoints statically checked before any child call.

Response top fields: evaluation, schema_version, numerical_policy, status, reasons, outputs,
output_units, diagnostics_complete, section_solve_result_count, residual_result_count,
load_result_count, lookup_result_count, physical_validation, numerical_qualification,
runtime_identity, aircraft_status, feasibility, evidence_level, source_classification,
mach_interval_status, limitations, limits, source_urls, request_sha256, evaluation_sha256.
Qualification/runtime fields NOT_ESTABLISHED, aircraft_status/feasibility null; source assertions unverified.
Successful outputs exact keys: rotor_state, annuli, integrated. Annulus row exact keys:
annulus_index, radial_inner_m, radial_outer_m, midpoint_radius_m, radial_width_m,
actual_solve_request, actual_solve_result, contribution.
Each contribution is null or {thrust_n, torque_nm}; integrated is null or
{total_thrust_n, total_torque_nm, shaft_power_w}. Ordered signed contributions use actual selected
all-blade V133 densities times dr; totals use fsum; shaft_power_w=Omega*total_torque_nm.
Only integrate if EVERY admitted solve is CONVERGED. Otherwise rotor_state
NOT_RUN_SECTION_NOT_CONVERGED, integrated/contributions null; retain diagnostic rows and matching null units.
Converged rotor_state COMPUTED. Angles rad, lengths m, velocities m/s, torque N*m, thrust N,
shaft power W, policy/labels text, counts/indexes dimensionless; full actual nested child units retained.
No child is redundantly embedded in secondary diagnostics. Actual requests retain their polar data separately.

Independent trace engine replays actual ordered rows over accepted V140 _guard_residual only.
No child evaluator, _bisect, producer closure/representation or solve evaluator is a guard oracle.
Freeze exact solve catalog, native shape/types/policy/metadata/units/counts and full hash domains.
Reconstruct endpoints, checked midpoints, sign updates, best endpoint/ties, BOTH tolerances,
zero-collapse, budget, stagnation and OOD semantics; reject missing/reordered/duplicate/extra/truncated rows.
Only whole fully guarded computed solves count, including nonconverged/OOD. No partial-row counts.

Root native ceilings: input262144 nodes/depth18/8MiB; output16777216 nodes/depth40/128MiB.
Actual V140 solve output ceilings:4194304 nodes/depth36/128MiB, not legacy V136 child bounds.
All nodes include keys, each measured whole object starts at root depth1. Container<=256,
string<=2000 strict UTF8 chars, integer<=1023 bits, exact builtins and finite floats only.
Only nested tip_rounding_effect_bound_m2_s allows positive finite subnormal after its actual V140 guard;
all other scalar rules remain normal-or-zero. Native resource walking alone does not qualify scalar math.
Canonical encoder: sorted compact JSON, ensure_ascii=False, allow_nan=False, strict UTF8.
Retained-child quota is the SUM of canonical WHOLE child objects, including units/metadata/hashes:
<=67108864 bytes and<=8388608 nodes. These counters exclude wrappers, requests and parent units.
Stream-measure CURRENT RAW child against BOTH intrinsic limits and remaining quota BEFORE any parent
deepcopy, hash or independent guard. iterencode counting must not construct a whole serialized string.
The actual child evaluator has ALREADY allocated/hashed its result; this cannot prevent upstream allocation.
Intrinsic violation => SOLVE_BOUNDARY_FAILED; remaining-quota crossing => distinct resource exception.
If either ceiling is crossed, stop at that observation; no further parent copy/hash/guard of that child.
For admitted size: snapshot, remeasure with same limits/quota, exact native compare and matching metrics,
THEN independent guard, THEN commit quota and whole-child counts. No count until all admission steps pass.
Counts: section_solve_result_count int0..8; residual/load/lookup equal sum of whole admitted solves int0..256.

Invalid/unsupported => MODEL_INAPPLICABLE/INVALID_REQUEST or SOLVER_UNSUPPORTED/UNSUPPORTED_EVALUATION;
zero calls/counts, empty outputs/units, null hashes. Guard failure => EXECUTION_FAILED/SOLVE_BOUNDARY_FAILED.
Quota => EXECUTION_FAILED/RESOURCE_BUDGET_EXCEEDED, atomic empty outputs/units, prior whole counts only.
Arithmetic/export => EXECUTION_FAILED/STABLE_POLAR_ROTOR_EXECUTION_FAILED with prior counts, empty payload.
Ordinary Exception sanitized, BaseException propagates. No partial totals/traces, truncation, retry or fallback.
Normal failure hash binds validated native request and full sanitized receipt, including prior counts/policy.
Persistent export/hash failure clears outputs/units/both hashes and preserves prior accepted counts.
Request SHA256: full native request including policy/geometry/polars/budgets; response SHA256:
full bounded response excluding ONLY evaluation_sha256; sorted compact UTF8; data binding, not authenticity.
Bound full export before hashing and again after sealing; parent128MiB ceiling is separate from child quota.

Required later evidence: actual8*32=256 calls with small polar and full replay; configured maximum-shape
quota crossing under timer/RAM cap; independent native/quota/trace tamper tests; conservative wrapper,
request-copy and units headroom accounting. If children are about8567421 bytes, the eighth crosses64MiB:
measure actual attempts/accepted counts (potentially8/256 attempted versus7/224 accepted), do not assume.
Do not weaken quotas on abort. Serialized caps are not RAM/API/concurrency/time proofs.
Maximum Cartesian row work256*8*256=524288 does not override any child limit.
Geometry-only f_target256 historical benchmark amendment remains forbidden until separate code acceptance.

## Final private candidate evidence; independent review still pending

The public evaluator, independent trace engine, native/quota admission, integration, receipts,
units and catalog are implemented in the new module. Authoring and these numerical/resource
observations do not establish physical validation or code/science/resource acceptance.
No API/UI/legacy switch, automatic fallback or conditional benchmark has been executed.

The first actual one-annulus synthetic smoke admitted one converged solve with12 residuals:
68.64006938601307 N thrust,14.618511909479102 N*m torque and730.9255954739551 W shaft power.
New V141 tests:48 passed (owner-observed13.55s); combined V141/V140/legacy section/rotor suites:
518 passed before audit-only lint edits. The three new Python files pass Ruff (owner verified).
The final lint changes are equivalent pairwise iteration and an explicit BaseException rationale
for writing a wall-abort audit receipt before a nonzero CLI exit. Product code did not change.
Measured receipts precede those two audit-only source edits; no expensive rerun is claimed or needed.

The actual small-polar resource case completed eight genuine solves and256 genuine residual calls,
32 per annulus, with all eight/256 admitted. Evaluation wall12.493826562s; peak RSS46960 KiB.
Full response:5068173 canonical UTF8 bytes,395761 nodes including keys, depth19.
Its16 actual preparation endpoint calls are separate from the256 rotor residual attempts.
Preparation verified signs, actual f-domain and retained positive normal corrections, then froze
the synthetic request digest. No physical measurements were used to select the fixture.

The owner-run CONFIGURED maximum-shape audit passed without a quota override or fabricated/cached
child: eight actual solve attempts/256 actual residual attempts, seven whole admitted solves/224
admitted residual/load/lookup results. The eighth returned child crossed the real64MiB quota.
Prior admitted children:61813983 bytes/6708401 nodes; including the eighth:70643910 bytes/7666744 nodes.
Receipt: EXECUTION_FAILED / RESOURCE_BUDGET_EXCEEDED, empty outputs/units, prior counts and normal
failure hashes. Rejected-child parent raw copies, whole-child hashes, guard attempts and successful
guards were all zero. Snapshot admission was attempted eight times and completed seven times.
Evaluation wall342.267537853s includes explicit owner SIGSTOP pauses while the command was idle;
evaluation CPU301.351572966s, total CPU310.039415843s, peak process RSS302884 KiB.
Fresh process limits: AS1536MiB, CPU600s, wall600s. Sixteen preparation residual calls are excluded
from the256 rotor attempts. These are observed cases, not universal time, allocation or RAM bounds.

An earlier owner run was ABORTED at the110-second audit wall limit after three solve attempts/96
residual attempts, approximately148356 KiB peak RSS, with no completed rotor response. Its earlier
maximum-report path was subsequently overwritten by the completed run; this note preserves the
reported aborted attempt without inventing a recovered receipt or treating it as completed evidence.

Direct independent byte comparison with accepted V140 covers ALL661 original files under
src/tests/docs/web:249/263/99/50 respectively, with zero changed or missing originals.
The earlier611-path author manifest omitted web's50 files; it was narrower than the owner's661
inventory. It is not used as the final complete comparison and has not been rewritten again.
Full serialized headroom and measurement qualifications are in stable-polar-rotor-resource-audit.md;
the independently reviewable numerical envelope is in stable-polar-rotor-headroom.json.
