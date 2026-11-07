# Variable-inertia beam FEM

`solve_beam_variable` models a straight, static Euler–Bernoulli cantilever with
an ideal clamp at x=0 (`w=theta=0`), constant E, and continuous piecewise **linear**
I(x) interpolated between nodal values. Nonuniform node spacing is supported.
Use consistent SI units throughout; dimensional consistency is not validation.

| Solver input (keyword) | SI unit / meaning |
| --- | --- |
| `length_m` | m; positive length L |
| `E_pa` | Pa; positive constant Young's modulus E |
| `nodes_m` | m; built-in tuple of strictly increasing node coordinates |
| `second_moments_m4` | m⁴; built-in tuple of positive nodal second moments I |
| `outer_fibre_m` | m; positive outer-fibre distance c |
| `tip_force_n` | N; nonnegative P, default 0 |
| `uniform_load_n_m` | N/m; nonnegative q, default 0 |
| `ramp_load_root_n_m`, `ramp_load_tip_n_m` | N/m; nonnegative ramp endpoints, default 0 |
| `tip_moment_n_m` | N·m; nonnegative Mtip, default 0 |

The distributed load is `q + qr*(1-x/L) + qt*x/L`; uniform and ramp loads add.
Positive w follows positive P; positive theta=dw/dx and Mtip acts on theta.
Root reactions oppose applied loads: `root_force_n=-(P+q*L+(qr+qt)*L/2)` and
`root_moment_nm=-(P*L+q*L**2/2+L**2*(qr+2*qt)/6+Mtip)`, up to arithmetic error.
They are negative for corresponding nonzero positive loading; zero loads give zeros.

Numeric inputs must be finite built-in int/float, excluding bool, strings and NumPy
scalars. The two tuples must have equal lengths 2..65 (1..64 elements), begin at
0 and end exactly at L. For physical element lengths h, `min(h)>=L*2**-20`,
`max(h)/min(h)<=1024`, and `max(I)/min(I)<=1e12` are required.
These are numerical support limits, not conditioning or accuracy guarantees.
Finite-normal arithmetic guards can reject further cases; invalid inputs and
failed solves raise errors. Validation precedes the exact all-zero-load result.

Cubic Hermite elements use displacement and rotation degrees of freedom (DOFs).
Three-point Gauss integration exactly integrates the polynomial element stiffness
integrand (degree at most 3) and consistent linear-ramp load integrand (degree at
most 4), apart from floating-point error. This does not make the beam solution exact.
The dense NumPy system is assembled symmetrically and the two root DOFs clamped.

`VariableBeamSolution` is frozen, with tuple-valued arrays. Its fields are:

| Fields | Meaning / unit |
| --- | --- |
| `L`, `E`, `rigidity_root_n_m2`, `c` | L [m], E [Pa], E·Iroot [N·m²], c [m] |
| `scale` | displacement scale S·L³/(E·Iroot) [m]; zero for zero loads |
| `n`, `elements` | element count; tuple of element DOF index quadruples |
| `ndof` | internal dimensionless alternating wbar, thetabar; length 2n+2 |
| `nodes`, `second_moments_m4` | physical node coordinates [m], nodal I [m⁴] |
| `displacements`, `rotations` | physical nodal w [m], theta [rad] |
| `root_force_n`, `root_moment_nm` | signed clamp reactions [N], [N·m] |
| `normalized_linear_residual` | dimensionless algebraic diagnostic |
| `physical_validation` | always `"NOT_ESTABLISHED"` |

Here `z=x/L`, `S=max(P,q*L,(qr+qt)*L/2,Mtip/L)` for nonzero loading;
`w=scale*wbar`, `theta=(scale/L)*thetabar`, and curvature scales by `scale/L**2`.
The residual is `maxabs(Kff*uf-ff)/(maxabs(Kff)*maxabs(uf)+maxabs(ff))`.
It is neither a discretization/physical error bound nor an acceptance criterion.

`evaluate_variable_solution(sol, element_index, local_coordinate)` requires a
built-in int index in `0..sol.n-1` and finite built-in numeric t in [0,1]. It returns
the existing `BeamPoint`: `x_m` [m], `deflection_m` [m],
`rotation_rad` [rad], `curvature_1_m` [1/m], and
`nominal_bending_stress_pa` = E·c·curvature [Pa]. The evaluator uses the stored dimensionless DOFs without mutation.
w is C1-continuous, with continuous theta across elements; curvature and stress
may jump. Evaluation chooses the requested element side and performs no smoothing.

With the package installed:

```python
from physimesh.drone.beam_fem_variable import solve_beam_variable, evaluate_variable_solution

L, E, I0, c = 2.0, 70e9, 1e-6, 0.01
nodes = (0.0, 0.5, 1.0, 1.5, 2.0)
inertias = tuple(I0 * (1 - 0.5 * x / 2) for x in nodes)
sol = solve_beam_variable(
    length_m=L, E_pa=E, second_moments_m4=inertias, nodes_m=nodes,
    outer_fibre_m=c, tip_force_n=10.0, uniform_load_n_m=0.0,
)
print("tip w [m]:", sol.displacements[-1])
print("root reactions [N, N m]:", sol.root_force_n, sol.root_moment_nm)
print("interior BeamPoint at x=0.75 m:", evaluate_variable_solution(sol, 1, 0.5))
```

Linear nodal I cannot represent EI jumps; this interface also excludes off-node
point loads. Sampling smooth nonlinear I introduces O(h²) coefficient representation
error through linear interpolation. Total comparisons with T2/T3 nonlinear-profile
closed forms must not demand fourth-order convergence. For exactly represented
linear I and suitable manufactured solutions (MMS), clean Hermite field errors
can converge as O(h⁴) in w and O(h²) in curvature/stress above the numerical floor.
There is no nodal exactness guarantee for variable I. Gauss-sampled RMS error is a
quadrature approximation, not an exact error norm.

Physical validation is **NOT_ESTABLISHED**: no material, aircraft or joint validation;
no shear deformation, torsion, axial response, buckling, fatigue, nonlinear response
or strength assessment. This document adds no API/catalog dispatch or physical validation.
Contract references: [Regueiro, Eq. 3.28](https://ceae.colorado.edu/~regueiro/courses/CVEN4511_5511_notes.pdf)
and [PyCBA theory, stiffness integral](https://ccaprani.github.io/pycba/theory.html).
