# ADR-0005: conditioned maps and bounded axial/failure capacity

Status: implemented and tested, **independent physics review pending**. The user
selected execution of the 5 October development direction, with synthetic inputs
until client data arrives. This is a model design decision, not ADR-0004 client
scope approval or flight acceptance. ADR-0003/v1 and historical evidence remain.

The opt-in `convex_axial_capacity_v2` profile emits `local_mission_capacity_v4`.
It supports the original static six-component balance, declared failed rotors,
matching-map steady axial climb, deterministic joint scenarios and separate
external payload caps. The old `convex_static_hover_v1` still emits local V3
and explicitly refuses extended declarations and conditioned sources.

A `rotor_conditioning_policy_v1` must declare source, torque-fit relative residual
tolerance, relative power/torque measurement bounds and maximum hull-shift fraction.
No real engineering tolerance is defaulted. The map requires strictly increasing
thrust versus RPM, one explicitly covered interval, nonnegative torque and fixed
conditions. Original raw bytes stay in the artifact store. A separate
`rotor_map_conditioned_v1` artifact binds the raw hash and retained coefficients.
Reading validates coefficients under their policy; it does not rerun a future fit.

For torque, minimize maximum relative sample residual for q(T)=aT+b, a>=0.
Zero measured torque is constrained exactly. Refuse when the residual exceeds
the declared tolerance. Retain global absolute error
B=max_i(|qfit_i-qmeas_i|+qmeas_i*uQ/(1-uQ)). This bounds the declared
piecewise-linear raw torque envelope between samples. At any candidate, all
independent rotor error corners produce axis-j moment radius
sum_i |axis_ij|*B_i. Do not cancel equal errors on counter-rotating rotors.
Nominal six-component equilibrium remains required. All three moment-interval
edges must pass sourced case allowances. These allowances describe a permitted
bounded discrepancy; they do not establish that feedback control balances it.

For power, convert shaft samples to electrical watts using declared efficiency
once. Build target_i=max(Pelectrical_i/(1-uP),
(qfit_i+B)*omega_i/eta), with eta=1 for an already electrical map. Compute the
lower convex hull H of targets, then delta=max_i(target_i-H(T_i)) and
Pconditioned=H+delta. Retain delta and refuse an excessive shift or decreasing
curve. The result is convex and at least every target sample. Within a sample
interval, linear interpolation preserves sample-envelope dominance. The product
of increasing affine RPM and affine torque is convex, so its endpoint chord
bounds the declared fitted upper-torque shaft demand. This is conservatism for
the declared surrogate and uncertainty envelope, not unknown installed physics.
A conservative power bound alone does not prove globally conservative physical
payload when torque fitting changes allocations. Our capacity comparison fixtures
hold coordinates and analytic symmetric torque states fixed; real validation is
separate. Certificates using a conditioned surrogate are **unsupported**, since
failure of a conservative envelope cannot prove physical impossibility.

A failed rotor has zero thrust/torque/RPM/input power. Its hardware mass remains;
base configuration/source identity remains known. Other rotors solve the six
balances again. Do not require operating-map coverage or continuous duty from
a rotor that does not operate. General autorotation, fault transients and
installed interference are outside this model.

Climb requires zero attitude/rates/accelerations, +z parallel rotor axes,
world velocity (0,0,Vc), body air-relative velocity (0,0,-Vc) and a positive
explicit inflow Vc. Each active source must match declared density, inflow and
pitch exactly. Case map overrides are retained by hash. This is steady axial
allocation with declared body loads, not a climb aerodynamics predictor;
no hover-to-climb extrapolation or arbitrary motion is inferred.

Deterministic scenarios are sourced joint changes to existing mass items,
atmosphere, covered maps and explicit loads. They preserve stated correlation;
there is no independent Cartesian product or probability claim. Take the
minimum only when nominal and every declared scenario is feasible, then re-solve
all participating cases and sequence energy at that same payload. External
structural/operational caps have separate sources and approval declarations.
Recheck min(cap, supported envelope), because payload intervals can exclude zero
or a smaller candidate. A caller's approval declaration is not authenticated
engineering acceptance. No nominal bound is overwritten by a cap or scenario.

The numerical identity uses an explicit model-module dependency closure and
NumPy/SciPy versions. Cosmetic/API/report edits do not invalidate capacity
identity; model/eligibility/contract/source-policy changes do. This is a local
source identity, not immutable deployment attestation.

MILP/discrete operating points and variable-power quadrature remain conditional
on real-data needs. Real validation, a cross-family independent review, client
engineering acceptance and hosting decisions remain release gates.
