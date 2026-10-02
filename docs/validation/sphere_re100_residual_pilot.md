# Sphere Re=100 execution record

VERIFICATION CASE: sphere Re=100; no aircraft result

Backend: `opencfd/openfoam-run@sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb`

Run group: `/Users/bhupeshcholake/Desktop/Claude Codes/physicore drone/.backend/demo/run_group.json`

Residual stopping tolerance is a chosen 1e-6 for p and U. Load drift and mesh
assessment remain separate. A completed solve is recorded as unverified.

| Mesh | Cells | Iterations | Wall seconds | Peak container bytes |
|---|---:|---:|---:|---:|
| coarse | 80473 | 164 | 16.146 | 194867200 |
| medium | 251192 | 154 | 45.967 | 583458816 |
| fine | 804280 | 149 | 203.464 | 2031714304 |

## coarse

Case: `/Users/bhupeshcholake/Desktop/Claude Codes/physicore drone/.backend/demo/runs/015dee3ba0b24d729aef6c27d436aac0`

```text
    cells:            80473
    Mesh non-orthogonality Max: 30.5321172997 average: 5.2938067045
    Max skewness = 0.831949805147 OK.
Mesh OK.
smoothSolver:  Solving for Ux, Initial residual = 1.53969248844e-08, Final residual = 7.93269173295e-10, No Iterations 1
smoothSolver:  Solving for Uy, Initial residual = 8.87994372542e-07, Final residual = 4.06883517347e-08, No Iterations 1
smoothSolver:  Solving for Uz, Initial residual = 9.82286767776e-07, Final residual = 4.57261522238e-08, No Iterations 1
GAMG:  Solving for p, Initial residual = 1.17429524379e-07, Final residual = 8.83380052825e-09, No Iterations 1
```

## medium

Case: `/Users/bhupeshcholake/Desktop/Claude Codes/physicore drone/.backend/demo/runs/cb6e3668810f4e85bd77733c623a55ac`

```text
    cells:            251192
    Mesh non-orthogonality Max: 33.432419589 average: 4.10870864292
    Max skewness = 0.793522004581 OK.
Mesh OK.
smoothSolver:  Solving for Ux, Initial residual = 1.78273777486e-08, Final residual = 2.32526675596e-09, No Iterations 1
smoothSolver:  Solving for Uy, Initial residual = 9.17835746457e-07, Final residual = 8.85290856567e-08, No Iterations 1
smoothSolver:  Solving for Uz, Initial residual = 9.69415467197e-07, Final residual = 9.37375105373e-08, No Iterations 1
GAMG:  Solving for p, Initial residual = 1.73470005092e-07, Final residual = 1.50940323153e-08, No Iterations 1
```

## fine

Case: `/Users/bhupeshcholake/Desktop/Claude Codes/physicore drone/.backend/demo/runs/f0242f8bcf4d4396a87c97eb89ddd644`

```text
    cells:            804280
    Mesh non-orthogonality Max: 36.9379485766 average: 3.16065054011
    Max skewness = 0.675510541901 OK.
Mesh OK.
smoothSolver:  Solving for Ux, Initial residual = 3.21290953154e-08, Final residual = 9.85381537475e-09, No Iterations 1
smoothSolver:  Solving for Uy, Initial residual = 9.70792607954e-07, Final residual = 8.70036915066e-08, No Iterations 2
smoothSolver:  Solving for Uz, Initial residual = 9.73709318596e-07, Final residual = 8.31540048222e-08, No Iterations 2
GAMG:  Solving for p, Initial residual = 2.69114806301e-07, Final residual = 2.51426982594e-08, No Iterations 1
```
