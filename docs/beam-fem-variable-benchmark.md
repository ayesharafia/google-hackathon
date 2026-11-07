# Variable-inertia beam MMS benchmark

`benchmark_variable_mms` checks numerical refinement against one manufactured solution.
It is experimental numerical verification; physical validation is not established.
See the [benchmark implementation and returned limitations](../src/physimesh/drone/beam_fem_variable_benchmark.py)
and the [variable-inertia solver and its limitations](../src/physimesh/drone/beam_fem_variable.py).
This documents the local module; it adds no API or catalog integration.

```python
from physimesh.drone.beam_fem_variable_benchmark import benchmark_variable_mms

L = 2.0
meshes = tuple(tuple(L * i / n for i in range(n + 1)) for n in (4, 8, 16))
result = benchmark_variable_mms(
    length_m=L, E_pa=70e9, I_root_m4=1e-6, outer_fibre_m=0.01,
    deflection_scale_m=0.001, mesh_nodes=meshes,
)
for row in result["rows"]:
    print(row["elements"], row["max_element_length_m"],
          row["displacement_rms_error_m"], row["rotation_rms_error_rad"],
          row["stress_rms_error_pa"], row["displacement_order"],
          row["rotation_order"], row["stress_order"])
```

All arguments are keyword-only. Supply positive finite physical parameters;
`mesh_nodes` must be a built-in tuple of 2–7 built-in tuples, each with 2–65 nodes
(1–64 elements). Each mesh starts at exactly zero, ends at exactly `length_m`,
and has strictly increasing nodes. Maximum element lengths must strictly decrease.

With `z=x/L`, `w0=deflection_scale_m`, and `EI=E_pa*I_root_m4`, the reference is
`w(z)=w0*z²*(6-4*z+z²)` and `I(x)=I_root_m4*(1+z/2)`.
The rotation is `(w0/L)*(12*z-12*z²+4*z³)` and stress is
`(E_pa*outer_fibre_m*w0/L²)*12*(1-z)²`.
The ramp has root intensity zero and tip intensity `36*EI*w0/L⁴`;
tip force, uniform load, and tip moment are zero.
Exact tip deflection is `3*w0`; root force is `-18*EI*w0/L³` and root moment
is `-12*EI*w0/L²`, using the solver's sign convention.
For the example these are 157.5 N/m, 0.003 m, -157.5 N, and -210 N m, respectively.

Each RMS error is `sqrt((1/L)*integral(error² dx))` over physical elements.
Five-point Gauss integration integrates squared displacement, rotation, and stress
error polynomials of degrees 8, 6, and 4 exactly in exact arithmetic.
Returned norms are floating-point numerical values, not symbolic exact norms.
Orders use `log(old_error/new_error)/log(old_hmax/new_hmax)`, including graded meshes,
not element counts or `L/n`. An order is `None` on the first row, for nondecreasing
error, or if either error is at or below its `64*epsilon*natural-field-scale` floor.
The scales are `w0`, `w0/L`, and `E_pa*outer_fibre_m*w0/L²`; these floors are
reporting heuristics, not proven precision bounds or pass/fail tolerances.

`rows` contains `elements` (dimensionless), `max_element_length_m` (m),
`tip_deflection_m` (m), `root_force_n` (N), `root_moment_nm` (N m),
`displacement_rms_error_m` (m), `rotation_rms_error_rad` (rad),
`stress_rms_error_pa` (Pa), `displacement_order`, `rotation_order`, `stress_order`,
and `normalized_linear_residual` (the last four are dimensionless).
Top-level reference values are `ramp_tip_load_n_m`, `exact_tip_deflection_m`,
`exact_root_force_n`, and `exact_root_moment_nm`; `output_units` records their units.
Metadata is `schema_version="variable_beam_mms_refinement_v1"`,
`reference_kind="manufactured_quartic_exact_linear_inertia"`,
`physical_validation="NOT_ESTABLISHED"`, `evidence_level="unverified"`,
`feasibility=None`, and `aircraft_status=None` (`None` becomes JSON `null`).

Uniform and graded refinement provide numerical verification only for this fixed
linear inertia and manufactured ramp load, not arbitrary profiles or all loads.
Piecewise-linear inertia represents this MMS profile exactly; that does not promise
fourth-order convergence for smooth nonlinear inertia profiles. The benchmark calls
the existing solver and evaluator; it is not a missing-solver placeholder.

The module's exact `sources` URLs are:
- https://ceae.colorado.edu/~regueiro/courses/CVEN4511_5511_notes.pdf
- https://www.osti.gov/biblio/759450
