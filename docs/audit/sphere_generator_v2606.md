# Sphere generator backend smoke

The vendor-derived generator produced a sphere case under the pinned OpenCFD
v2606 image. The retained case is `.backend/runs/sphere-generator-smoke`.
All dictionaries identify their source tutorial and original SHA-256; the
mapping is retained in `openfoam_templates/v2606/external_steady/SOURCES.json`.

The origin-centred sphere has diameter 1 m, speed 1 m/s and kinematic viscosity
0.01 m²/s, giving Re = 100. The caller supplies and verifies that sphere STL.
The generator supports this verification case family only.

`blockMesh`, `snappyHexMesh -overwrite`, `checkMesh` and 20 `simpleFoam`
iterations exited successfully in the hardened container.

Literal `checkMesh.log` evidence:

```text
    cells:            80473
    Mesh non-orthogonality Max: 30.5321172997 average: 5.2938067045
    Max skewness = 0.831949805147 OK.
Mesh OK.
```

The solver completed `Time = 20` and wrote native pressure, wall shear,
vorticity and sampled outputs. This establishes dictionary compatibility and
pipeline execution only. Twenty iterations do not establish convergence or
drag accuracy. Normal-sign and native-force reconciliation remain separate
checks.

The first MVP mesh uses surface refinement without added prism layers. The
retained motorBike defaults provide snapping/quality controls; layer addition
is explicitly disabled. The mesh study must assess the resulting drag.
