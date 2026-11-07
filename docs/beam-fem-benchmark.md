# Experimental 1D beam FEM benchmark

**Scope.** Static, straight, uniform, small-deflection Euler-Bernoulli bending with constant Young's modulus \(E\) and second moment of area \(I\).
The caller supplies positive outer-fibre distance \(c\); tip force \(P\) and uniform load \(q\) are nonnegative and act in the same direction.
The clamp imposes zero displacement and slope: \(w(0)=w'(0)=0\).
Dimensions: \(E\) in \(\mathrm{Pa}\), \(I\) in \(\mathrm{m}^4\), \(c\) and \(L\) in \(\mathrm{m}\), \(P\) in \(\mathrm{N}\), \(q\) in \(\mathrm{N/m}\), slope \(\theta=w'\) in \(\mathrm{rad}\), curvature \(w''\) in \(\mathrm{m}^{-1}\), and signed stress in \(\mathrm{Pa}\).
Excluded: shear deformation, torsion, geometric/material nonlinearities, 3D joint stress, buckling, fatigue, aircraft strength, and allowable checks.

**Formulation and mesh.** The solver uses 1-64 uniform elements with cubic Hermite displacement and slope interpolation, giving \(C^1\) continuity.
It assembles and solves the nondimensional FEM matrix system with consistent element loads.
The analytical solution is used separately by the benchmark, not substituted into the FEM solve.
Primary reference: [Regueiro, University of Colorado Boulder, 2024, Eq. 3.28](https://ceae.colorado.edu/~regueiro/courses/CVEN4511_5511_notes.pdf).

**Independent analytical comparison.** For \(0\le x\le L\), the reference displacement is
\[
w_{\mathrm{ref}}(x)=\frac{Px^2(3L-x)}{6EI}+\frac{qx^2(6L^2-4Lx+x^2)}{24EI}.
\]
The reference curvature and signed nominal outer-fibre bending stress are
\[
w_{\mathrm{ref}}''(x)=\frac{P(L-x)+q(L-x)^2/2}{EI},
\qquad
\sigma_{\mathrm{ref}}(x)=Ec\,w_{\mathrm{ref}}''(x).
\]
The evaluator returns signed stress \(\sigma_h(x)=Ec\,w_h''(x)\) at the caller-supplied positive outer-fibre distance \(c\), without taking an absolute value.
Stress signs follow this bending convention; the opposite fibre has the opposite sign.
The reconstructed FEM stress can be negative within the final element near the free end under uniform loading, even though the analytical reference is nonnegative.
This is a curvature approximation effect, not a strength result.
The separate benchmark compares reconstructed FEM displacement and signed stress against these analytical fields.

**Verification.** The benchmark computes field RMS errors as
\[
e_f=\sqrt{\frac{1}{L}\int_0^L(f_h-f_{\mathrm{ref}})^2\,dx}.
\]
It uses five-point Gauss quadrature on each element.
The displacement error is quartic, so its square has degree eight; the signed stress error is quadratic, so its square has degree four.
The quadrature integrates both squared errors exactly in exact arithmetic.

For uniform element length \(h=L/n\), independent exact-arithmetic RMS identities are
\[
e_w=\frac{qh^4}{24EI\sqrt{630}},
\qquad
e_\sigma=\frac{qch^2}{I\sqrt{720}}.
\]
The tip-force contribution is cubic and representable by the FEM space, so these errors arise from the uniform-load contribution.
For \(q>0\), the identities give fourth-order displacement convergence and second-order stress convergence.
Computed errors follow these rates while they remain above roundoff.

Tip and nodal displacements can already be exact in exact arithmetic.
Their agreement with the reference does not establish field convergence.
For pure tip loading, the exact displacement is cubic and representable by the FEM space, so convergence orders are not meaningful.

For pure tip loading (\(q=0\)), the benchmark deliberately reports refinement orders as `None`, including when computed errors are positive due to roundoff.
For \(q>0\), numerical refinement orders are \(\log_2(e_{\mathrm{coarse}}/e_{\mathrm{fine}})\), with `None` reported for zero or nondecreasing errors.
Tiny, monotonically decreasing roundoff errors can still yield a meaningless numerical order.

Root reactions oppose the applied force and moment directions:
\[
R_0=-(P+qL),
\qquad
M_0=-\left(PL+\frac{qL^2}{2}\right).
\]
The reported balance residuals are \(R_0+P+qL\) and \(M_0+PL+qL^2/2\).
The normalised matrix residual is
\[
\frac{\operatorname{maxabs}(K_{ff}u_f-f_f)}
{\operatorname{maxabs}(K_{ff})\operatorname{maxabs}(u_f)+\operatorname{maxabs}(f_f)}.
\]
Here \(\operatorname{maxabs}\) is the maximum absolute entry, not an induced matrix norm, so this is not a rigorous backward error.
Matrix residuals and global force/moment balances are arithmetic diagnostics, not physical validation or pass gates.

**Numerical support.** Conservative finite-normal intermediate checks can reject mathematically finite extreme inputs.
The fixed mesh cap establishes neither conditioning nor accuracy; material suitability and beam-theory applicability remain unverified.

**Usage.** The experimental solver, evaluator, and benchmark are imported from their implementation modules.
The solver accepts `elements`; the benchmark accepts `mesh_elements`, a tuple of 3-7 element counts doubling within 1-64.

```python
from physimesh.drone.beam_fem import solve_beam, evaluate_solution
from physimesh.drone.beam_fem_benchmark import benchmark_refinement

parameters = dict(
    length_m=2.0,
    E_pa=70e9,
    I_m4=1e-6,
    outer_fibre_m=0.01,
    tip_force_n=10.0,
    uniform_load_n_m=100.0,
)

solution = solve_beam(**parameters, elements=8)
tip = evaluate_solution(
    solution,
    element_index=solution.n - 1,
    local_coordinate=1.0,
)

benchmark = benchmark_refinement(
    **parameters,
    mesh_elements=(1, 2, 4, 8, 16),
)
```

For this example, \(L=2\ \mathrm{m}\), \(E=70\times10^9\ \mathrm{Pa}\), \(I=10^{-6}\ \mathrm{m}^4\), \(c=0.01\ \mathrm{m}\), \(P=10\ \mathrm{N}\), and \(q=100\ \mathrm{N/m}\).
The computed field RMS errors are:

| Elements | Displacement RMS error (m) | Signed nominal stress RMS error (Pa) |
| --- | --- | --- |
| 1 | 3.79438e-05 | 149071.2 |
| 16 | 5.78977e-10 | 582.309 |

The refinement sequence demonstrates approximately fourth-order displacement convergence and second-order stress convergence.
The analytical tip displacement is
\[
w_{\mathrm{ref}}(L)=\frac{PL^3}{3EI}+\frac{qL^4}{8EI}
=0.003238095238\ \mathrm{m}.
\]
FEM tip values agree to numerical precision across the meshes; this agreement is not evidence of tip convergence.
The root reactions are approximately \(-210\ \mathrm{N}\) and \(-220\ \mathrm{N\,m}\).

**Status.** Experimental only: no API or registry binding, automatic dispatch, automatic physical validation, or aircraft pass/fail decision.
Success means calculation only; the beam/joint specification is not complete because joints and 3D effects are excluded.
The benchmark reports `physical_validation="NOT_ESTABLISHED"`.
This covers only the structural-demonstration part of original PDF §11.4; it does not complete M7/M8.
Promotion requires independent code and benchmark review plus broader validation using real geometry, materials, and experimental evidence.
