# Task 1.4 backend audit: fixture verified, aircraft estimates pending

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
Local retained archive: `.backend/vendor/v2606/OpenFOAM-v2606.tgz`, also retained in the content-addressed evidence store.
This is an observed hash, not an independently authenticated vendor checksum.
Extracted tutorials: `.backend/vendor/v2606/tutorials`.
The vendor archive, case bundles and logs are retained locally under `.backend/evidence`; preserve these when transferring the project. [M§26]

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
The fixture was not retried until the user explicitly instructed continued work.

At that point, work stopped under plan §1.4: "The backend rejects a dictionary keyword, or a
capability fixture fails." No hardening flags were relaxed. Steps 4–8 were then
incomplete. No solver result, measured sizing, or backend-supported capability
is claimed. All dependent tasks were then pending.

## Diagnosis and verified recovery, 2026-10-02

The original stop above is retained as history. User authorization: continue
working and diagnose the reported failure. Direct Colima checks found the home
tree mounted through virtiofs, while the original macOS /private/var test path
was absent in the VM. A copy under the workspace was readable in the container.
This confirms a host/VM shared-path mismatch, not a rejected CFD dictionary.

The test now creates and cleans up its case under `.backend/tests` by default,
or `PHYSIMESH_BACKEND_WORK_ROOT` when explicitly configured. No hardening flag
changed. The original meshing regression was rerun:

```text
1 passed, 25 deselected in 0.84s
```

The source archive was retained under the shared workspace and verified against
the originally observed hash. Two serial 3D squareBend simpleFoam profiles also
completed exactly 20 iterations with 112000 and 896000 cells. Full input cases,
meshes, fields and logs are retained by hash. See compute_sizing.md for resource
measurements and limitations. This establishes the tested meshing and short
solver fixture only; it does not establish all future OpenFOAM capabilities or
Release A acceptance. [M§26, M§27]

The user confirmed real geometry and rotor data are unavailable, and explicitly
authorized continuing independent software tasks while leaving Task 1.4 Steps
6/7 pending. No aircraft sizing or effort estimate is invented. [M§28]

## Exact-release template discovery

Runtime tutorials are absent; these actual paths were discovered in the retained
v2606 vendor source archive. They are template candidates, not verified rotating
or transient capabilities. [M§26]

```text
IO/fileHandler_dynamicCode
basic/laplacianFoam/implicitAMI-nonblocking
basic/overLaplacianDyMFoam/heatTransfer/constant/dynamicMeshDict
basic/overLaplacianDyMFoam/heatTransferFluxConservation1D/constant/dynamicMeshDict
basic/overPotentialFoam/cylinder/cylinderAndBackground/constant/dynamicMeshDict
basic/simpleFoam/implicitAMI
combustion/PDRFoam/flamePropagationWithObstacles/constant/dynamicMeshDict
combustion/XiDyMFoam/annularCombustorTurbine/constant/dynamicMeshDict
combustion/XiDyMFoam/annularCombustorTurbine/system/createPatchDict.ami
combustion/XiDyMFoam/oscillatingCylinder/constant/dynamicMeshDict
combustion/reactingFoam/laminar
compressible/overRhoPimpleDyMFoam/twoSimpleRotors/constant/dynamicMeshDict
compressible/overRhoSimpleFoam/hotCylinder/cylinderAndBackground/constant/dynamicMeshDict
compressible/rhoCentralFoam/movingCone/constant/dynamicMeshDict
compressible/rhoPimpleFoam/RAS/annularThermalMixer/constant/dynamicMeshDict
compressible/rhoPimpleFoam/laminar
compressible/sonicDyMFoam/movingCone/constant/dynamicMeshDict
compressible/sonicFoam/laminar
compressible/sonicLiquidFoam/decompressionTank/constant/thermodynamicProperties
discreteMethods/molecularDynamics
heatTransfer/overBuoyantPimpleDyMFoam/movingBox/constant/dynamicMeshDict
heatTransfer/solidFoam/movingCone/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/sensitivityMaps/naca0012/laminar
incompressible/adjointOptimisationFoam/sensitivityMaps/sbend/laminar
incompressible/adjointOptimisationFoam/shapeOptimisation/fork-uneven/flowRate/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/fork-uneven/flowRatePartition/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/fork-uneven/uniformityPatch/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/motorBike/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/naca0012/kOmegaSST/lift/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/naca0012/laminar
incompressible/adjointOptimisationFoam/shapeOptimisation/naca0012/laminar/drag/primalAdjoint/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/naca0012/laminar/lift/opt/constraintProjection/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/naca0012/laminar/moment/primalAdjoint/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/naca0012/laminar/multipleConstraints/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/laminar
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/laminar/opt/constrained/SQP/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/laminar/opt/unconstrained/losses/BFGS-transformBox/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/laminar/opt/unconstrained/losses/BFGS/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/laminar/opt/unconstrained/losses/SD/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/laminar/opt/unconstrained/uniformityCellZone/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/laminar/primalAdjoint/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/turbulent/SA/opt/losses/BFGS-continuation/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/turbulent/SA/opt/losses/BFGS-oneGo/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/turbulent/SA/opt/losses/BFGS/multiPoint/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/turbulent/SA/opt/losses/BFGS/op1/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/turbulent/SA/opt/losses/BFGS/op2/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/turbulent/SA/opt/nutSqr/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/turbulent/SA/opt/powerDissipation/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/turbulent/SA/primalAdjoint/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/turbulent/SA/primalAdjointFullSetup/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/shapeOptimisation/sbend/turbulent/kOmegaSST/opt/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/topologyOptimisation/monoFluidAero/laminar
incompressible/adjointOptimisationFoam/topologyOptimisation/monoFluidAero/laminar/3DBox/losses-mass-uniformity-SQP-extraVars/reEval/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/topologyOptimisation/monoFluidAero/laminar/3DBox/losses-mass-uniformity-SQP/reEval/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/topologyOptimisation/monoFluidAero/laminar/3DBox/losses-mass-uniformity/reEval/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/topologyOptimisation/monoFluidAero/laminar/3DBox/losses-mass/reEval/constant/dynamicMeshDict
incompressible/adjointOptimisationFoam/topologyOptimisation/monoFluidAero/laminar/3DBox/losses/reEval/constant/dynamicMeshDict
incompressible/lumpedPointMotion/bridge/steady/constant/dynamicMeshDict
incompressible/lumpedPointMotion/building/steady/constant/dynamicMeshDict
incompressible/overPimpleDyMFoam/cylinder/cylinderAndBackground/constant/dynamicMeshDict
incompressible/overPimpleDyMFoam/rotatingSquare
incompressible/overPimpleDyMFoam/rotatingSquare/constant/dynamicMeshDict
incompressible/overPimpleDyMFoam/simpleRotor/constant/dynamicMeshDict
incompressible/overPimpleDyMFoam/twoSimpleRotors/constant/dynamicMeshDict
incompressible/overSimpleFoam/aeroFoil/background_overset/constant/dynamicMeshDict
incompressible/pimpleFoam/RAS/axialTurbine_rotating_oneBlade
incompressible/pimpleFoam/RAS/axialTurbine_rotating_oneBlade/constant/dynamicMeshDict
incompressible/pimpleFoam/RAS/axialTurbine_rotating_oneBlade/system/changeDictionaryDict_cyclicAMI
incompressible/pimpleFoam/RAS/oscillatingInletACMI2D/constant/dynamicMeshDict
incompressible/pimpleFoam/RAS/oscillatingInletPeriodicAMI2D
incompressible/pimpleFoam/RAS/oscillatingInletPeriodicAMI2D/constant/dynamicMeshDict
incompressible/pimpleFoam/RAS/propeller
incompressible/pimpleFoam/RAS/propeller/constant/dynamicMeshDict
incompressible/pimpleFoam/RAS/propeller/system/AMIWeights
incompressible/pimpleFoam/RAS/propeller/system/propellerInfo
incompressible/pimpleFoam/RAS/propeller1
incompressible/pimpleFoam/RAS/propeller1/constant/dynamicMeshDict
incompressible/pimpleFoam/RAS/rotatingFanInRoom
incompressible/pimpleFoam/RAS/rotatingFanInRoom/constant/dynamicMeshDict
incompressible/pimpleFoam/RAS/wingMotion/wingMotion2D_pimpleFoam/constant/dynamicMeshDict
incompressible/pimpleFoam/laminar
incompressible/pimpleFoam/laminar/contactAngleCavity/constant/dynamicMeshDict
incompressible/pimpleFoam/laminar/contaminatedDroplet2D
incompressible/pimpleFoam/laminar/contaminatedDroplet2D/constant/dynamicMeshDict
incompressible/pimpleFoam/laminar/mixerVesselAMI2D
incompressible/pimpleFoam/laminar/mixerVesselAMI2D/mixerVesselAMI2D
incompressible/pimpleFoam/laminar/mixerVesselAMI2D/mixerVesselAMI2D-topologyChange
incompressible/pimpleFoam/laminar/mixerVesselAMI2D/mixerVesselAMI2D-topologyChange/constant/dynamicMeshDict
incompressible/pimpleFoam/laminar/mixerVesselAMI2D/mixerVesselAMI2D/constant/dynamicMeshDict
incompressible/pimpleFoam/laminar/movingCone/constant/dynamicMeshDict
incompressible/pimpleFoam/laminar/sloshing2D/constant/dynamicMeshDict
incompressible/pisoFoam/laminar
incompressible/simpleFoam/rotatingCylinders
lagrangian/MPPICDyMFoam/column/constant/dynamicMeshDict
lagrangian/MPPICDyMFoam/denseRotor2DAMI
lagrangian/MPPICDyMFoam/denseRotor2DAMI/constant/dynamicMeshDict
lagrangian/icoUncoupledKinematicParcelDyMFoam/mixerVesselAMI2D
lagrangian/icoUncoupledKinematicParcelDyMFoam/mixerVesselAMI2D/constant/dynamicMeshDict
lagrangian/uncoupledKinematicParcelDyMFoam/rotor2DAMI
lagrangian/uncoupledKinematicParcelDyMFoam/rotor2DAMI/constant/dynamicMeshDict
mesh/blockMesh/pipe/constant/dynamicMeshDict
mesh/blockMesh/sphere7/constant/dynamicMeshDict
mesh/foamyHexMesh/mixerVessel/constant/dynamicMeshDict
mesh/moveDynamicMesh
mesh/moveDynamicMesh/SnakeRiverCanyon/constant/dynamicMeshDict
mesh/moveDynamicMesh/badMove/constant/dynamicMeshDict
mesh/moveDynamicMesh/bendJunction/constant/dynamicMeshDict
mesh/moveDynamicMesh/faceZoneBlock/constant/dynamicMeshDict
mesh/moveDynamicMesh/relativeMotion/box2D_moveDynamicMesh
mesh/moveDynamicMesh/relativeMotion/box2D_moveDynamicMesh/constant/dynamicMeshDict
mesh/moveDynamicMesh/rotorDisk_inclined/constant/dynamicMeshDict
mesh/moveDynamicMesh/twistingColumn/constant/dynamicMeshDict
mesh/polyDualMesh/missingCorner/constant/dynamicMeshDict
mesh/snappyHexMesh/rotated_block/constant/dynamicMeshDict
mesh/snappyHexMesh/sphere_multiRegion/constant/dynamicMeshDict
multiphase/cavitatingFoam/LES/throttle/constant/thermodynamicProperties
multiphase/cavitatingFoam/LES/throttle3D/constant/thermodynamicProperties
multiphase/cavitatingFoam/RAS/throttle/constant/thermodynamicProperties
multiphase/compressibleInterDyMFoam/laminar
multiphase/compressibleInterDyMFoam/laminar/sloshingTank2D/constant/dynamicMeshDict
multiphase/compressibleInterDyMFoam/laminar/sphereDrop/constant/dynamicMeshDict
multiphase/compressibleInterFoam/laminar
multiphase/compressibleInterIsoFoam/laminar
multiphase/compressibleMultiphaseInterFoam/laminar
multiphase/icoReactingMultiphaseInterFoam/mixerVesselAMI2D
multiphase/icoReactingMultiphaseInterFoam/mixerVesselAMI2D/constant/dynamicMeshDict
multiphase/interFoam/RAS/DTCHullMoving/constant/dynamicMeshDict
multiphase/interFoam/RAS/DTCHullMoving/constant/dynamicMeshDict.sixDoF
multiphase/interFoam/RAS/electrostaticDeposition/constant/dynamicMeshDict
multiphase/interFoam/RAS/floatingObject/constant/dynamicMeshDict
multiphase/interFoam/RAS/floatingObject/constant/dynamicMeshDict.sixDoF
multiphase/interFoam/RAS/mixerVesselAMI
multiphase/interFoam/RAS/mixerVesselAMI/constant/dynamicMeshDict
multiphase/interFoam/RAS/motorBike/constant/dynamicMeshDict
multiphase/interFoam/laminar
multiphase/interFoam/laminar/damBreakWithObstacle/constant/dynamicMeshDict
multiphase/interFoam/laminar/oscillatingBox/constant/dynamicMeshDict
multiphase/interFoam/laminar/sloshingCylinder/constant/dynamicMeshDict
multiphase/interFoam/laminar/sloshingTank2D/constant/dynamicMeshDict
multiphase/interFoam/laminar/sloshingTank2D3DoF/constant/dynamicMeshDict
multiphase/interFoam/laminar/sloshingTank3D/constant/dynamicMeshDict
multiphase/interFoam/laminar/sloshingTank3D3DoF/constant/dynamicMeshDict
multiphase/interFoam/laminar/sloshingTank3D6DoF/constant/dynamicMeshDict
multiphase/interFoam/laminar/testTubeMixer/constant/dynamicMeshDict
multiphase/interFoam/laminar/waves/waveMakerFlap/constant/dynamicMeshDict
multiphase/interFoam/laminar/waves/waveMakerMultiPaddleFlap/constant/dynamicMeshDict
multiphase/interFoam/laminar/waves/waveMakerMultiPaddlePiston/constant/dynamicMeshDict
multiphase/interFoam/laminar/waves/waveMakerPiston/constant/dynamicMeshDict
multiphase/interFoam/laminar/waves/waveMakerSolitary/constant/dynamicMeshDict
multiphase/interIsoFoam/damBreak/constant/dynamicMeshDict
multiphase/interIsoFoam/damBreakWithObstacle/constant/dynamicMeshDict
multiphase/interIsoFoam/discInConstantFlowCyclicBCs/constant/dynamicMeshDict
multiphase/interIsoFoam/sloshingTank2D/constant/dynamicMeshDict
multiphase/interIsoFoam/standingWave/constant/dynamicMeshDict
multiphase/interMixingFoam/laminar
multiphase/interPhaseChangeDyMFoam/propeller
multiphase/interPhaseChangeDyMFoam/propeller/constant/dynamicMeshDict
multiphase/multiphaseInterFoam/laminar
multiphase/overCompressibleInterDyMFoam/compressibleTwoSimpleRotors/constant/dynamicMeshDict
multiphase/overInterDyMFoam/floatingBody/background/constant/dynamicMeshDict
multiphase/overInterDyMFoam/floatingBodyWithSpring/background/constant/dynamicMeshDict
multiphase/overInterDyMFoam/rigidBodyHull/background/constant/dynamicMeshDict
multiphase/overInterDyMFoam/simpleRotor/constant/dynamicMeshDict
multiphase/overInterDyMFoam/twoSimpleRotors/constant/dynamicMeshDict
multiphase/overInterDyMFoam/twoSquaresOutDomain/constant/dynamicMeshDict
multiphase/overInterPhaseChangeDyMFoam/twoSimpleRotors/constant/dynamicMeshDict
multiphase/potentialFreeSurfaceDyMFoam/oscillatingBox/constant/dynamicMeshDict
multiphase/reactingMultiphaseEulerFoam/laminar
multiphase/reactingTwoPhaseEulerFoam/laminar
multiphase/reactingTwoPhaseEulerFoam/laminar/steamInjection
multiphase/twoPhaseEulerFoam/laminar
preProcessing/PDRsetFields/simplePipeCage/constant/dynamicMeshDict
resources/geometry/annularCombustorTurbine/ami.obj.gz
resources/geometry/annularThermalMixer/AMI.obj.gz
resources/geometry/faceZoneRegions/rotatingZone.obj.gz
resources/geometry/mixerVesselAMI
resources/geometry/mixerVesselAMI/rotating.stl.gz
resources/geometry/mixerVesselAMI/shaftRotating.stl.gz
resources/geometry/propeller
resources/geometry/propeller/propellerStem1.obj.gz
resources/geometry/propeller/propellerStem2.obj.gz
resources/geometry/propeller/propellerStem3.obj.gz
resources/geometry/propeller/propellerTip.obj.gz
resources/geometry/propeller1
resources/geometry/propeller1/propeller.obj.gz
resources/geometry/rotatingFanInRoom
resources/geometry/rotatingFanInRoom/AMI.stl.gz
resources/geometry/rotorDisk/rotatingZone.obj.gz
```
