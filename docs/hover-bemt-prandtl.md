# Opt-in Prandtl losses for small-angle hover BEMT

`hover_bemt_losses.py` is a separate, opt-in calculation; the legacy
`hover_bemt.py` core remains unchanged. This is no new public API/catalog entry.
`solve_hover_prandtl` returns a frozen `PrandtlHoverSolution` envelope around an
unchanged `HoverSolution` type, available as `.solution`. The nested status stays
`COMPUTED_EXPERIMENTAL`; envelope metadata records `loss_model="prandtl_small_angle"`
and `physical_validation="NOT_ESTABLISHED"`, station factors, the largest station
iteration count, and the explicitly supplied hub radius fraction.

`hub_loss_radius_fraction` is required: `0 < hub <= root_cutout_fraction < 1`.
The numerical cutout neither implies a physical hub radius nor verifies geometry.
The standalone `prandtl_tip_hub_factor` requires `0 < hub < r < 1`, nonnegative
inflow, and a built-in integer blade count `1 <= B <= 32`. Numeric inputs must
satisfy the core's built-in-number and finite-normal arithmetic guards.

Let `r = radius/R`, `h = Rhub/R`, and `lambda = induced_velocity/(omega*R)`.
The chosen hub convention uses **Rhub in the denominator**. With the model's
small-angle substitution `|sin(phi)| ~= lambda/r`, rather than exact trigonometry:

```text
f_tip = (B/2) * (1-r)/lambda
f_hub = (B/2) * r*(r-h)/(h*lambda)
P(f) = (2/pi) * atan2(sqrt(-expm1(-2*f)), exp(-f))
F = P(f_tip) * P(f_hub)
```

This stable `atan2`/`expm1` expression evaluates the actual factor, not a leading
series approximation. Zero inflow uses the documented limit `F=1`.
Each part saturates to `1` at `f >= 40`, with absolute factor error below about
`3e-18` per part. The guarded numerator-versus-`40*divisor` comparison precedes
division; unsupported underflow/overflow ranges are conservatively refused.
Otherwise positive intermediates must remain finite and normal; exact zeros are
accepted only where allowed. Factors must satisfy `0 < F <= 1`, without clipping
apart from the documented saturation.

The solver first calls the original lossless `solve_hover` for validation and an
initial solution. All original domain and positive-difference/cancellation guards
remain in force. This lossless preflight can conservatively reject a case that a
lossy calculation might otherwise support. Unsupported hover keywords raise
`ValueError`. With `sigma = B*chord/(pi*R)` and lift slope `a`, each station iterates:

```text
lambda_new = 2*theta*r / (1 + sqrt(1 + 32*F(lambda)*theta*r/(sigma*a)))
momentum_local = 4*F*lambda**2*r
blade_local = (sigma*a/2)*(theta*r**2 - lambda*r)
induced_local = momentum_local*lambda
```

Momentum thrust and induced power use the corrected factors; blade loading is
rebalanced with the solved inflow. Profile power is copied unchanged, bit for bit.
The relative update check is `abs(new-old) <= 1e-13*max(abs(new),abs(old))`.
After convergence, `F` is recomputed and final local balance must satisfy
`abs(blade-momentum) <= 1e-10*max(abs(blade),abs(momentum))`; zero/zero is accepted.
These are numerical checks, not physical-validity criteria. `max_iterations`
defaults to `100`, accepts built-in integers `1..1000`, and caps each station.
Exhaustion, failed balance, or arithmetic refusal raises `ValueError`: no partial
result is returned. Zero-pitch stations use zero inflow, factor one, zero iterations.

Synthetic example, with the package installed:

```python
from physimesh.drone.hover_bemt_losses import solve_hover_prandtl

result = solve_hover_prandtl(
    radius_m=1.0, angular_speed_rad_s=100.0, density_kg_m3=1.225,
    blade_count=2, chord_m=0.05, lift_curve_slope_per_rad=5.7,
    profile_drag_coefficient=0.01, pitch_tip_rad=0.12,
    root_cutout_fraction=0.2, annuli=32, hub_loss_radius_fraction=0.2,
)
print("CT:", result.solution.thrust_coefficient)
print("factor bounds:", min(result.tip_hub_loss_factor),
      max(result.tip_hub_loss_factor))
print("max iterations:", result.max_fixed_point_iterations)
```

There is no external NASA geometry validation or empirical fit, and no established
reference-error or formal-order guarantee. This model excludes swirl, stall,
airfoil polars, Reynolds/Mach effects, non-hover, strength, and electrical modeling.
The source cites [CCBlade's raw source](https://raw.githubusercontent.com/byuflowlab/CCBlade.jl/master/src/airfoils.jl)
and the [NREL hub-loss discussion](https://forums.nrel.gov/t/hub-losses/368).
The small-angle substitution is this implementation's choice; those references
do not establish physical validation of these results.
