# Uniform cantilever modal candidate

`physimesh.drone.beam_modal.solve_cantilever_modes(*, length_m, E_pa, I_m4,
mass_per_length_kg_m, elements=8, modes=3)` is a standalone research-grade
numerical candidate. It has no application API integration. Independent review
is required before integration or other effects.

The model is one uniform, undamped, unforced Euler–Bernoulli cantilever in one
bending plane. Inputs use metres, pascals, metres to the fourth power, and
kilograms per metre. Only exact builtin int/float physical scalars are accepted,
converted to finite positive normal binary64. Booleans, subclasses, NumPy
scalars, nonpositive, subnormal and nonfinite values are refused. Counts require
exact builtin integers: 2..64 elements and 1..min(6, 2*elements) modes. These are
support limits; coarse meshes need not resolve all requested modes.

Dimensionless Hermite coordinates are (w/L, theta), xi=x/L. Assembly uses
consistent translational mass, with root displacement and slope eliminated.
Mass Cholesky whitening uses triangular solves, then symmetric `eigh` with
`driver="evd"`. There are no explicit matrix inverses. The physical angular
frequency scale is sqrt(E I/(mu L^4)), evaluated using bounded mantissas and
integer exponents. Computed scale and frequencies must be finite normal;
classification against an exact reference is not guaranteed within one ulp of
a normal/overflow threshold.

All matrix norms are spectral and vector norms Euclidean. With q=2*elements
and eps=binary64 epsilon, symmetry defects must be <=32 q eps before repair.
Both matrices must admit Cholesky factors. Condition budgets are eps*kappa(M)
<=1e-8 and eps*kappa(A)<=1e-4. Whitened residual and orthogonality bounds are
128 q eps; generalized residual bound is min(1e-6,256 q eps sqrt(kappa(M))) and
mass orthogonality bound is min(1e-6,256 q eps kappa(M)). With
 delta=128 q eps ||A||, the first eigenvalue must exceed delta and all gaps
involving selected modes, including the first omitted neighbor, must exceed
2 delta. Tip magnitude relative to vector norm must exceed 128 q eps.
No gates are loosened for fine meshes. No partial success is returned.

Success contains exactly `status`, `inputs`, `modes`, `diagnostics`, `limits`,
and `physical_validation`. Refusal contains exactly `status`, `refusal`,
`limits`, and `physical_validation`; refusal details contain `code`, `field`,
and a concise `message` without exception internals. Metadata uses contract
`uniform-cantilever-modal-v1`. `numerical_qualification`, `mesh_accuracy`, and
`physical_validation` remain `NOT_ESTABLISHED` on every applicable response.
Results contain only finite builtin JSON values, including structural zeros.

Each mode reports dimensionless eigenvalue, `omega_rad_s` in radians/second,
`frequency_hz` in cycles/second, nodal `xi`, `normalized_deflection`, and
`normalized_deflection_derivative_xi`. Shapes have exact root zeros and tip
+1. The derivative is ds/dxi of the tip-normalized shape, also called slope_xi;
it is not an unnormalized physical rotation. Within each element interpolate
using the cubic Hermite functions with slope terms multiplied by h=1/elements;
differentiate with respect to xi for slope. Shapes imply no vibration amplitude.

Passing numerical gates establishes only backward consistency of this discrete
computation. Small residuals and condition budgets do not promise 1e-8 frequency
accuracy. A previously observed 64-element `evd` mode-one relative discrepancy
of about 7.4e-9 is specific to that environment; method spread is known. It is
not a portable bound or qualification of this implementation. Mesh error and
physical accuracy require separate work. Shear deformation, rotary inertia,
tip mass, damping, taper, prestress, joints, rotation and aeroelasticity are
excluded. No aircraft feasibility, resonance clearance, strength or
airworthiness claims follow.

The [IFEM Chapter 31](https://quickfem.com/wp-content/uploads/IFEM.Ch31.pdf)
provides background on Hermite consistent mass and the omission of rotary
inertia. This supplied source URL was not newly verified. Independent review,
independent quadrature verification, broader numerical qualification and
physical validation remain required before downstream use.

## Exact nested response fields

`inputs` contains exactly `length_m`, `E_pa`, `I_m4`,
`mass_per_length_kg_m`, `elements`, `modes`. Accepted physical scalars are
returned as builtin floats. Each entry of `modes` contains exactly `mode_index`
(starting at one), `eigenvalue_dimensionless`, `omega_rad_s`, `frequency_hz`,
`xi`, `normalized_deflection`, `normalized_deflection_derivative_xi`.
All three nodal arrays have elements+1 entries; eigenpairs are ordered by
increasing eigenvalue. The eigenvalue, xi, normalized deflection and its xi
derivative are dimensionless.

`diagnostics` contains exactly `frequency_scale_rad_s`, `free_dofs`,
`condition_mass_2`, `condition_whitened_2`, `symmetry_relative`,
`residual_whitened`, `residual_generalized`, `orthogonality_whitened_2`,
`orthogonality_mass_2`, `uncertainty_radius`, `minimum_selected_gap`,
`tip_relative_magnitudes`, `thresholds`. `symmetry_relative` contains exactly
`stiffness`, `mass`, `whitened` and reports defects before repair. Residual and
tip lists follow mode order. All diagnostics except the angular frequency
scale and the integer free DOF count are dimensionless.

`thresholds` contains exactly `symmetry_relative`, `residual_whitened`,
`residual_generalized`, `orthogonality_whitened_2`, `orthogonality_mass_2`,
`tip_relative_min`, `eigenvalue_min`, `gap_min`. These report the actual
bounds defined above; eigenvalue and gap comparisons are strict lower bounds.

`limits` contains exactly:

| Field | Value |
| --- | --- |
| contract_version | uniform-cantilever-modal-v1 |
| elements_min / elements_max | 2 / 64 |
| modes_min / modes_max | 1 / 6 |
| modes_free_dof_cap | true |
| scalar_policy | builtin-int-or-float-positive-normal-binary64 |
| eps_condition_mass_max | 1e-8 |
| eps_condition_whitened_max | 1e-4 |
| numerical_qualification | NOT_ESTABLISHED |
| mesh_accuracy | NOT_ESTABLISHED |
| model_scope | uniform-undamped-Euler-Bernoulli-cantilever |

`refusal.code` is one of `INVALID_TYPE`, `INVALID_VALUE`,
`UNSUPPORTED_RANGE`, `NONFINITE_OR_UNDERFLOW`, `NOT_SPD`, `ILL_CONDITIONED`,
`SOLVER_FAILURE`, `DIAGNOSTIC_FAILURE`, `UNRESOLVED_SPECTRUM`,
`TIP_NORMALIZATION_FAILURE`. Its `field` is an attributable input name or null.
Inputs are checked in signature order, then assembly/scaling, factorization,
conditioning, spectrum, diagnostics and normalization. The first failing gate
wins. Negative and zero finite physical scalars are `INVALID_VALUE`;
unrepresentable integer conversions are `NONFINITE_OR_UNDERFLOW`.

The tests compare actual public results with independently integrated
four-point Gauss stiffness/mass matrices and generalized symmetric eigenpairs,
and with supplied high precision discrete numerical references. Conservative
regression tolerances apply only to those finite comparisons. They establish
neither a universal error bound nor physical model accuracy. A bracketed root
solve supplies the analytical first-mode convergence comparison.

Normalization conservatively checks the computed division against the saved
vector: any nonzero component rounded to zero is refused, as is a nonzero
subnormal component or any nonfinite normalized component. Exact structural
zeros remain allowed. This representability check covers the final tip
normalization; it cannot detect every loss within preceding LAPACK operations.
Tests that inject synthetic snapshots at this boundary exercise the gate without
claiming those snapshots arise from supported physical inputs.
