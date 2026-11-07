# Experimental hover BEMT library: numerical benchmark

This new standalone experimental library comprises `hover_bemt.py` and `hover_bemt_benchmark.py`.
It computes isolated-hover blade element momentum theory (BEMT) with small-angle approximations and attached, linear lift.
There is no API integration, registry or dispatch integration, or physical qualification; numerical verification is not experimental validation.

## Formulation and discretization

Let `R` be radius [m], `Omega` angular speed [rad/s], `rho` density [kg/m³], `N` blade count, and `c` constant chord [m].
Use nondimensional radius `r=y/R`, induced velocity `v=lambda*Omega*R`, solidity `sigma=N*c/(pi*R)`, lift slope `a` [rad⁻¹], and constant section drag coefficient `Cd`.
Pitch angles are radians: `theta(r)=pitch_tip_rad` for `constant`, or `theta(r)=pitch_tip_rad/r` for `hyperbolic`.
The local hover balance is `lambda² + (sigma*a/8)*lambda - (sigma*a/8)*theta*r = 0`.
The solver evaluates its nonnegative root as `lambda=2*theta*r/(1+sqrt(1+32*theta*r/(sigma*a)))`, avoiding subtraction in the root formula.
With `r0=root_cutout_fraction` and `n=annuli`, uniform annuli span `r0..1`, with `dr=(1-r0)/n` and midpoints `r_j=r0+(j+1/2)*dr`.
All sums below use those midpoints and the same `dr`:

```text
CT       = sum(4*lambda²*r*dr)
CT_blade = sum((sigma*a/2)*(theta*r²-lambda*r)*dr)
CPi      = sum(4*lambda³*r*dr)
CP0      = sum((sigma*Cd/2)*r³*dr)
CP       = CPi + CP0
T        = rho*pi*R²*(Omega*R)²*CT
Pshaft   = rho*pi*R²*(Omega*R)³*CP
Q        = Pshaft/Omega
```

`CT_blade` independently accumulates the blade-element thrust expression using the solved inflow; it is not a second inflow solution.
Thrust is in N, shaft power in W, and shaft torque in N·m. Power is mechanical shaft power, not electrical input power.
The approximated inflow angle is `lambda/r`; approximated angle of attack is `theta-lambda/r`.
`thrust_balance_coefficient=CT_blade-CT` is a signed integral thrust-coefficient difference.
`max_local_balance_coefficient` is the maximum absolute blade-minus-momentum integrand difference before multiplication by `dr`.
Its units are coefficient per unit nondimensional radius `r`; it is not an annulus thrust in N.

## Call contract and numerical support

Both entry points are keyword-only. Their shared required keywords are shown exactly in the runnable example below.
`solve_hover` additionally accepts `annuli=32`; `benchmark_refinement` instead accepts `annuli_counts=(8, 16, 32, 64, 128)`.
Both default to `twist_law="constant"`; the only other accepted value is `"hyperbolic"`, and the value must be a builtin `str`.
Scalar physical inputs must be builtin `int` or `float`; booleans and other numeric types are rejected with `ValueError`.
Values must convert to finite, normal floats and be positive, except `profile_drag_coefficient` and `pitch_tip_rad`, which may be zero.
`root_cutout_fraction` must satisfy `0<r0<1`; `blade_count` must be a builtin `int` in `1..32`, and `annuli` in `1..2048`.
`annuli_counts` must be a builtin tuple of 3–8 builtin integers, each in `1..2048`, with every entry exactly twice its predecessor.
These are numerical bounds, not a validated aerodynamic operating envelope.

Derived arithmetic rejects unsupported overflow, underflow, subnormal results, and indistinguishable annulus edges or midpoints.
For positive-operand subtraction in angle of attack and blade thrust, the difference must exceed `sqrt(sys.float_info.epsilon)*max(left,right)`; two exact zero operands are allowed.
This subtraction guard limits cancellation amplification to roughly `1/sqrt(epsilon)`, retaining roughly half the significand; it concerns numerical representation only.
It is not a physical small-angle threshold. An accepted result does not guarantee a uniform error bound.
Many finite extreme inputs are rejected; even the zero-pitch branch can reject derived overflow or mesh collapse before returning a result.
For supported zero-pitch inputs, inflow, thrust, and induced power are zero; positive drag gives profile-only power, while zero drag gives zero total power and torque.

`solve_hover` returns a frozen `HoverSolution` dataclass with tuple-valued radial, inflow, pitch, inflow-angle, and angle-of-attack arrays.
Its scalar fields include the coefficients, dimensional loads, balances, and annulus count; `status="COMPUTED_EXPERIMENTAL"` and `physical_validation="NOT_ESTABLISHED"`.
The benchmark returns a dictionary with `reference`, `rows`, `notes`, `source_url`, `status="BENCHMARK_COMPUTED"`, and the same physical-validation marker.

## Reproducible benchmark

Run this in the repository environment with Python 3.11 or later and the package installed (or `PYTHONPATH=src`).

```python
import json

from physimesh.drone.hover_bemt_benchmark import benchmark_refinement

report = benchmark_refinement(
    radius_m=1.0, angular_speed_rad_s=100.0, density_kg_m3=1.225,
    blade_count=2, chord_m=0.05, lift_curve_slope_per_rad=5.7,
    profile_drag_coefficient=0.01, pitch_tip_rad=0.08,
    root_cutout_fraction=0.2, twist_law="hyperbolic",
    annuli_counts=(8, 16, 32, 64, 128),
)
print(json.dumps(report, indent=2, allow_nan=False))
```

For this hyperbolic case, `theta*r=0.08` and the exact-arithmetic inflow is constant, `lambda≈0.03273919828742709659425409118`.
The independent reference uses 80-digit `Decimal` arithmetic, decimal strings for the supplied parameters, and a high-precision pi constant, rather than solver samples.
With `k=sigma*a/8`, it evaluates `lambda=2*k*pitch_tip_rad/(k+sqrt(k²+4*k*pitch_tip_rad))` and the closed-form integrals:

| Quantity | Exact-arithmetic integral | Rounded float reference |
| --- | --- | --- |
| CT | `2*lambda²*(1-r0²)` | `0.002057961800646661` |
| CPi | `2*lambda³*(1-r0²)` | `6.737601945932155e-5` |
| CP0 | `sigma*Cd/8*(1-r0⁴)` | `3.9725073795737075e-5` |

`reference_kind="ideal_hyperbolic_closed_form"`. CT and CPi integrands are linear in `r`, so midpoint integration is exact in exact arithmetic at every mesh size.
Their floating-point differences measure roundoff, not a convergence sequence; `CT_observed_order` and `CPi_observed_order` always remain `None`.
For profile power, let `h=(1-r0)/n` and `m` be a cell midpoint: `integral_cell(r³ dr)-h*m³=m*h³/4`.
Summing `m` gives `n*(1+r0)/2`, hence the positive global error is `CP0_ref-CP0_midpoint=(sigma*Cd/2)*(1-r0)²*(1-r0²)/(8*n²)`.
This verifies second-order profile convergence analytically; doubling `n` quarters the quadrature error before roundoff cancellation dominates.
For `n=8,16,32,64,128`, reported `CP0_absolute_error` is approximately `1.9098593e-7, 4.7746483e-8, 1.1936621e-8, 2.9841552e-9, 7.4603880e-10`.
`profile_observed_order=log2(coarse_error)-log2(fine_error)` is computed only when `0<fine_error<coarse_error`; otherwise it is `None`.
References are rounded to floats before errors are subtracted; references and errors can round to zero. Apparent orders near cancellation are not reliable accuracy evidence.
For constant pitch, `reference_kind="mesh_change_only"`, all reference values and absolute errors are `None`, and all observed orders are `None`.
Rows report absolute successive `CT_change` and `CP_change` (first row `None`); refinements are mesh-change diagnostics, not error bars.

## Scope and sources

There are no tip or hub loss factors, swirl, stall, Reynolds-dependent polars, compressibility, forward flight, climb/descent, ground effects, interference, coupled-aircraft effects, or structural-strength assessment.
The cutout specifies an integration domain; it is not a validated hub-loss treatment. Small-angle applicability and physical qualification remain unestablished.
The formulation follows [Georgia Tech combined blade-element/momentum notes](https://sankar.gatech.edu/AE6070/Combined.BE.Momentum.Theory.doc) and [Sumeet Kumar's BEMT notes](https://kumar-sumeet.github.io/HeliAeroNotes/Lectures/2_BET/2_BEMT.html); benchmark results verify numerical behavior only.
