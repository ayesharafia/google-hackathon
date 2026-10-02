# Sphere native-load verification

VERIFICATION CASE: not an aircraft result. Evidence level remains unverified.

Replay command:

```sh
.venv/bin/python scripts/demo_loads.py --run-group .backend/demo-load-history/run_group.json
```

| Level | Cd from native surface | Reconciliation | Last-window relative drift |
|---|---:|---|---:|
| coarse | 1.146892575 | accepted | 2.63668e-9 |
| medium | 1.124913006 | accepted | 8.51886e-11 |
| fine | 1.120620183 | accepted | 3.37150e-10 |

Every component of pressure force, viscous force, total force and origin moment,
and the drag coefficient, meets `abs(error) <= 1e-3 abs(native) + 1e-6`.
Pressure dimensions determine conversion; native kinematic pressure and shear
are multiplied by declared density once. OpenCFD fluid-domain face vectors and
wallShearStress are each negated once for traction on the solid. No smoothed
visualization mesh is integrated. Byte-value-identical adjacent final history
rows written by OpenFOAM's end callback are collapsed for statistics; conflicting
duplicates are refused. Source-byte hashes appear in `load_results.json` and
must match the execution record before replay is accepted.

The windows cover iterations 412–612 and 612–812 (201 samples each). These are
steady iteration statistics, not physical time averages. Residuals remain in
the execution record. No input or numerical setting was tuned to a reference.

Fine Cd is +2.6463% from the plan's frozen Schiller–Naumann value 1.09173.

## Mesh estimate and limits

Actual effective ratios: r21=1.473897069, r32=1.461454181, from cell counts.
The generalized Richardson fit gives observed order 4.326944948,
extrapolated Cd 1.119634987, fine-grid GCI 0.001098941 (0.109894%).

The cell-count basis approximates a common-domain global h. Surface refinement
levels are fixed while background divisions change. The observed order is high
relative to a nominal second-order scheme. Three numbers fitting a monotonic
curve do not establish an asymptotic range. Show this as a qualified mesh
sensitivity estimate; it excludes domain, modeling, boundary-condition and
geometric errors. It cannot justify claiming 0.11% total accuracy.

Source: [Celik et al., Procedure for Estimation and Reporting of Uncertainty Due
to Discretization in CFD Applications, Eqs 1, 3, 4, 7](https://www.asme.org/wwwasmeorg/media/resourcefiles/shop/journals/jfenumaccuracy.pdf).
The monotonic branch is solved directly for a positive order; oscillatory or
nonpositive-order data receive no GCI. Analytical unequal-spacing second-order
fixtures recover order 2 and the exact extrapolate.

## Independent-review follow-up, 2026-10-03

F1 adds an order-capped sensitivity estimate with p_used=min(4.326944948,2)
and Fs=1.25: GCI_fine=0.00408440535 (0.408440535%). The nominal cap comes from
the retained sphere schemes. The observed-order estimate remains available;
the order-capped value leads the page and mesh-chart error bar. Neither is a
proven error bound or total uncertainty. The estimator code hash, cap, order
and safety factor are retained in the regenerated load record. Published
packages from before this correction remain intact. F3 corrected the stopping
rule description in sphere_re100_runs.md without changing any native run.
