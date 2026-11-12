# Tabulated geometry hover kernel (experimental)

`physimesh.drone.tabulated_hover_bemt.solve_tabulated_hover` is a separate local
Python kernel, identified in its result as
`tabulated_geometry_hover_experimental`, version `0.1`. It adds piecewise-linear
chord and blade-angle geometry to the accepted isolated-hover closure. Existing
hover models, API, registry, and graph integration are unchanged.

The supplied originalPDF_A §6.2 motivates geometry-dependent blade loads. This
kernel implements only the geometry representation and local-solidity closure
portion of that scope. It does not implement or validate the full scientific
capability described by that section.

## Equations and units

Let rotor radius be R [m], true radius r [m], radial fraction x = r/R,
blade count B, chord c(r) [m], blade angle θ(r) [rad], constant lift slope
a [rad⁻¹], and constant profile drag coefficient Cd [dimensionless]. The local
rotor-normalized solidity is

```text
σ(x) = B c(Rx) / (πR)
```

Each annulus uses small-angle, attached linear lift. The positive inflow ratio
λ = vi/(ΩR) follows from the annular blade/momentum quadratic:

```text
4λ²x = (σa/2)(θx² − λx)
λ = 2θx / (1 + sqrt(1 + 32θx/(σa)))
```

The rationalized expression avoids cancellation in evaluating the positive
root. A zero blade angle gives exactly zero inflow and thrust. Uniform physical
midpoint annuli approximate the following integrals over rcut/R ≤ x ≤ 1:

```text
CT,momentum = ∫ 4λ²x dx
CT,blade    = ∫ (σa/2)(θx² − λx) dx
CPi         = ∫ 4λ³x dx
CP0         = ∫ (σCd/2)x³ dx
CP          = CPi + CP0
```

For density ρ [kg/m³] and angular speed Ω [rad/s], the dimensional results are

```text
T [N]   = ρ πR² (ΩR)² CT,momentum
P [W]   = ρ πR² (ΩR)³ CP
Q [N m] = P / Ω
```

The approximate inflow angle is λ/x and approximate angle of attack is θ − λ/x.
Zero angle can retain positive profile power when Cd > 0. Zero angle and Cd = 0
give zero thrust, power, and torque.

## Strict SI request

All arguments are required keyword arguments. Model and version are result
identifiers, not request fields. Unknown keywords are rejected.

| Field | Contract |
| --- | --- |
| `radius_m` | R > 0, metres |
| `angular_speed_rad_s` | Ω > 0, radians per second |
| `density_kg_m3` | ρ > 0, kilograms per cubic metre |
| `blade_count` | Builtin integer in 1..32 |
| `root_cutout_m` | 0 < rcut < R, metres |
| `annuli` | Builtin integer in 1..2048 |
| `lift_curve_slope_per_rad` | Constant a > 0, per radian |
| `profile_drag_coefficient` | Constant Cd ≥ 0, dimensionless |
| `stations` | Builtin list of 2..256 stations described below |
| `geometry_source` | Nonblank builtin string, at most 2000 characters, valid UTF-8 |
| `geometry_kind` | Exactly `measured`, `digitized_measurement`, `as_designed`, or `synthetic` |
| `uncertainty_status` | Nonblank builtin string, at most 2000 characters, valid UTF-8 |

Each station is an exact builtin dictionary with exactly three builtin string
keys: `radius_m` [m], `chord_m` [m], and `blade_angle_rad` [rad]. Require c > 0
and θ ≥ 0. Station radii must increase strictly within [0, R]. The first station
must lie at or inside the cutout; the final station must equal R exactly.
Geometry below the cutout may be absent. A station at zero is allowed, while
every evaluated annulus remains strictly outside the positive cutout.

Chord and angle are interpolated independently at physical annulus midpoints.
An exact station knot preserves its supplied values. There is no extrapolation,
endpoint autofill, cutout adjustment, or inference of missing hub or airfoil
geometry. The provenance should identify the geometry source/revision and its
true-radius meaning; explicitly unknown uncertainty is permitted. Provenance
and geometry classifications are caller assertions, not verified measurements.

Numerical scalars accept only builtin `int` or `float`; booleans and subclasses
are rejected. All values and derived arithmetic must remain finite and normal,
except explicitly permitted zeros. Unsupported subnormal arithmetic, overflow,
underflow, collapsed physical or normalized coordinates, and excessive
subtractive cancellation in blade loads are rejected with `ValueError`.
Unknown keyword arguments raise `TypeError`. Inputs are never silently rescaled
or clamped. Work limits and precision guards are computational constraints;
they define no physical angle threshold or validated operating envelope.

## Local Python usage

```python
from physimesh.drone.tabulated_hover_bemt import solve_tabulated_hover

result = solve_tabulated_hover(
    radius_m=1.0,
    angular_speed_rad_s=100.0,
    density_kg_m3=1.225,
    blade_count=2,
    root_cutout_m=0.25,
    annuli=64,
    lift_curve_slope_per_rad=5.7,
    profile_drag_coefficient=0.01,
    stations=[
        {"radius_m": 0.25, "chord_m": 0.06, "blade_angle_rad": 0.10},
        {"radius_m": 0.625, "chord_m": 0.08, "blade_angle_rad": 0.06},
        {"radius_m": 1.0, "chord_m": 0.03, "blade_angle_rad": 0.04},
    ],
    geometry_source="synthetic example revision 1; true SI radius",
    geometry_kind="synthetic",
    uncertainty_status="unknown; illustrative geometry only",
)
print(result.thrust_n, result.shaft_power_w, result.shaft_torque_nm)
```

The frozen result contains a frozen station snapshot and tuple arrays for the
actual SI midpoint radii, chords, blade angles, radial fractions, local solidity,
inflow, and approximate angles. It also contains both thrust coefficients,
induced/profile/total power coefficients, SI thrust/power/torque, and balance
residuals. Residuals are blade minus momentum; local residuals compare integrands
before multiplication by annular width, and the maximum is their largest
absolute value. Mutating the request later does not alter the result.

## Numerical verification and scope

Constant chord with constant angle reduces algebraically to the accepted
constant-twist hover model. Constant chord with an affine angle over the active
span reduces to its linear-twist model. Floating-point comparisons allow
roundoff; bit identity is not required. A piecewise-linear table generally only
approximates hyperbolic twist. Constant pitch length p implies
β(r) = atan[p/(2πr)]; it does not imply constant blade angle.

The focused tests compare the reductions across annulus counts and dimensional
scales, and compare variable geometry against independent 80-digit Decimal
interpolation, quadratic roots, loads, and power. Zero-angle profile power is
checked against the analytic integral of piecewise-linear chord times x³.
Refinement checks the midpoint rule's second-order convergence with aligned
segment boundaries. These are checks of equations and discretization, with no
claim of experimental accuracy or physical acceptance.

Every computed result retains `COMPUTED_EXPERIMENTAL` and `NOT_ESTABLISHED`.
The closure assumes isolated hover, small angles, attached linear lift, and
constant lift slope and drag. It includes no Reynolds-dependent polars, stall,
swirl, tip/root loss, compressibility, non-hover flight, ground/interference
effects, or structural qualification. No APC fitting, empirical calibration,
aircraft feasibility, or validation of as-built geometry follows from a finite
answer, a small residual, or midpoint convergence.
