# PHYSIMESH Hackathon — Autonomous Physics-Controlled CFD (H1)

**Branch:** `hackathon`  
**Status:** H1 decision/evidence foundations committed; autonomous CFD **not yet operational**.

## Goal
Given an explicitly unit-declared geometry and engineering operating regime, the system shall:
1. Inspect geometry, reject corrupt/invalid surfaces, and record original-byte identity.
2. Select physics only from validated, versioned supported adapters.
3. Propose physically and numerically suitable mesh candidates.
4. Execute pinned CFD solvers with bounded resources, persist logs and check mesh quality.
5. Automatically generate at least three systematically refined meshes and solve identical cases.
6. Quantify convergence for declared engineering quantities, check conservation, then use Richardson/GCI **only when applicable**.
7. Generate derived contours, numerical uncertainty plots and provenance-linked engineering reports.
8. Refuse qualification when inputs, solver convergence, physics validity, reproducibility or grid criteria are not met.

## H1 implemented
- `src/physimesh/drone/autonomous_cfd.py`: bounded STL parser + topology gate, restricted stationary-sphere eligibility and explicit unsupported rotor/airframe classification.
- `select_physics`: provisional Mach/Re admission for the existing v2606 incompressible steady sphere template; this does **not** validate its turbulence model or establish experimental accuracy.
- `propose_mesh_levels`: three bounded background-grid refinements. **Candidates only**, not meshed or solver-tested.
- `assess_grid_independence`: recorded coarse/medium/fine scalar data, actual cell counts, positive observed order, Richardson extrapolation and relative fine-grid GCI threshold. Rejects nonmonotone cases, failed solver/mesh/conservation gates, suspect refinement ratios and duplicate identities.
- `tests/drone/test_autonomous_cfd_hackathon.py`: focused source tests. CI result remains to be confirmed on GitHub.

## H1 important limitations
- Geometry identification is **declared-part and topology-driven**, not learned autonomous multi-part recognition.
- The gate is intentionally **restricted to an origin-centred, closed sphere**. It does not imply support for octocopter or rotating-rotor CFD.
- H1 does **not** generate OpenFOAM case files, launch OpenFOAM, record mesh statistics or produce contour plots.
- The GCI calculation assumes corresponding quantities on equal domains with equivalent physics/boundaries. It uses `h ∝ cells^(-1/3)` for 3D volume meshes; applicability and equal-domain provenance must be verified by the future orchestrator, not inferred from hashes alone.
- A three-grid GCI under tolerance is a *provisional numerical discretization screening*, not proof of overall solution accuracy; model-form, iterative, geometry, temporal and experimental uncertainty remain separate.
- No CFD source, mesh or result should be represented as aircraft flight qualification.

## H2: mesh and solver integration — next engineering task
Build a case adapter around existing `solver/openfoam_cases.py` and `solver/runner.py`:
- Bind explicit sphere STL bytes, SI length, airflow, density/viscosity and reference quantities to the supported template, without unreviewed defaults.
- Construct uniquely hashed coarse, medium, fine cases with frozen common physics and boundaries.
- Run each through bounded `blockMesh`, `snappyHexMesh`, `checkMesh` and `simpleFoam`.
- Extract final **measured** cell count, checkMesh statistics, residual trajectories, integral conservation and engineering result for every grid.
- Refuse failed cases and retain each solver log, input manifest and exact artifact hashes.

## H3: convergence-loop automation
- Compare identical engineering quantities (`Cd`, `Cl`, power, thrust or pressure-drop as applicable).
- Check solver and quantity time/iteration stability before analyzing grid sensitivity.
- For stationary 3D sphere, use three or more systematically refined meshes and report GCI only for admissible sequences.
- On failed GCI, produce an actionable refinement proposal within explicit compute budget; stop with `NOT_GRID_INDEPENDENT` if exhausted.
- Flag oscillatory/monotonicity failures and non-asymptotic ratios; no forced PASS.

## H4: drone extension
- Extend the physics registry only after obtaining qualified rotating/rotor–airframe flow models and benchmark evidence.
- Part roles/rotor axes/inlet-outlet regions need documented source-backed declarations or user confirmation.
- Add boundary-layer targets based on the chosen turbulence/wall model; y+ is measured after solution and corrected iteratively.
- Add multirotor wake interactions, possibly transient moving/overset/AMI meshes, model-specific CFL and time-step convergence.
- Extend to pressure/velocity/vorticity contours, streamlines, rotor force/torque and uncertainty-aware engineering recommendations.

## Release gates
1. CI unit and integration tests green on **hackathon**.
2. Independent pinned OpenFOAM sphere case reproducibly passes all setup and numerical checks.
3. Three meshes with matching frozen physics/conditions and recorded mesh quality.
4. At least one passing and one *deliberately failing* grid study shown end-to-end.
5. Scientific reviewer approves model eligibility and numerical criteria.
6. Physical aircraft validation remains an independent, separate requirement.
