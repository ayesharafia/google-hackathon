# Compute sizing: measured tutorial profiles, aircraft estimates pending

2026-10-02. Task 1.4 Step 5 development measurements; Steps 6/7 remain blocked by real geometry and rotor data (Q03/Q04). [M§28]

## Method and limits

Exact v2606 vendor `incompressible/simpleFoam/squareBend` dictionaries and physical inputs were retained. Original mesh count parameters were multiplied by 1 or 2 in all three directions. Both meshes passed `checkMesh` with three geometric and solution directions. [retained backend logs]

Each run used an explicit 20-iteration profiling window (`endTime` changed from 500 to 20), serial simpleFoam, a two-core CPU limit, 4 GiB memory limit and the Task 1.2 hardened runner. This is a recorded development fixture choice [ASSUMPTION], not a converged tutorial result, mesh-sensitivity assessment or aircraft CFD result.

Peak memory comes from Linux cgroup v2 `memory.peak`, measured at solver completion in a fresh container. It includes the whole container, charged file cache and process overhead; it is **not solver RSS**. Host wall time includes container startup and teardown. Solver-reported ClockTime is rounded. The tests do not establish parallel scaling or long-run resource demand.

## Actual measurements

| Resolution | Cells | Iterations | Peak container bytes | Host elapsed seconds | Solver ClockTime seconds | Retained case bytes |
|---|---:|---:|---:|---:|---:|---:|
| 1x | 112000 | 20 | 220200960 | 3.187438 | 3.0 | 13173626 |
| 2x | 896000 | 20 | 1487839232 | 21.906142 | 22.0 | 102538942 |

Both cell counts differ by exactly 8, as expected for a 2x count increase along each of three directions. This verifies the fixture refinement, not convergence.

## Normalized measurements and preliminary fit

For each measured run, normalize memory as peak_bytes / (cells / 1e6), and host time as elapsed_s / ((cells / 1e6) * iterations). These are profiling definitions [ASSUMPTION], not physical equations.
- 1x: 1966080000.000 bytes per million cells; 1.422963 seconds per million cells per iteration.
- 2x: 1660534857.143 bytes per million cells; 1.222441 seconds per million cells per iteration.

Two-point descriptive memory fit: M(N) = 39109778.286 + 1616.885551 N bytes. Two-point host-time fit per iteration: t(N) = 0.025666879 + 0.000001193795 N seconds. [ASSUMPTION: affine profiling model, valid only as a description of these two observations]

Two observations cannot establish scaling uncertainty or justify extrapolation to actuator sources, rotating interfaces or transient fields. They have no statistical redundancy. No aircraft estimate is supplied.

## Reproduction

Runtime artifacts are retained under `.backend/evidence` as content-addressed write-once objects. They are local evidence, excluded from Git. Preserve this directory when transferring or archiving the project. The full case bundles retain meshes and native fields in addition to logs. [M§26]

Run the meshing regression:

```sh
PHYSIMESH_OPENFOAM_TUTORIALS='.backend/vendor/v2606/tutorials' .venv/bin/python -m pytest -q -m backend
```

Run both profiling cases:

```python
from pathlib import Path
from tests.backend.test_container_smoke import profile_tutorial
root = Path(".backend").resolve()
for factor in (1, 2):
    profile_tutorial(root / "vendor/v2606/tutorials", root / "profiles", factor)
```

Vendor source archive SHA-256: `2a1310e3ed192cc4c521e1d22dcc176f57bec61160c878dc4348f21d6672294d`. The archive is retained in the artifact store as well as `.backend/vendor/v2606`; the hash is observed, not independently vendor-authenticated.

## Evidence attachments

### 1x resolution

- [Full retained case (.tar.gz)](../../.backend/evidence/objects/c5/c510a0da04a46f2dcdbf0eed139f4cc1f5948bdec924d3025577479c14210823): `c510a0da04a46f2dcdbf0eed139f4cc1f5948bdec924d3025577479c14210823`
- [Profile record](../../.backend/evidence/objects/ae/ae843877749a574455b5deddd7dfaa164c8f9ebb6bbb75a77f3c0cd38df414c4): `ae843877749a574455b5deddd7dfaa164c8f9ebb6bbb75a77f3c0cd38df414c4`
- [mesh.log](../../.backend/evidence/objects/9c/9c6f1c791140912c344cfa8a18a4f3e164607691689702e59abfa7e2e19dd02f): `9c6f1c791140912c344cfa8a18a4f3e164607691689702e59abfa7e2e19dd02f`
- [solver.log](../../.backend/evidence/objects/b2/b24e4234204769bbcc4154959808895ae69250554ec4984bfb56fdddd317950e): `b24e4234204769bbcc4154959808895ae69250554ec4984bfb56fdddd317950e`

### 2x resolution

- [Full retained case (.tar.gz)](../../.backend/evidence/objects/eb/eb614776a302ad1e8ba183d621f03ce9176b63c7adba8fef155ea7c1b0fe47c8): `eb614776a302ad1e8ba183d621f03ce9176b63c7adba8fef155ea7c1b0fe47c8`
- [Profile record](../../.backend/evidence/objects/ea/ea3cddb90ccdd5471bcc3fc772eec9ecc7933422ac34ffa6947a2f83be256b76): `ea3cddb90ccdd5471bcc3fc772eec9ecc7933422ac34ffa6947a2f83be256b76`
- [mesh.log](../../.backend/evidence/objects/92/925253577eccb7f3213239b0f458db303ae33ddbbfe9b2b1cb55c399c2e8929b): `925253577eccb7f3213239b0f458db303ae33ddbbfe9b2b1cb55c399c2e8929b`
- [solver.log](../../.backend/evidence/objects/98/987d0bf11083c756be86fe9247ed8096b2f46a11ec2d61c43c69424bb9b3ec84): `987d0bf11083c756be86fe9247ed8096b2f46a11ec2d61c43c69424bb9b3ec84`

## BLOCKED / QUESTIONS

Aircraft actuator and transient cell counts require real STL geometry. Effort estimates require the first real STL and rotor review. The user confirmed these inputs are not available. Steps 6/7 remain pending under plan §1.4. The 4 vCPU / 16 GB / 50 GB legacy host profile is not an accepted 3D capacity; Release C compute approval remains Q12. [M§28]
