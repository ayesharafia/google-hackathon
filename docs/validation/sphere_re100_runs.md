# Sphere Re=100 execution record

VERIFICATION CASE: sphere Re=100; no aircraft result

Backend: `opencfd/openfoam-run@sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb`

Run group: `/Users/bhupeshcholake/Desktop/Claude Codes/physicore drone/.backend/demo-load-history/run_group.json`

After 400 warm-up iterations, a vendor-derived drag-average controller waits for a 400-step window within
an absolute range of 1e-3, then retains 400 further iterations. The cap is
3000. Independent 200-step drift and mesh checks remain separate. Completion
is recorded as unverified until post-processing gates run.

| Mesh | Cells | Iterations | Wall seconds | Peak container bytes |
|---|---:|---:|---:|---:|
| coarse | 80473 | 812 | 40.929 | 205983744 |
| medium | 251192 | 812 | 227.632 | 613011456 |
| fine | 804280 | 812 | 653.090 | 2198327296 |

## coarse

Case: `/Users/bhupeshcholake/Desktop/Claude Codes/physicore drone/.backend/demo-load-history/runs/78d9495dd48b4b528746f73b2768848b`

```text
    cells:            80473
    Mesh non-orthogonality Max: 30.5321172997 average: 5.2938067045
    Max skewness = 0.831949805147 OK.
Mesh OK.
smoothSolver:  Solving for Ux, Initial residual = 1.18944241691e-08, Final residual = 2.63168445703e-10, No Iterations 1
smoothSolver:  Solving for Uy, Initial residual = 9.99204806839e-08, Final residual = 2.02466211352e-09, No Iterations 1
smoothSolver:  Solving for Uz, Initial residual = 1.03522126825e-07, Final residual = 2.10011812738e-09, No Iterations 1
GAMG:  Solving for p, Initial residual = 8.96200136703e-08, Final residual = 8.96200136703e-08, No Iterations 0
```

## medium

Case: `/Users/bhupeshcholake/Desktop/Claude Codes/physicore drone/.backend/demo-load-history/runs/1854860400c44eb38cb281724a654fb8`

```text
    cells:            251192
    Mesh non-orthogonality Max: 33.432419589 average: 4.10870864292
    Max skewness = 0.793522004581 OK.
Mesh OK.
smoothSolver:  Solving for Ux, Initial residual = 5.95973822878e-09, Final residual = 5.95973822878e-09, No Iterations 0
smoothSolver:  Solving for Uy, Initial residual = 1.24239469897e-07, Final residual = 6.91038654577e-09, No Iterations 1
smoothSolver:  Solving for Uz, Initial residual = 1.26559891504e-07, Final residual = 7.36583005567e-09, No Iterations 1
GAMG:  Solving for p, Initial residual = 9.33925482562e-08, Final residual = 9.33925482562e-08, No Iterations 0
```

## fine

Case: `/Users/bhupeshcholake/Desktop/Claude Codes/physicore drone/.backend/demo-load-history/runs/506e5b5f3e834f31a4441024d8e6a2cc`

```text
    cells:            804280
    Mesh non-orthogonality Max: 36.9379485766 average: 3.16065054011
    Max skewness = 0.675510541901 OK.
Mesh OK.
smoothSolver:  Solving for Ux, Initial residual = 9.54527764281e-09, Final residual = 9.54527764281e-09, No Iterations 0
smoothSolver:  Solving for Uy, Initial residual = 1.73052658558e-07, Final residual = 1.05370992865e-08, No Iterations 1
smoothSolver:  Solving for Uz, Initial residual = 1.71233496291e-07, Final residual = 1.05144917887e-08, No Iterations 1
GAMG:  Solving for p, Initial residual = 1.11957531918e-07, Final residual = 1.48927756899e-08, No Iterations 1
```
