# Task 1.4 backend audit: incomplete

Date: 2026-10-02. Distribution/release: OpenCFD v2606, explicitly confirmed
by the workspace user. No CFD capability or release gate is approved. [plan Q02]

## Retained pin and sources

Vendor tag: `opencfd/openfoam-run:2606`.
Immutable reference returned by Docker inspect:
`opencfd/openfoam-run@sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb`.
Local architecture: arm64. Docker engine: 29.5.2. Context: colima,
endpoint `unix:///Users/bhupeshcholake/.colima/default/docker.sock`.

Primary sources:
- https://hub.docker.com/r/opencfd/openfoam-run/tags
- https://www.openfoam.com/news/main-news/openfoam-v2606
- https://dl.openfoam.com/source/v2606/

Downloaded exact-release source archive:
`https://dl.openfoam.com/source/v2606/OpenFOAM-v2606.tgz`.
Observed SHA-256: `2a1310e3ed192cc4c521e1d22dcc176f57bec61160c878dc4348f21d6672294d`.
Local retained archive: `/tmp/physicore-v2606-audit/OpenFOAM-v2606.tgz`.
This is an observed hash, not an independently authenticated vendor checksum.
Extracted tutorials: `/tmp/physicore-v2606-audit/OpenFOAM-v2606/tutorials`.
Temporary retention must be copied to permanent evidence storage before reuse
on another machine. [ASSUMPTION]

## Probe output

The container was probed with no network, read-only root, all capabilities
dropped, 512 PIDs, two CPU cores, 4g memory, and writable /tmp. [ASSUMPTION:
fixture budgets, not aircraft inputs]

```text
v2606
/usr/lib/openfoam/openfoam2606/tutorials
/usr/lib/openfoam/openfoam2606/platforms/linuxARM64GccDPInt32Opt/bin
checkMesh
foamToVTK
foamToVTKHDF
pimpleFoam
simpleFoam
snappyHexMesh
find: '/usr/lib/openfoam/openfoam2606/tutorials': No such file or directory
```

The runtime image does not contain its configured tutorial tree. A query of
`opencfd/openfoam-dev:2606` returned:

```text
Error response from daemon: failed to resolve reference "docker.io/opencfd/openfoam-dev:2606": docker.io/opencfd/openfoam-dev:2606: not found
```

No older release substituted. The vendor source archive provides the inspected
`incompressible/simpleFoam/squareBend` tutorial. Its own blockMeshDict defines
three-dimensional blocks; case dictionaries were copied unchanged for meshing.
The vendor entrypoint changes directory to HOME, so the test explicitly runs
`cd /case` before invoking the mesh utilities. Presence of executables is not
capability evidence. [M§26]

## Failed hardened fixture and required stop

Command:

```sh
PHYSIMESH_OPENFOAM_TUTORIALS=/tmp/physicore-v2606-audit/OpenFOAM-v2606/tutorials .venv/bin/python -m pytest -q -m backend
```

Literal failure excerpts:

```text
Build  : _481094f-20260618 OPENFOAM=2606 version=2606
Exec   : blockMesh
Case   : /case
nProcs : 1
--> FOAM FATAL ERROR: (openfoam-2606)
cannot find file "/case/system/controlDict"
FAILED tests/backend/test_container_smoke.py::test_v2606_tutorial_mesh_in_hardened_container
1 failed, 25 deselected in 0.43s
```

Read-only host check confirms the copied controlDict exists at:
`/private/var/folders/fw/7f21wrbj7xnf7w919ljdj4r40000gn/T/pytest-of-bhupeshcholake/pytest-17/test_v2606_tutorial_mesh_in_ha0/case/system/controlDict`.
This establishes a difference between host file presence and container access;
it does not establish the cause. Investigate Colima bind-mount visibility and
file-sharing configuration before retrying. [ASSUMPTION: diagnostic next step]

The pending test's banner assertion was corrected to the observed
`version=2606`; `WM_PROJECT_VERSION` prints `v2606` separately. This is a test
harness correction, not an engineering expected value or supplied plan fixture.
The backend fixture was not retried after the stop.

Work stopped under plan §1.4: "The backend rejects a dictionary keyword, or a
capability fixture fails." No hardening flags were relaxed. Steps 4–8 remain
incomplete. No solver result, measured sizing, or backend-supported capability
is claimed. All dependent tasks remain pending.
