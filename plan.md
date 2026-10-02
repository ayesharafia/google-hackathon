# PhysiCore Drone Module — Implementation Plan

> **For agentic workers (GPT, Claude, Codex or any other model):** read §0 and §1 in full before touching any task. Work one task at a time, in the order given in §9. Each task's steps use checkboxes (`- [ ]`). If a step depends on something marked `[VERIFY-IN-BACKEND]`, `[OPEN-QUESTION]` or `null`, **stop and report**. Do not guess.

**Goal:** Build a 3D drone analysis module on top of the existing PhysiMesh platform. It imports STL assemblies, checks geometry and symmetry, predicts and verifies rotor thrust, torque and power plus whole-vehicle aerodynamic loads using a pinned OpenFOAM backend, and produces reproducible, honestly labelled engineering evidence for a multirotor that must carry a **750 kg payload**.

**Architecture:** A new repository whose `src/physimesh/core/` holds the platform services (artifacts, jobs, hardened containers) and whose `src/physimesh/drone/` domain package holds schema, units, geometry, symmetry, mass, atmosphere, propulsion, meshing, trim and mission logic. It sits on top of solver services that do not care about aircraft type (`solver/`, extended with 3D, rotation and source capabilities) and a postprocessing layer (`postpro/`) that integrates loads from native solver face data and chooses plots with deterministic rules. OpenFOAM computes the flow. PhysiMesh orchestrates, checks, reconciles and reports. No number reaches a report unless it traces back to an analytical calculation, a measured source or a retained solver run.

**Build mode:** **greenfield**: a new repository built from scratch (decision 2026-10-02, §2.1). The flow equations are still solved by an established CFD engine, as the manifest requires [M§0].

**Tech stack (decided, §6.0):** Python 3.11, NumPy/SciPy, PyYAML, FastAPI + uvicorn, SQLite job ledger + content-addressed filesystem store, Docker, pytest + ruff, OpenFOAM (one pinned OpenCFD release, recommended **v2606** because it is the documentation release the manifest cites in R1) run in a container pinned by image digest, ParaView/pvpython for rendered evidence (manifest R8), and a plain HTML/JS browser UI with a three.js 3D viewer. The existing 2D PhysiMesh product (SU2) is **not modified** by this repository (§2.5).

**Spec:** `docs/source/PhysiCore_Drone_Detailed_Project_Manifest.docx` (v1.0, 1 Oct 2026), with a machine-extracted copy at `docs/source/manifest_v1.0_extracted.md`. Citations such as **[M§12]** mean "manifest section 12". **If this plan and the manifest disagree, the manifest wins.** Record the conflict in §14 (Open Questions).

---

## Table of contents

- §0 Read-me-first: the anti-hallucination protocol for every model
- §1 How to run a task with an LLM (prompt template, definition of done, stop conditions)
- §2 What exists today and what is new
- §3 Global constraints (copied verbatim from the manifest)
- §4 Status vocabularies (exact enum strings)
- §5 Review focus (failure modes most likely to bite)
- §6 Architecture, package layout and data flow
- §7 Equation catalogue E01–E56 (with owning module and test)
- §8 Settings registers (manifest §31–§32)
- §9 Release roadmap and work-package order
- §10 Work packages WP01–WP12 broken into tasks
- §11 Validation campaigns and acceptance fixtures
- §12 Risk register
- §13 Client communication: allowed and blocked claims, report template
- §14 Open questions and required external inputs
- §15 Traceability matrix (REQ01–REQ12 → tasks → evidence)
- Appendix A: Draft project YAML (`drone_manifest_v1`)
- Appendix B: Role prompts (physics, numerical, geometry, software, critic)
- Appendix C: Glossary

---

## §0 Read-me-first: anti-hallucination protocol

This project goes to a client. A plausible-looking number that is wrong does more damage than a missing one. Every model working on it **must** follow these rules. The manifest backs each one ([M§28], [M§29], [M§31]).

### 0.1 Source tags. Every non-trivial statement you write carries one.

| Tag | Meaning | Example |
|---|---|---|
| `[M§n]` | Stated in manifest section *n* | "Payload is 750 kg [M§4]" |
| `[M-En]` | Manifest equation *n* (transcribed in §7) | "Shaft power P = −M·Ω [M-E43]" |
| `[LEGACY-PHYSIMESH]` | Concerns the separate existing 2D PhysiMesh product, whose source was never available. Only matters for the later integration step (§2.5) | "Load-case export format must match `[LEGACY-PHYSIMESH]`" |
| `[VERIFY-IN-BACKEND]` | Depends on exact OpenFOAM release syntax or behaviour; must be confirmed by a capability fixture run | "`forces` function object keyword `CofR` `[VERIFY-IN-BACKEND]`" |
| `[ASSUMPTION]` | A development choice this plan makes; the client or lead engineer may overturn it | "Use pytest `[ASSUMPTION]`" |
| `[OPEN-QUESTION]` | Unknown; blocks the dependent step until answered (listed in §14) | "Rotor count `[OPEN-QUESTION]`" |
| `[STD]` | A standard physical constant or textbook definition, value given exactly | "g₀ = 9.80665 m/s² `[STD]`" |

### 0.2 Hard rules (breaking any of these means the work is rejected)

1. **Never invent a design value.** Total mass, rotor count, radius, RPM, pitch, atmosphere, motor limits and battery data are `null` until the client supplies them [M§4], [M§31]. A `null` blocks the run or decision that needs it. It is never replaced by a "typical" value.
2. **Never invent a thrust, torque, power or force number.** "No role may create a thrust number that lacks an analytical calculation, measured source or retained run" [M§28]. Numbers in tests are either analytical (derived in the test from first principles) or come from the verified fixture values in this plan (§7.3), which were computed with code while the plan was written.
3. **Never invent API names in existing code.** Before calling or editing anything in `src/physimesh/` that this plan did not create, open the file and confirm the name and signature. If it differs from the plan, follow the code and add a note to §14.
4. **Never invent OpenFOAM syntax.** Dictionary keywords, boundary-condition names and function-object options must come from the pinned release's own tutorials or `foamGet`/`foamInfo` output, checked by a capability fixture [M§14], [M§26]. A plan snippet tagged `[VERIFY-IN-BACKEND]` is a starting point, not truth.
5. **Never fake a missing field.** If a plot or output cannot be derived, return the exact missing dependency and the next action [M§23]. Never substitute an unrelated plot, a smoothed field or an AI-generated image.
6. **Never upgrade a status.** A completed CFD job is not a feasibility status [M§2]. A pretty plot is not validation [M§24]. Status changes only through the gate functions in this plan.
7. **Never silently change a setting.** Every relaxation, tolerance or fidelity change is versioned and recorded [M§14]. Resource limits may *recommend* a cheaper screening run but may not *downgrade* an accepted design decision [M§7].
8. **Units are SI internally.** Store the original declared unit and each conversion [M§3]. A source unit is never inferred from file contents [M§11].
9. **Do not claim "zero hallucination" to the client.** The manifest explicitly blocks that claim [M§29]. What we *can* say is that every number traces back to its source and that deterministic gates check units, schemas, capabilities and provenance [M§28].
10. **Leave the existing 2D product alone.** This repository never edits legacy PhysiMesh code. Integration happens only through the export interface in §2.5 (REQ11, adapted).

### 0.3 When unsure

Stop. Write a short note at the end of your output under the heading `BLOCKED / QUESTIONS` that lists what you need and why. A clear question is a successful outcome. A guessed answer is a failed one.

---

## §1 How to run a task with an LLM

### 1.1 Context to paste into every task session

1. This file's §0, §3 and §4 (always).
2. The single task block from §10 you are executing.
3. The equations from §7 that the task cites.
4. The relevant manifest section(s) from `docs/source/manifest_v1.0_extracted.md`.
5. The **actual current contents** of every existing file the task modifies. Never rely on the plan's description of an existing file.

### 1.2 Task prompt template (copy, fill in, send)

```text
You are implementing one task of the PhysiCore Drone module.
Rules: follow plan.md §0 (anti-hallucination protocol) exactly.

TASK: <paste the task block, e.g. "Task 3.2 Binary/ASCII STL parser">
EQUATIONS: <paste cited equations from plan.md §7>
MANIFEST EXCERPT: <paste cited manifest sections>
CURRENT FILES: <paste current content of files to modify, or "new files only">

Deliver, in this order:
1. The failing tests exactly as specified (you may add tests, never remove them).
2. The implementation.
3. The command you ran and its literal output (pass/fail).
4. A "SOURCES" list tagging every constant and formula you used ([M§n], [M-En], [STD], [ASSUMPTION]).
5. A "BLOCKED / QUESTIONS" list (write "none" if empty).
Do not modify files outside the task's Files list. Do not invent values for null inputs.
```

### 1.3 Definition of done (every task)

- [ ] All tests in the task block exist and pass, with **real command output pasted**, not described.
- [ ] The full suite passes: `python -m pytest -q -m "not backend"` (plus `-m backend` for tasks that touch OpenFOAM), and `ruff check .` is clean.
- [ ] No new constant without a source tag.
- [ ] No `null` input replaced by a default.
- [ ] New public functions have type hints and docstrings that state units.
- [ ] Commit made with the message given in the task.
- [ ] A **second model or a human** has reviewed the diff using the Critic prompt (Appendix B.5). For tasks marked ⚠ *physics-critical*, this review is mandatory before merge.

### 1.4 Stop conditions (abort the task and report)

- A test the plan supplies fails for a reason that looks like an error *in the plan* (e.g. an analytical value seems wrong). Report it. Do not "fix" the expected value until a human checks the derivation.
- Existing code contradicts the plan's assumed interface.
- The backend rejects a dictionary keyword, or a capability fixture fails.
- You would need a value that is `null` or `[OPEN-QUESTION]`.

### 1.5 Model-assignment recommendation `[ASSUMPTION]`

| Work type | Primary model | Required second check |
|---|---|---|
| Schema, parsers, API plumbing, UI | GPT (primary) | Automated tests + critic review |
| ⚠ Physics-critical (§7 equations, force integration, BEM, symmetry transforms, trim, pressure semantics) | GPT (primary) | A **different** model family or a human engineer re-derives the test expectations independently |
| OpenFOAM case generation | GPT (primary) | Must pass a real backend capability fixture; model review is not enough |
| Final client report wording | Any | Human sign-off against §13 |

The reason for cross-model review: two runs of the same model tend to make the same mistake. The manifest's critic role exists to "challenge evidence and unsupported claims" [M§28].

---

## §2 What exists today and what is new

### 2.1 Baseline, as stated by the manifest [M§1]

The manifest describes the current PhysiMesh platform (from the separate "PhysiMesh Complete Project Documentation", repository reference dated 29 Sep 2026 [M§30]) as having:

- a steady 2D scalar research solver;
- a guided 2D aerodynamic workflow through an external SU2 adapter;
- aerodynamic geometry that is a closed profile or polyline, with mesh generation, reference area and force integrals all in 2D conventions.

**Not established today:** 3D STL healing, 3D volume meshing, rotating assemblies and GPU execution [M§1].

> **Build decision (2026-10-02): greenfield.** The PhysiMesh source repository was not available. The three related files in the user's Downloads folder were inspected:
> - `physimesh_aero.zip` is an **exported 2D SU2 case** (NACA 0012, `project.json`, `config.cfg`, mesh, readiness report), i.e. output of the existing app, not its source.
> - `physicore.zip` is a separate **from-scratch 2D C++ incompressible solver prototype** (MAC grid, Chorin projection, checked against Ghia 1982 and Poiseuille). It is not suitable as the 3D rotor solver; see §2.6.
> - `PhysiMesh_Technical_Architecture_and_Resource_Requirements.pdf` (26 Sep 2026) describes the existing stack: Python + built-in HTTP server, HTML/CSS/JS, NumPy, PyYAML, Gmsh, SU2 8.5.0 in Docker, SQLite + filesystem, ReportLab/Pillow, and a 4 vCPU / 16 GB / 50 GB server profile for **2D** work.
>
> The user therefore chose to build the drone module **from scratch** in a new repository. This **deviates** from the manifest's "Extend the existing PhysiMesh orchestration and reporting services" [M§0]. The deviation must be confirmed with the client (§14 Q01). To keep a later merge cheap, the new repository reuses the same language, the same package name (`physimesh`), the same proposed paths [M§25] and the same platform patterns (SQLite ledger, filesystem evidence, locked-down Docker solver).

### 2.2 Reuse map [M§1] (now a design reference, not code reuse)

In greenfield mode the left column describes ideas to copy, not code to import. Every row's right column is built new in this repository.

| Existing area | Reuse | New development required |
|---|---|---|
| aero models and service | Request validation, workflow structure | New 3D assembly and operating-condition models |
| 2D geometry and Gmsh workflow | Quality-reporting concepts | STL preparation and 3D mesh adapter |
| solver contracts and run service | Job lifecycle, artifacts, diagnostics | Rotor capabilities and a version-pinned backend |
| 2D force reconstruction | Provenance and sign-testing patterns | 3D surface integrals and moments |
| analysis sessions and campaigns | Saved recipes and comparisons | Volume, surface, rotor-phase and time statistics |
| browser raster worker | Some UI conventions | 3D viewer, clipping, vector display |
| scalar adaptation engine | Research verification examples | **No direct reuse** as a rotor Navier–Stokes solver |

### 2.3 Scope exclusions for the first program [M§1]

No automatic CAD shape optimisation from STL. No full-aircraft aeroelastic coupling. No battery chemistry solver. No acoustic certification. No flight-controller deployment. No guarantee of flight compliance. **No GPU acceleration claim** [M§14]. Each of these gets an extension interface (aerodynamic load-case export and propulsion-map export) and nothing more.

### 2.4 First configuration [M§0]

A **multirotor**. Coaxial rotors, tiltrotors and lift-plus-cruise layouts need extra cases and capability checks. They are out of scope until a capability exists for them.

### 2.5 Integration with the existing 2D PhysiMesh product

The manifest wants aerodynamic load cases and propulsion maps exported "so the rest of the engineering program can use them" [M§1]. That export is also the integration seam with the existing product:

- `GET /api/drone/runs/{id}/export` returns a ZIP with `load_cases.json` (force ledger per case, origin, frame, units, status, provenance), `propulsion_map.json` (rotor map with its convention metadata, Task 6.2), the plot recipes and the hashes.
- A later merge into the legacy repository moves `src/physimesh/drone`, `postpro` and `solver/openfoam.py` across. The `core/` services map onto the legacy job and artifact modules `[LEGACY-PHYSIMESH]`.
- The 2D SU2 workflow keeps running in the legacy product, untouched (REQ11).

### 2.6 Why we do not write our own 3D flow solver

"Build from scratch" applies to the **application**: geometry, meshing control, orchestration, loads, statistics, plots, trim, mission and reports. It does **not** apply to the Navier–Stokes solver, for three reasons:
1. The manifest says to "use an established CFD backend for the flow equations" and puts a home-made turbulence closure out of scope [M§0], [M§9].
2. A 3D, turbulent, rotating-mesh solver that a client could trust needs years of verification. OpenFOAM brings that history.
3. The `physicore` prototype is 2D, laminar, uniform-grid and non-rotating. It is a good teaching and verification artefact, but extending it to blade-resolved 3D RANS would be a new research project with no validation evidence for this client.

---

## §3 Global constraints (verbatim values from the manifest)

Every task implicitly includes this section.

| # | Constraint | Value / rule | Source |
|---|---|---|---|
| G01 | Payload | **750 kg of carried payload**, not total mass | [M§0], REQ01 |
| G02 | Total mass | `m_TO = 750 + m_structure + m_propulsion + m_energy + m_avionics + m_other` | [M-E01] |
| G03 | Internal units | SI. Original declaration plus every conversion stored | [M§3] |
| G04 | World frame | Right-handed ENU: x, y horizontal, **z up**; gravity = (0, 0, −g) | [M§3] |
| G05 | Body frame default | Right-handed: **x forward, y left, z up** | [M§3] |
| G06 | Rotor frame | Unit thrust axis aᵢ, centre xᵢ, signed angular velocity; +RPM follows the right-hand rule about aᵢ; azimuth zero and phase offsets mandatory for blade-resolved transients | [M§3] |
| G07 | Force sign | Reported aerodynamic forces act **on the aircraft**. Body normal points **out of the solid into the fluid** | [M§3] |
| G08 | Moments | Always tied to a stated origin | [M§3] |
| G09 | Gas constant | R_air = **287.05 J/(kg·K)**; γ ≈ 1.4 only where the ideal-gas approximation is appropriate | [M§4] |
| G10 | Atmosphere | Absolute pressure and Kelvin. Altitude and pressure must not be combined inconsistently | [M§4] |
| G11 | Unknowns | `null` blocks execution. Never substitute a guess | [M§0], [M§26] |
| G12 | Schema version | `drone_manifest_v1`; changes only through explicit migration | [M§31] |
| G13 | Symmetry execution | **Off** until eligible and compared against a full domain | [M§31] |
| G14 | Compute | Local workstation / CPU parallel. **No GPU claim** | [M§14] |
| G15 | Backend | One pinned OpenFOAM distribution and release for the first 3D rotor workflow. SU2 kept for its existing cases | [M§1] |
| G16 | Paths | All new code under `src/physimesh/` at the paths in §6.2 | [M§25] |
| G17 | 2D preservation | The existing 2D force APIs keep their per-unit-span behaviour | [M§25] |
| G18 | Reproducibility | Hashes of input, geometry, mesh, backend and recipe on every result | REQ10 |
| G19 | No hidden mutation | Relaxation and solver-setting changes are versioned; no automatic hidden changes | [M§14] |
| G20 | Provisional gates | Mesh/time change < 2 %, symmetry < 1 %, experimental targets e.g. 5 % thrust / 10 % torque. These are **targets, not achieved accuracy** | [M§15] |
| G21 | Standard gravity | g₀ = 9.80665 m/s² `[STD]`. This is consistent with the manifest's 7,354.99 N for 750 kg [M§4] | [STD] |

---

## §4 Status vocabularies (use these exact strings)

### 4.1 Aircraft study status [M§2]

`inputs_incomplete` · `screening_only` · `numerically_unverified` · `validation_pending` · `within_validated_envelope` · `requirement_not_met`

Rules:
- Missing required input → `inputs_incomplete`. Nothing else is possible.
- Only measured-map or BEM screening done → at most `screening_only`.
- CFD run completed but no mesh or time assessment → at most `numerically_unverified`.
- Mesh and time assessed, no comparison against measurement → at most `validation_pending`.
- `within_validated_envelope` requires a validation campaign (§11) covering that case family.
- `requirement_not_met` may be assigned at **any** fidelity once a requirement (thrust, power, energy, control) is shown to fail. The trim and mission code sets it.

### 4.2 Execution state [M§15]

`queued` · `preparing` · `meshing` · `running` · `postprocessing` · `completed` · `cancelled` · `failed`

### 4.3 Engineering evidence level [M§15]

`unverified` · `iteration_converged` · `periodic_or_statistical_converged` · `mesh_assessed` · `time_assessed` · `validated_for_case_family`

### 4.4 Release status

Software release status (Release A–D gates, §9) is tracked **separately** from each aircraft study's status. Passing a software release does not validate any customer model [M§2].

### 4.5 Fidelity levels [M§7]

`measured_map` · `bem` · `actuator_disk` · `actuator_line` · `steady_rotating_frame` · `transient_mesh`

---

## §5 Review focus (failure modes most likely to bite)

Each line below names an input or condition the manifest implies and the behaviour a reasonable person expects. The owning task contains a test that pins it.

1. **Kinematic pressure multiplied by density twice, or not at all.** OpenFOAM incompressible solvers store `p` in m²/s². Physical force must use ρ·p_k exactly once, and already-dimensional Pa must never be multiplied again [M§16], CT04. → Task 5.2 test `test_kinematic_pressure_converted_once`.
2. **A binary STL whose 80-byte header starts with `solid`.** It must still be parsed as binary [M§11]. → Task 3.1 test `test_binary_starting_with_solid_is_binary`.
3. **Mirror symmetry offered for a single swirling rotor, or for crosswind, yaw, asymmetric RPM, displaced payload or motor loss.** It must be rejected [M§12]. → Task 8.2 tests `test_reject_*`.
4. **Freestream Cp requested in hover (U_ref = 0).** It must be rejected, with dimensional pressure offered instead [M§19], CT03. → Task 9.2 test `test_ct03_cp_rejected_at_zero_reference`.
5. **Peak (or best-case) thrust used to justify continuous hover, or numbers mixed from different cases.** Margins must use sustained limits at the same density and electrical state, and the report must never combine best thrust from one case with best efficiency from another [M§5], [M§17]. → Task 12.3 test `test_margin_uses_sustained_limit_same_case`.

---

## §6 Architecture, package layout and data flow

### 6.0 Technology decisions (greenfield)

| Concern | Decision | Why |
|---|---|---|
| Language | Python 3.11 (exact versions frozen in `requirements.lock`) | Same as existing PhysiMesh; the reference code is Python |
| Numerics | NumPy, SciPy | Reference implementation already uses them |
| Config | PyYAML `safe_load` only | Same as existing PhysiMesh; safe parsing |
| Web/API | FastAPI + uvicorn behind a reverse proxy; bearer-token auth; bind 127.0.0.1 by default | The existing product's built-in `http.server` is not recommended for production (PDF §2) |
| Jobs | SQLite ledger (`core/jobs.py`) + one worker process; one heavy job at a time at first | Same pattern as existing PhysiMesh; the PDF advises serialised pilot workloads |
| Evidence storage | Content-addressed write-once filesystem store (`core/artifacts.py`) | Reproducibility (REQ10); never rewrite old evidence [M§26] |
| Solver isolation | Docker by **digest**, read-only root, no network, `--cap-drop ALL`, pids/CPU/memory limits | Mirrors the existing SU2 container safeguards (PDF §2) |
| CFD + meshing | OpenFOAM (one pinned release; snappyHexMesh for 3D meshes) | Manifest recommendation [M§1]; STL-driven meshing [R1] |
| Rendering | ParaView `pvbatch` from saved recipes `[VERIFY-IN-BACKEND: image]` | [R8]; recipe-driven ranges |
| Front end | Plain HTML/CSS/JS + vendored three.js (pinned, SHA-256 recorded) | Matches existing UI; no React needed (PDF) |
| Tests / lint | pytest, ruff; `backend` marker for container tests | Fast unit suite, separate backend job |
| CI | GitHub Actions `[ASSUMPTION]` | Swap for the client's CI if different |

Repository layout:

```
physimesh-drone/
├── pyproject.toml  requirements.lock  README.md
├── src/physimesh/
│   ├── core/      artifacts.py  jobs.py  container.py
│   ├── api/       settings.py  app.py
│   ├── drone/     models.py units.py frames.py provenance.py atmosphere.py mass.py stl_import.py
│   │              geometry.py symmetry.py propulsion.py bem.py meshing.py trim.py allocation.py
│   │              mission.py report.py api.py schema/drone_manifest_v1.yaml
│   ├── solver/    contracts.py  openfoam.py  openfoam_templates/<release>/...
│   └── postpro/   loads3d.py field_registry.py capability_manifest.py contour_rules.py recipes.py statistics.py
├── web/           index.html  js/  vendor/
├── tests/         core/ api/ drone/ solver/ postpro/ architecture/ backend/
├── docs/          source/ decisions/ audit/ validation/ qa/
└── reference_impl/   (verified reference code, ported task by task, then deleted at Release D)
```

### 6.1 Layering rules

```
            ┌──────────────────────────────────────────────────────────┐
  Browser   │ 3D viewer · setup wizard · plot panels (no backend vocab)│
            └───────────────▲──────────────────────────────────────────┘
                            │ REST  /api/drone/*   (§10 WP09/WP04 tasks)
            ┌───────────────┴──────────────────────────────────────────┐
  Domain    │ src/physimesh/drone/   (aircraft-specific)               │
            │  models · units · frames · stl_import · geometry ·       │
            │  symmetry · atmosphere · mass · propulsion · bem ·       │
            │  meshing · trim · allocation · mission                   │
            └───────▲───────────────────────────────▲──────────────────┘
                    │ uses (never the reverse)      │
            ┌───────┴──────────────┐       ┌────────┴─────────────────┐
  Shared    │ src/physimesh/solver │       │ src/physimesh/postpro    │
            │ contracts · service  │       │ loads3d · field_registry │
            │ jobs · artifacts     │       │ contour_rules · recipes  │
            │ openfoam (adapter)   │       └──────────────────────────┘
            └───────▲──────────────┘
                    │ subprocess in pinned container
            ┌───────┴──────────────┐
  Backend   │ OpenFOAM vX (digest) │  snappyHexMesh · simpleFoam · pimpleFoam ·
            └──────────────────────┘  function objects (forces, yPlus, wallShearStress)
```

Rules:
- `solver/` and `postpro/` **must not import** `drone/` [M§1] ("Keep shared solver services independent of aircraft type"). Enforce this with an import-linter test (Task 1.3).
- Customer-facing flows never show OpenFOAM dictionary words. An "advanced" panel may show the translated profile [M§25].
- Every computed artefact carries a `Provenance` record (§6.4).

### 6.2 Files (proposed paths from [M§25]; tests mirror them)

| Path (under `src/physimesh/`) | Responsibility | Created in |
|---|---|---|
| `drone/__init__.py` | Package marker, exports | Task 2.1 |
| `drone/models.py` | Versioned project schema, readiness rules, status enums | Task 2.1, 2.5 |
| `drone/units.py` | Unit declarations, conversion records, dimension checks | Task 2.2 |
| `drone/frames.py` | World/body/rotor frames, rotations, transforms of points, vectors, axial vectors, tensors | Task 2.3 |
| `drone/atmosphere.py` | E03–E04, ISA, Sutherland (optional law), provenance | Task 2.4 |
| `drone/mass.py` | E01–E02 mass ledger, CG, inertia | Task 2.4 |
| `drone/provenance.py` | Hashing, canonical JSON, `Provenance` record | Task 2.1 |
| `drone/stl_import.py` | Safe bounded ASCII/binary STL parser | Task 3.1 |
| `drone/geometry.py` | Welding, topology checks, shells, component IDs, assembly tagging, repair revisions | Task 3.2–3.4 |
| `drone/symmetry.py` | E32–E33, geometric matching, physical eligibility, load reconstruction | Task 8.1–8.3 |
| `drone/propulsion.py` | Rotor maps (E15–E16), interpolation limits, momentum theory (E09–E10) | Task 6.1–6.2 |
| `drone/bem.py` | Blade element momentum (E11–E14, E55) | Task 6.3–6.4 |
| `drone/meshing.py` | 3D mesh request contract, rotor-zone readiness, E34 | Task 4.2 |
| `drone/trim.py` | E05–E08 residuals, trim outer loop | Task 12.1 |
| `drone/allocation.py` | E56 constrained allocation, failure masks | Task 12.2 |
| `drone/mission.py` | E46–E47 coupled mass–energy screening | Task 12.3 |
| `drone/api.py` | `/api/drone/*` FastAPI router (registered by `api/app.py`) | Tasks 3.5, 4.5, 7.3, 8.2, 9.4 |
| `postpro/loads3d.py` | E41–E44 native face integrals, reconciliation | Task 5.1–5.3 |
| `postpro/field_registry.py` | Canonical fields, dependency graph | Task 5.5 |
| `postpro/contour_rules.py` | Deterministic 8-step evidence selection | Task 9.2 |
| `postpro/recipes.py` | Plot-recipe persistence and replay, colour/range policy | Task 9.3 |
| `postpro/statistics.py` | E37–E40 windows, drift, GCI | Task 11.1 |
| `solver/openfoam.py` | Backend probe/validate/prepare/run/parse/diagnose/export | Task 4.3–4.4 |
| `solver/contracts.py` | Capabilities, capability records, backend protocol | Task 4.1 |
| `core/artifacts.py`, `core/jobs.py`, `core/container.py` | Evidence store, job ledger, hardened container runner | Task 1.2 |
| `api/settings.py`, `api/app.py` | Settings, FastAPI app factory, auth | Task 1.5 |

Tests: `tests/core/…`, `tests/api/…`, `tests/drone/…`, `tests/postpro/…`, `tests/solver/…`, `tests/architecture/…`.
Backend fixtures (need OpenFOAM): `tests/backend/…`, marked `@pytest.mark.backend` and run by a separate CI job.

### 6.3 End-to-end data flow

```
STL files + declared units + transforms
   │  POST /api/drone/import        (Task 3.5)
   ▼
GeometryRevision (hash) ── topology report ── 3D preview
   │  user tags roles: body/blade/hub/landing_gear/payload/ground/excluded
   ▼
ProjectSnapshot (immutable, hashed; nulls allowed)
   │  POST /api/drone/validate      (Task 2.5)
   ▼
Readiness report ──(any blocking null?)──► status = inputs_incomplete, STOP
   │
   ├── Screening path: rotor map / BEM ─► momentum check ─► mass–energy ─► screening_only report
   │
   └── CFD path:
        POST /api/drone/symmetry (optional, default OFF)
        POST /api/drone/mesh  ─► snappyHexMesh case ─► checkMesh report ─► MeshRecord(hash)
        POST /api/drone/runs  ─► probe() ─► validate() ─► prepare_case() ─► run() ─► parse()
                                  │
                                  ▼
                 native face fields + backend force histories
                                  │ loads3d (E41–E44) ─► reconcile with backend forces (0.1 % + abs)
                                  ▼
                 Force ledger (rotor / body / gravity / external, no duplication)
                                  │ statistics (windows, drift, GCI) ─► evidence level
                                  ▼
        POST /api/drone/plots ─► contour_rules (8 steps) ─► recipe.json + figures + integral table
                                  ▼
                 Trim + allocation + mission ─► Decision report (§13.3) with aircraft status
```

### 6.4 Provenance record (attached to every artefact)

```python
@dataclass(frozen=True)
class Provenance:
    schema_version: str          # "drone_manifest_v1"
    project_snapshot_sha256: str
    geometry_sha256: str | None
    mesh_sha256: str | None
    backend_name: str | None     # e.g. "openfoam-opencfd"
    backend_version: str | None  # e.g. "v2606"  [VERIFY-IN-BACKEND]
    backend_image_digest: str | None   # "sha256:..."; null blocks execution [M§32]
    recipe_sha256: str | None
    code_version: str            # git commit of physimesh
    created_utc: str             # ISO-8601
```

Hashing: SHA-256 of raw file bytes for files, and SHA-256 of **canonical JSON** (UTF-8, `sort_keys=True`, `separators=(",", ":")`, floats via `repr`) for structured records `[ASSUMPTION]`.

---

## §7 Equation catalogue E01–E56

These equations were transcribed from the manifest's Word math objects. Notation follows [M§3]. `×` is the cross product, `·` the dot product, `1` the identity tensor, `∮` a closed-surface integral. Equations marked ⚠ have caveats in the manifest that **must** go into the code docstring.

> The manifest says the turbulence and solver equations (E17–E30, E35) "identify required fields and coupling" and are **not** to be implemented as a home-made solver. OpenFOAM solves them. PhysiMesh only checks, translates and post-processes [M§8], [M§9]. Those rows show "backend" in the owner column.

### 7.1 Table

| ID | Equation | Owner module | Notes / caveat |
|---|---|---|---|
| E01 | m_TO = 750 + m_structure + m_propulsion + m_energy + m_avionics + m_other | `drone/mass.py` | Payload fixed at 750 kg [M§4] |
| E02 | x_CG = Σⱼ mⱼxⱼ / Σⱼ mⱼ ;  I_CG = Σⱼ [ Iⱼ + mⱼ( ‖dⱼ‖² 1 − dⱼdⱼᵀ ) ] | `drone/mass.py` | Iⱼ first rotated into the body frame; dⱼ = xⱼ − x_CG. STL volume × density is **not** a valid mass for hollow parts [M§4] |
| E03 | ρ = p_abs / (R_air T_air) ;  a = √(γ R_air T_air) ;  ν = μ/ρ | `drone/atmosphere.py` | Absolute p, Kelvin [M§4] |
| E04 | Re_c = ρ V_rel c / μ ;  M_local = V_rel / a ;  M_tip,screen = √((ΩR)² + V_axial²) / a | `drone/atmosphere.py` | Axial screening only. Forward flight needs local advancing/retreating velocity [M§4] |
| E05 | Σᵢ F_rotor,i + F_body + F_other + m g = m a | `drone/trim.py` | g = (0, 0, −g₀) in the world frame |
| E06 | Σᵢ [ (xᵢ − x_CG) × F_rotor,i + M_rotor,i ] + M_body = I ω̇ + ω × (I ω) | `drone/trim.py` | ⚠ Rigid body, constant inertia. Rotor gyroscopic terms and varying mass need an extended model. Fixed-pose CFD gives loads, not a trajectory [M§5] |
| E07 | Σᵢ Tᵢ = m g₀ + D_body,down ;  D_body,down = −F_body · e_z | `drone/trim.py` | Level hover, vertical rotor axes. Do **not** force D to be positive [M§5] |
| E08 | ε_F = ‖F_aero + m g − m a‖ / F_scale ;  ε_M = ‖M_aero − M_required‖ / M_scale | `drone/trim.py` | F_scale = m g₀, M_scale = m g₀ L_ref. Report components, not only norms [M§5] |
| E09 | A = πR² ;  vᵢ = √(T / (2ρA)) ;  P_ideal = T vᵢ = T^{3/2} / √(2ρA) ;  DL = T/A | `drone/propulsion.py` | Isolated ideal hover rotor, lower bound on power [M§6] |
| E10 | FM = P_ideal / P_shaft ;  P_shaft = Q_shaft Ω | `drone/propulsion.py` | ⚠ Not a whole-aircraft efficiency. Overlapping/coaxial rotors may not sum disk areas [M§6] |
| E11 | W_a = V_a + vᵢ ;  W_t = Ωr − v_θ ;  W = √(W_a² + W_t²) ;  φ = atan2(W_a, W_t) ;  α = θ(r) − φ | `drone/bem.py` | Propeller convention. Do **not** copy wind-turbine induction signs [M§6] |
| E12 | dL = ½ρW² c C_l(α, Re, M) dr ;  dD = ½ρW² c C_d(α, Re, M) dr | `drone/bem.py` | Polars are looked up, never extrapolated through stall [M§7] |
| E13 | dT = B (dL cos φ − dD sin φ) ;  dQ = B r (dL sin φ + dD cos φ) | `drone/bem.py` | B = blade count. Integrate from root cut-out to tip |
| E14 | dT = 4πρ r (V_a + vᵢ) vᵢ dr | `drone/bem.py` | ⚠ Simple non-swirling annulus, axial only. Not valid in strong crossflow, vortex-ring descent or interacting wakes [M§6] |
| E15 | n = RPM/60 ;  C_T = T/(ρn²D⁴) ;  C_Q = Q/(ρn²D⁵) ;  C_P = P/(ρn³D⁵) = 2π C_Q | `drone/propulsion.py` | Propeller convention. Undefined at n = 0, so return `unavailable` [M§7] |
| E16 | J = V_a/(nD) ;  η_p = T V_a / P_shaft | `drone/propulsion.py` | η_p → 0 in hover. This is **not** "zero hover capability" [M§7] |
| E17 | ∇·u = 0 | backend | Incompressible continuity |
| E18 | ρ(∂u/∂t + u·∇u) = −∇p + ∇·τ_eff + f_rotor | backend | f_rotor = force per volume on the fluid |
| E19 | S = ½(∇u + ∇uᵀ) ;  τ_eff = 2(μ + μ_t) S − ⅔ ρ k 1 | backend; adapter checks | ⚠ Some RANS solvers absorb ⅔ρk into a modified pressure. **Never add turbulent pressure twice** [M§8] |
| E20 | ∂ₜρ + ∇·(ρu) = 0 | backend | Compressible (future capability) |
| E21 | ∂ₜ(ρu) + ∇·(ρuu) = −∇p + ∇·τ + f | backend | |
| E22 | ∂ₜ(ρE) + ∇·((ρE + p)u) = ∇·(τ·u − q) + S_E ;  p = ρRT | backend | E = e + ‖u‖²/2. Do **not** implement with guessed source work [M§8] |
| E23 | ∂ₜ(ρk) + ∇·(ρuk) = P_k − β* ρ k ω_t + ∇·((μ + σ_k μ_t)∇k) | backend | Representative SST form only [M§9] |
| E24 | ∂ₜ(ρω_t) + ∇·(ρuω_t) = (γ_t/ν_t) P_k − β ρ ω_t² + ∇·((μ + σ_ω μ_t)∇ω_t) + D_cross | backend | |
| E25 | D_cross = 2(1 − F₁) ρ σ_ω2 (∇k·∇ω_t)/ω_t ;  μ_t = ρ a₁ k / max(a₁ω_t, S F₂) | backend | Store a backend coefficient snapshot + model version [M§9] |
| E26 | k = 3/2 (I_t U_t)² ;  ω_t = √k / (C_μ^{1/4} L_t) | `drone/models.py` (inflow helper) | ⚠ Do not set U_t = 0 in hover and conclude zero turbulence. L_t is not the box size [M§9] |
| E27 | u_τ = √(‖τ_w‖/ρ) ;  y⁺ = u_τ y / ν ;  y₁ = y⁺_target ν / u_τ | `drone/meshing.py` | Estimate only. Accept on the achieved y⁺ distribution [M§9] |
| E28 | ∂ₜu_r + (u_r·∇)u_r + 2Ω×u_r + Ω×(Ω×r) = −∇p/ρ + ∇·τ/ρ | backend (MRF) | Add Ω̇ × r for angular acceleration [M§10] |
| E29 | d/dt ∫_{V(t)} ρ dV + ∮_{∂V(t)} ρ(u − w)·n dS = 0 | backend | Moving-mesh conservation |
| E30 | dV/dt = ∮_{∂V} w·n dS | backend; diagnose() checks | Geometric (space) conservation law |
| E31 | F_rotor,i = −∫_{Vᵢ} fᵢ dV ;  M_rotor,i = −∫_{Vᵢ} (x − xᵢ) × fᵢ dV | `postpro/loads3d.py` | Reaction on the aircraft from a source on the fluid. Never also add resolved blade traction for the same rotor [M§10] |
| E32 | H = 1 − 2nnᵀ ;  x′ = x₀ + H(x − x₀) | `drone/symmetry.py` | Plane through x₀ with unit normal n |
| E33 | F′ = H F ;  Ω′ = det(H) H Ω ;  M′ = det(H) H M | `drone/symmetry.py` | det H = −1, so axial vectors pick up an extra sign. Rotation sense flips |
| E34 | H_layers = y₁ (r_g^{N_l} − 1)/(r_g − 1)  (r_g ≠ 1) ;  N_l y₁ at r_g = 1 | `drone/meshing.py` | Geometric layer-stack thickness [M§13] |
| E35 | d(ρφV)/dt + Σ_f ṁ_f φ_f = Σ_f Γ_f (∇φ)_f · S_f + S_φ V | backend | Finite-volume cell balance [M§14] |
| E36 | Co ~ ‖u − w‖ Δt / Δx ;  Δt_θ = Δθ_rad / ‖Ω‖ ;  f_BPF = B ‖RPM‖ / 60 | `drone/meshing.py` (time-step planner) | Backend uses its own exact Courant definition [M§14] |
| E37 | F̄ = (1/(t₂ − t₁)) ∫_{t₁}^{t₂} F dt ;  F′_rms = √( mean( (F − F̄)² ) ) | `postpro/statistics.py` | Whole revolution windows [M§15] |
| E38 | ε_mass = ‖ṁ_boundary + dM_fluid/dt‖ / ṁ_scale | `postpro/statistics.py` | ṁ_scale = gross flux or rotor throughput, **never** net hover flux [M§15] |
| E39 | p_o = ln((f₃ − f₂)/(f₂ − f₁)) / ln r ;  f_ext = f₁ + (f₁ − f₂)/(r^{p_o} − 1) | `postpro/statistics.py` | f₁ = finest. Constant ratio r only [M§15], [R6] |
| E40 | GCI₁₂ = F_s ‖(f₁ − f₂)/f₁‖ / (r^{p_o} − 1) | `postpro/statistics.py` | F_s safety factor; 1.25 for 3-grid studies per NPARC/Roache practice `[STD]` [R6] |
| E41 | t = −(p − p_ref) n_s + τ·n_s ;  F = ∫_S t dS | `postpro/loads3d.py` | n_s = solid outward normal (into fluid) |
| E42 | M_CG = ∫_S (x − x_CG) × t dS | `postpro/loads3d.py` | |
| E43 | Tᵢ = Fᵢ · aᵢ ;  Q_aero,i = Mᵢ · aᵢ ;  P_shaft,i = −M_aero,i · Ωᵢ | `postpro/loads3d.py` | Mᵢ about rotor centre. Windmilling can flip the sign [M§16] |
| E44 | M_O = M_CG + (x_CG − x_O) × F | `postpro/loads3d.py` | Moment transfer |
| E45 | d/dt ∫_V ρu dV + ∮_{∂V} ρu (u − w)·n dS = ∮_{∂V} (−p n + τ·n) dS + ∫_V f_ext dV | `postpro/loads3d.py` (CV check) | Independent consistency check only [M§17] |
| E46 | P_elec = Σᵢ P_shaft,i / (η_motor,i η_inverter,i η_drive,i) + P_aux ;  E_mission = ∫ P_elec dt | `drone/mission.py` | Signed regeneration needs an extended model [M§17] |
| E47 | m_battery,screen = (E_mission + E_reserve) / (e_pack f_usable) | `drone/mission.py` | ⚠ Screening only. Must iterate with E01 [M§17] |
| E48 | f_A,e = t·e ;  f^p_A,e = −(p − p_ref) n_s·e ;  f^v_A,e = (τ·n_s)·e | `postpro/field_registry.py` | Units N/m² [M§19] |
| E49 | m_A,e = ((x − x_CG) × t) · e | `postpro/field_registry.py` | Units N·m/m² |
| E50 | Cp = (p − p_ref)/q_ref ;  q_ref = ½ρU_ref² | `postpro/field_registry.py` | Rejected when U_ref = 0 [M§19] |
| E51 | u_rel = u_abs − Ω × (x − xᵢ) ;  u_a = u_abs·aᵢ ;  u_θ = u_abs·e_θ | `postpro/field_registry.py` | Mask the axis singularity [M§20] |
| E52 | ζ = ∇×u ;  W = ½(∇u − ∇uᵀ) ;  Q_v = ½(‖W‖_F² − ‖S‖_F²) | `postpro/field_registry.py` | Q_v (vortex criterion) ≠ torque Q [M§20] |
| E53 | τ_stream = τ_w · e_stream,tangent ;  C_f = τ_stream / q_ref | `postpro/field_registry.py` | Tangent undefined at stagnation, so mask it |
| E54 | aᵢ·(x − xᵢ) = s ;  s/R ∈ {−0.25, −0.5, −1, −2} | `postpro/contour_rules.py` | Wake planes when thrust axis is up and the wake runs down [M§21] |
| E55 | F_tip = (2/π) cos⁻¹( exp( −B(R − r) / (2 r sin φ) ) ) | `drone/bem.py` | ⚠ Don't apply to measured maps or already-corrected polars [M§31] |
| E56 | min_c ‖W_s (wrench(c) − wrench_req)‖² + λ P(c) | `drone/allocation.py` | c = RPM or pitch, only if physically available [M§31] |

### 7.2 Equation-implementation rules

- Every function that implements an equation has a docstring line `Implements: [M-Exx]` and states the units of every argument and of the return value.
- Equations owned by "backend" are **never** re-implemented. Our code only (a) generates settings for them, (b) reads their outputs, (c) checks their outputs against diagnostics.
- When a loss correction (E55) is used, the code must record whether it modifies induction, loading or both, to avoid applying it twice [M§6].

### 7.3 Verified fixture values (computed with Python while writing this plan)

Use these as exact test expectations. Tolerances are given per test.

| Quantity | Inputs | Value |
|---|---|---|
| Payload weight | 750 kg × 9.80665 | **7354.9875 N** (manifest rounds to 7,354.99 N) |
| Illustrative weight | 1500 kg × 9.80665 | **14709.975 N** |
| ISA sea-level density | p = 101325 Pa, T = 288.15 K, R = 287.05 | ρ = **1.2250123 kg/m³** |
| ISA sea-level sound speed | γ = 1.4 | a = **340.29229 m/s** |
| Sutherland μ at 288.15 K | μ_ref = 1.716e-5 Pa·s, T_ref = 273.15 K, S = 110.4 K `[STD]` | μ = **1.7892976e-5 Pa·s**, ν = **1.4606365e-5 m²/s** |
| Hover momentum | T = 1000 N, R = 1 m, ρ above | A = 3.1415927 m², vᵢ = **11.398294 m/s**, P_ideal = **11398.294 W**, DL = **318.30989 N/m²** |
| Figure of merit | P_ideal above, Q = 300 N·m at 500 RPM | Ω = 52.359878 rad/s, P_shaft = **15707.963 W**, FM = **0.72563792** |
| FM consistency trap | same but Q = 100 N·m | FM = 2.1769, which is **> 1 and physically impossible**, so the code must flag inconsistent input |
| Rotor coefficients | T = 1000 N, Q = 100 N·m, 500 RPM, D = 2 m | n = 8.3333333 s⁻¹, C_T = **0.73468652**, C_Q = **0.036734326**, C_P = **0.23080858** (= 2πC_Q) |
| Tip Mach (screen) | R = 1 m, 500 RPM, V_axial = 0 | **0.15386737** |
| Time step | 1° at 1000 RPM | Ω = 104.71976 rad/s, Δt = **1.6666667e-4 s** (manifest: 0.0001667 s) |
| Layer stack (E34) | y₁ = 1e-5 m, r_g = 1.2, N_l = 10 | **2.5958682e-4 m** |
| GCI example (E39–E40) | f₁ = 100, f₂ = 101, f₃ = 103, r = 2, F_s = 1.25 | p_o = **1.0**, f_ext = **99.0**, GCI₁₂ = **0.0125** |
| Prandtl tip (E55) | B = 2, R = 1, r = 0.9, φ = 10° | F_tip = **0.64636050** |
| Mirror (E33) | n = (0,1,0), Ω = (0,0,10) | det H = −1, Ω′ = **(0, 0, −10)** |
| Quad hover trim | W = 1500 kg × g₀, T = k_T Ω², k_T = 0.05 N·s²/rad², 4 equal rotors | Ω = **271.20080 rad/s** (2589.7769 RPM) |
| Mass–energy toy A | m_fixed = 1200 kg, A_tot = 8·π·1.5² m², FM 0.7, η 0.85, P_aux 2 kW, e_pack 250 Wh/kg, f_usable 0.8, reserve 20 %, 10 min hover | converges in 10 iterations (relative tol 1e-6): m_total = **1442.1503 kg**, m_battery = **242.15030 kg** |
| Mass–energy toy B | same with 200 Wh/kg, 20 min | converges slowly (107 iterations): m_total = **3066.9058 kg** |
| Mass–energy toy C | 200 Wh/kg, 60 min | **diverges** (m > 1e6 kg by iteration 6), so the status must be `requirement_not_met` |

> These toy cases test the code. They say **nothing** about the client's aircraft and must never appear in a client report as predictions.

---

## §8 Settings registers (from [M§31], [M§32])

All values are **proposed starting development settings**. None of them represents achieved accuracy. `null` means required project data is missing and blocks the related run or decision.

### 8.1 Geometry and physics [M§31]

| Setting key (YAML) | Initial policy | Change trigger |
|---|---|---|
| `identity.schema_version` | `drone_manifest_v1` | Explicit migration only |
| `mission.payload_mass_kg` | `750` | Customer requirement revision |
| `units.source_units` | `null` | Required CAD declaration |
| `frames.world_frame` | `ENU_z_up` | Explicit coordinate transformation |
| `frames.solid_normal` | `outward_into_fluid` | Backend patch conversion test |
| `masses.total_mass_kg`, `masses.cg_m` | `null` | Ledger completion |
| `rotors[].count`, `rotors[].radius_m` | `null` | Actual design selection |
| `rotors[].signed_rpm`, `rotors[].pitch_deg` | `null` | Per-condition design inputs |
| `atmosphere.pressure_pa`, `atmosphere.temperature_k` | `null` | Defined mission environment |
| `atmosphere.viscosity` | `null` or approved law (e.g. `sutherland`) | Atmosphere consistency |
| `fidelity.initial` | `measured_map` or `bem` | Input availability and intent |
| `flow.compressibility` | decided from local flow (blade Mach) | Blade Mach and physical effects |
| `flow.turbulence_model` | pinned backend SST variant for RANS tests | Validation and sensitivity |
| `symmetry.match_tolerance` | user-declared absolute (m) **and** relative | Tessellation and required accuracy |
| `symmetry.execution` | `off` | Full-domain verification |
| `boundaries.ground_model` | explicit per case | Actual flight clearance |
| `fidelity.bem.radial_stations` | `80` | Station sensitivity |
| `fidelity.bem.relative_load_residual` | `1.0e-4` | Tolerance sensitivity |
| `fidelity.bem.max_iterations` | `200` | — |
| `fidelity.bem.induction_relaxation` | `null` `[OPEN-QUESTION]` (manifest lists the setting without a value) | — |
| `fidelity.bem.loss_model` | `prandtl_tip` / `none`, with `applies_to: momentum|loading` | Data comparison |
| `fidelity.bem.polar_extrapolation` | `reject` `[ASSUMPTION]`, consistent with "do not extrapolate through stall" [M§7] | — |

### 8.2 Mesh, solver and evidence [M§32]

| Setting key | Starting value | Acceptance rule |
|---|---|---|
| `mesh.scales`, `domain.bounds` | `null` | Filled from geometry and a domain study |
| `mesh.layers.first_layer_yplus_target` | `1` (low-y⁺ strategy) | Achieved distribution and model suitability |
| `mesh.layers.growth` | `1.2` (manifest experimental range 1.15–1.25) | Collision, coverage, sensitivity |
| `mesh.layers.count` | `null` | Thickness and geometry dependent |
| `numerics.steady.iteration_budget` | `3000` (resource cap) | **The cap is not convergence** |
| `numerics.transient.rotation_per_step_deg` | `1` | Refine and compare loads |
| `numerics.transient.target_courant` | `0.8` | Actual maximum and sensitivity |
| `numerics.linear.final_rel_tol` | `0` where supported | No relative early termination in final solves |
| `numerics.linear.p_abs_tol` | `1e-7` | Residual definition and balance checks |
| `numerics.linear.u_turb_abs_tol` | `1e-6` | Backend scale and load checks |
| `numerics.correctors.outer`, `.pressure` | `2`, `2` | Per-step nonlinear sensitivity |
| `convergence.startup_discard_revs` | `≥ 5` | Extend until start-up has decayed |
| `convergence.averaging_window_revs` | `10` (to begin with) | Extend for drift and sampling convergence |
| `postprocessing.load_history_cadence` | every time step | Peak and blade-passage resolution |
| `postprocessing.full_field_cadence_deg` | `5` | Volume budget and sampling need |
| `convergence.force_drift_gate` | `0.5 %` between consecutive windows | Component and absolute-scale checks |
| `convergence.continuity_target` | `0.1 %` of declared gross scale | Moving-mesh balance |
| `validation.native_force_reconciliation` | `0.1 %` **plus** an absolute tolerance | Matching formulation and inputs |
| `validation.mesh_time_change_target` | `2 %` in decision quantities | Local loading also assessed |
| `validation.symmetry_change_target` | `1 %` with absolute scales | Eligible family only |

**Capability blocking [M§32]:** a `null` backend version or image digest, unsupported compressibility, an unresolved rotation zone, invalid pressure dimensions, missing rotor loading input, an unsupported wall treatment or incomplete physical boundaries **blocks execution**. Reaching a user-chosen resource ceiling never upgrades an incomplete solution.

---

## §9 Release roadmap and work-package order

### 9.1 Releases [M§27]

| Release | Contents | Gate evidence |
|---|---|---|
| **A** | STL import, component assignment, 3D viewer, mass and atmosphere contracts, stationary 3D mesh, verified force integration | Native units + analytical fixtures (F-GEO, F-FORCE) pass; one real stationary 3D OpenFOAM case reproduces from its hashes |
| **B** | Measured rotor maps or BEM, calibrated actuator sources, vehicle hover interference, intent-based postprocessing | Source-only models label prescribed vs predicted loads (CT05); contour fixtures CT01–CT08 pass |
| **C** | Blade-resolved steady rotating frame, then transient interfaces, phase processing, peak loads | Comparison against a suitable rotor dataset; mesh and time sensitivity; load/contour reconciliation still passes |
| **D** | Trim, control allocation, mission energy, uncertainty, constrained design comparisons | Decision report (§13.3) with correct status; fault cases report unreachable conditions honestly |

### 9.2 Work-package dependency graph [M§28]

```
WP01 Greenfield foundation
  └─► WP02 Schema & equations
        ├─► WP03 STL & 3D assembly
        │     └─► WP04 Mesh & backend
        │           └─► WP05 Loads & registry ───────────────┐
        └─► WP06 Rotor screening (needs rotor data)          │
                    │                                        │
   WP04+WP05+WP06 ─► WP07 Vehicle sources ──► WP09 Contour automation (needs WP05+WP07)
   WP03+WP07 ─────► WP08 Symmetry
   WP04–WP07 ─────► WP10 Explicit blades ──► WP11 Transient evidence
   WP06–WP11 ─────► WP12 Trim & mission
```

Release mapping: **A** = WP01–WP05 (plus viewer parts of WP03). **B** = WP06, WP07, WP09. **C** = WP08 (validation part), WP10, WP11. **D** = WP12.

### 9.3 Effort and schedule

The manifest says to **set development effort after WP01 and the first review of real STL and rotor data** [M§28]. This plan therefore gives no hours or dates. Task 1.4 produces the estimate from **measured** backend runs. Do not quote a timeline to the client before then.

### 9.4 Branching and commits `[ASSUMPTION]`

- One branch per work package: `drone/wp03-stl-import`.
- One commit per task (messages given in each task).
- Merge to main only after the definition of done (§1.3) and the release gate for that WP's release, where applicable.

---

## §10 Work packages and tasks

### How to read a task

- **Files** lists everything the task may touch. Touching anything else is a defect.
- **Interfaces** lists what the task consumes from earlier tasks and what it produces for later ones. Names and types here are binding.
- **Reference** points at verified code in `reference_impl/` (118 tests passing, see `reference_impl/README.md`). Port the tests **first and unchanged**, then port or adapt the implementation to the conventions WP01 found.
- ⚠ marks physics-critical tasks. These need an independent second review (§1.5).
- Test commands assume the Task 1.1 `pyproject.toml` (pytest with `src` on the path).

---

### WP01: Greenfield foundation (Release A, prerequisite for everything)

**Completion criterion (adapted from [M§28] for greenfield):** an empty but production-shaped repository, the platform services every later task relies on (artifact store, job ledger, hardened container runner, API shell), and a pinned, **measured** OpenFOAM backend.
**Why first:** every later task imports from these modules. Nothing here involves physics.

#### Task 1.1: Repository scaffold

**Files:** Create `pyproject.toml`, `README.md`, `docs/decisions/ADR-0001-greenfield.md`, `src/physimesh/__init__.py`, empty `__init__.py` in `src/physimesh/{core,drone,solver,postpro,api}/`, `tests/__init__.py`, `tests/test_smoke.py`, `.github/workflows/ci.yml` `[ASSUMPTION: GitHub; use the client's CI if different]`.

- [ ] **Step 1:** Write `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "physimesh-drone"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "numpy>=1.26", "scipy>=1.11", "pyyaml>=6",
  "fastapi>=0.110", "uvicorn>=0.29", "pydantic>=2.6", "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = ["pytest>=8", "httpx>=0.27", "ruff>=0.4"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
markers = ["backend: needs the pinned OpenFOAM container (run in the backend CI job)"]

[tool.ruff]
line-length = 110
```

- [ ] **Step 2:** Create the environment and **freeze exact versions** so that every model and every machine runs the same code:

```bash
python3.11 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]" && pip freeze > requirements.lock
```

- [ ] **Step 3:** Write `tests/test_smoke.py`:

```python
import physimesh


def test_package_imports():
    assert physimesh.__name__ == "physimesh"
```

- [ ] **Step 4:** Run `python -m pytest -q`. Expected: `1 passed`.
- [ ] **Step 5:** Run the verified reference suite on Python 3.11 to confirm it is still green on the chosen interpreter. It was verified on 3.9.6:

```bash
cd reference_impl && python -m pytest -q
```

Expected: `118 passed`. If anything fails on 3.11, stop and report. Do not edit expected values.
- [ ] **Step 6:** Write `ADR-0001-greenfield.md` recording the decision (§2.1), its reason (no PhysiMesh source available; user decision on 2026-10-02), the deviation from [M§0] ("Extend the existing PhysiMesh…"), and the integration path (§2.5).
- [ ] **Step 7:** Write `ci.yml` with three jobs: `lint` (`ruff check .`), `unit` (`pytest -q -m "not backend"`), `backend` (`pytest -q -m backend`, on a runner with Docker; it may be manual at first).
- [ ] **Step 8:** Commit: `git commit -m "chore: greenfield scaffold, pinned deps, CI skeleton, ADR-0001"`

#### Task 1.2: Platform core: artifact store, job ledger, hardened container runner

**Files:** Create `src/physimesh/core/artifacts.py`, `src/physimesh/core/jobs.py`, `src/physimesh/core/container.py`. Tests: `tests/core/test_artifacts.py`, `tests/core/test_jobs.py`, `tests/core/test_container.py`.

**Why these designs:** they match what the existing PhysiMesh platform already proved in production planning (SQLite job ledger, filesystem results, SU2 in a locked-down Docker container: read-only root, no network, dropped capabilities, process limit, writable case mount), as described in the *PhysiMesh Technical Architecture* PDF (26 Sep 2026). Matching it keeps a later merge cheap (§2.5).

**Interfaces (produces):**

```python
# core/artifacts.py  -- content-addressed, write-once
class ArtifactStore:
    def __init__(self, root: pathlib.Path): ...
    def put_bytes(self, data: bytes, *, kind: str, meta: dict) -> str: ...   # returns sha256; idempotent
    def put_file(self, path: pathlib.Path, *, kind: str, meta: dict) -> str: ...
    def open(self, sha256: str) -> typing.BinaryIO: ...
    def meta(self, sha256: str) -> dict: ...
# layout: <root>/objects/<sha[:2]>/<sha>  and  <root>/meta/<sha>.json ; never overwritten, never deleted here

# core/jobs.py  -- SQLite ledger; states exactly as plan §4.2
@dataclass(frozen=True)
class Budgets:                       # all REQUIRED, no defaults (plan §0 rule 1)
    cpu_cores: float
    memory_gb: float
    disk_gb: float
    wall_time_s: int
    pids_limit: int

ALLOWED_TRANSITIONS = {
    "queued": {"preparing", "cancelled"},
    "preparing": {"meshing", "running", "failed", "cancelled"},
    "meshing": {"running", "failed", "cancelled"},
    "running": {"postprocessing", "failed", "cancelled"},
    "postprocessing": {"completed", "failed", "cancelled"},
}

class JobLedger:
    def __init__(self, db_path: pathlib.Path): ...
    def submit(self, kind: str, payload: dict, budgets: Budgets) -> str: ...      # job_id
    def claim_next(self, worker_id: str) -> "Job | None": ...                     # atomic
    def transition(self, job_id: str, new_state: str, *, reason: str | None = None) -> None: ...
    def append_event(self, job_id: str, event: dict) -> None: ...
    def get(self, job_id: str) -> "Job": ...
    def mark_interrupted(self, live_worker_ids: set[str]) -> list[str]: ...       # orphaned running -> failed

# core/container.py
def docker_run_args(image_digest: str, workdir: pathlib.Path, cmd: list[str], budgets: Budgets) -> list[str]: ...
```

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_jobs.py
import threading

import pytest

from physimesh.core.jobs import Budgets, JobLedger

B = Budgets(cpu_cores=2, memory_gb=4, disk_gb=10, wall_time_s=3600, pids_limit=512)


def test_lifecycle_and_illegal_transition(tmp_path):
    led = JobLedger(tmp_path / "jobs.sqlite")
    jid = led.submit("mesh", {"x": 1}, B)
    assert led.get(jid).state == "queued"
    with pytest.raises(ValueError):
        led.transition(jid, "completed")              # queued -> completed is illegal
    led.transition(jid, "cancelled")
    assert led.get(jid).state == "cancelled"


def test_claim_is_atomic(tmp_path):
    led = JobLedger(tmp_path / "jobs.sqlite")
    led.submit("run", {}, B)
    got = []
    ts = [threading.Thread(target=lambda w=w: got.append(JobLedger(tmp_path / "jobs.sqlite").claim_next(w)))
          for w in ("w1", "w2", "w3")]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert sum(j is not None for j in got) == 1


def test_state_survives_restart(tmp_path):
    jid = JobLedger(tmp_path / "jobs.sqlite").submit("run", {}, B)
    assert JobLedger(tmp_path / "jobs.sqlite").get(jid).state == "queued"


def test_orphaned_running_job_marked_failed_interrupted(tmp_path):
    led = JobLedger(tmp_path / "jobs.sqlite")
    jid = led.submit("run", {}, B)
    led.claim_next("dead-worker")                     # -> preparing
    led.transition(jid, "running")
    assert led.mark_interrupted(live_worker_ids=set()) == [jid]
    j = led.get(jid)
    assert j.state == "failed" and j.reason == "interrupted"   # never silently resumed
```

```python
# tests/core/test_artifacts.py
import hashlib

import pytest

from physimesh.core.artifacts import ArtifactStore


def test_put_is_idempotent_and_content_addressed(tmp_path):
    s = ArtifactStore(tmp_path)
    a = s.put_bytes(b"solid x", kind="stl", meta={"name": "a"})
    b = s.put_bytes(b"solid x", kind="stl", meta={"name": "a"})
    assert a == b == hashlib.sha256(b"solid x").hexdigest()
    with s.open(a) as fh:
        assert fh.read() == b"solid x"
    assert s.meta(a)["kind"] == "stl"


def test_unknown_object_raises(tmp_path):
    with pytest.raises(KeyError):
        ArtifactStore(tmp_path).open("0" * 64)
```

```python
# tests/core/test_container.py
from pathlib import Path

from physimesh.core.container import docker_run_args
from physimesh.core.jobs import Budgets


def test_hardening_flags_present():
    args = docker_run_args("img@sha256:" + "a" * 64, Path("/data/case1"), ["simpleFoam"],
                           Budgets(4, 8, 20, 7200, 512))
    for flag in ("--network", "none", "--read-only", "--cap-drop", "ALL", "--pids-limit", "512",
                 "--cpus", "4", "--memory", "8g"):
        assert flag in args
    assert "img@sha256:" + "a" * 64 in args           # image referenced by digest, never by tag


def test_tag_reference_refused():
    import pytest
    with pytest.raises(ValueError):
        docker_run_args("opencfd/openfoam:latest", Path("/c"), ["x"], Budgets(1, 1, 1, 1, 64))
```

- [ ] **Step 2:** Run `python -m pytest tests/core -v`. Expected: FAIL (modules missing).
- [ ] **Step 3:** Implement:
  - `JobLedger`: one SQLite file. Use `BEGIN IMMEDIATE` for `claim_next` so only one worker wins. `jobs` table (`id, kind, payload_json, budgets_json, state, reason, worker_id, created_utc, updated_utc`) and an `events` table. Reject transitions not in `ALLOWED_TRANSITIONS`.
  - `ArtifactStore`: write to a temp file, `fsync`, then `os.replace` into place. Never overwrite an existing object.
  - `docker_run_args`: `["docker","run","--rm","--network","none","--read-only","--cap-drop","ALL","--pids-limit",str(b.pids_limit),"--cpus",str(b.cpu_cores),"--memory",f"{b.memory_gb:g}g","--tmpfs","/tmp","-v",f"{workdir}:/case:rw","-w","/case",image_digest,*cmd]`. Refuse any image string without `@sha256:`. The disk budget is enforced by the worker (checked before and after each stage), because Docker does not limit bind-mount disk use.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `git commit -m "feat(core): content-addressed artifacts, SQLite job ledger, hardened container runner"`

#### Task 1.3: Architecture guardrail tests

**Files:** Create `tests/architecture/test_layering.py`.

**Interfaces:** Produces the rule "solver/ and postpro/ never import drone/" [M§1], and "core/ imports nothing from drone/, solver/, postpro/ or api/".

- [ ] **Step 1: Write the test**

```python
"""Shared layers must stay independent of aircraft type [M§1]."""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2] / "src" / "physimesh"
RULES = {"solver": {"drone", "api"}, "postpro": {"drone", "api"},
         "core": {"drone", "solver", "postpro", "api"}}


def _resolved_imports(path: pathlib.Path):
    pkg = ["physimesh"] + list(path.relative_to(ROOT).parent.parts)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.split(".")
        elif isinstance(node, ast.ImportFrom):
            base = pkg[: len(pkg) - (node.level - 1)] if node.level else []
            mod = node.module.split(".") if node.module else []
            full = base + mod if node.level else mod
            yield full
            for a in node.names:
                yield full + [a.name]


def test_layering_rules():
    offenders = []
    for layer, forbidden in RULES.items():
        for f in (ROOT / layer).rglob("*.py"):
            for parts in _resolved_imports(f):
                if parts[:1] == ["physimesh"] and len(parts) > 1 and parts[1] in forbidden:
                    offenders.append(f"{f.relative_to(ROOT)} -> {'.'.join(parts)}")
    assert not offenders, offenders
```

- [ ] **Step 2:** Run `python -m pytest tests/architecture -v`. Expected: PASS.
- [ ] **Step 3:** Commit: `git commit -m "test(arch): enforce layer independence"`

#### Task 1.4: Pin the backend, measure it, size the compute

**Files:** Create `docs/audit/backend_pin.md`, `docs/audit/compute_sizing.md`, `docs/audit/effort_estimate.md`, `tests/backend/test_container_smoke.py`.

- [ ] **Step 1:** Choose **one** OpenFOAM distribution and release [M§1]. Recommendation: OpenCFD **v2606**, because the manifest's meshing reference [R1] is the v2606 documentation `[ASSUMPTION]`. Confirm with the client (§14 Q02).
- [ ] **Step 2:** Pull the vendor's official container image for that release `[VERIFY-IN-BACKEND: exact image name and tag on the vendor's registry]` and record its immutable digest:

```bash
docker inspect --format='{{index .RepoDigests 0}}' <image:tag>
```

- [ ] **Step 3:** Inside the container, record `echo $WM_PROJECT_VERSION`, the solver list (`ls $FOAM_APPBIN | grep -E 'simpleFoam|pimpleFoam|snappyHexMesh|checkMesh|foamToVTK'`) and the tutorials used as templates later:

```bash
find "$FOAM_TUTORIALS" -iname '*rotating*' -o -iname '*AMI*' -o -iname '*propeller*' | sort
```

Record the actual paths found. **Do not assume the tutorial names in this plan exist.** The rotating-fan AMI example the manifest cites [R2] is documented for v2212 and may have moved.
- [ ] **Step 4: Hardened-runner smoke test** (`tests/backend/test_container_smoke.py`, marked `backend`): run `blockMesh` and `checkMesh` on a copied tutorial **through `docker_run_args` from Task 1.2**, i.e. read-only root, no network. OpenFOAM may need writable paths besides `/case` and `/tmp`. If it fails, add the minimum extra `--tmpfs` mounts, record why, and keep every other hardening flag.
- [ ] **Step 5: Measure, don't guess.** Run one shipped incompressible `simpleFoam` tutorial, then the same case refined about 2× in each direction. For each run record: cell count (from `checkMesh`), peak RAM (`docker stats --no-stream` sampled, or `/usr/bin/time -v` inside the container), wall time, cores. Fit **measured** RAM per million cells and time per million cells per iteration. Write these into `compute_sizing.md` with the raw logs attached.
- [ ] **Step 6: Compute decision gate.** The existing PhysiMesh server profile is 4 vCPU / 16 GB RAM / 50 GB disk, sized for **2D** work only. The architecture PDF says "3D and unsteady simulations require fresh sizing". Using the Step 5 numbers, estimate the RAM, disk and time of (a) a coarse actuator-disk hover case (Release B) and (b) a blade-resolved transient case (Release C), once real geometry gives cell counts. If (b) exceeds the server, record the gap. The **client must decide** about a separate compute host before Release C starts (§14 Q12). Never shrink the mesh to fit the box [M§28], PDF §5.
- [ ] **Step 7:** Write `effort_estimate.md` from Tasks 1.1–1.4 plus the first real STL and rotor data, as the manifest requires [M§28]: person-days per WP with assumptions, plus the compute estimate. Mark it **draft for lead-engineer approval**.
- [ ] **Step 8:** Commit: `git commit -m "docs(audit): pin OpenFOAM by digest; measured compute sizing; draft effort"`

#### Task 1.5: API server shell and web shell

**Files:** Create `src/physimesh/api/settings.py`, `src/physimesh/api/app.py`, `web/index.html`, `web/js/app.js`, `web/vendor/` (pinned libraries with SHA-256 recorded in `web/vendor/SOURCES.md`). Test: `tests/api/test_app.py`.

**Interfaces (produces):**

```python
@dataclass(frozen=True)
class Settings:
    data_root: pathlib.Path
    db_path: pathlib.Path
    api_token: str                     # required; app refuses to start without it
    openfoam_image_digest: str | None  # null -> runs blocked (plan §8.2 capability blocking)
    bind_host: str = "127.0.0.1"       # private by default (PDF §2)

def load_settings(env: Mapping[str, str]) -> Settings: ...    # PHYSIMESH_* environment variables
def create_app(settings: Settings) -> fastapi.FastAPI: ...      # mounts /api/* routers and /web static files
```

Routers registered later: `drone/api.py` (Tasks 3.5, 4.5, 7.3, 8.2, 9.4).

- [ ] **Step 1: Failing tests**

```python
import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings, load_settings


def make(tmp_path, digest=None):
    s = Settings(tmp_path, tmp_path / "jobs.sqlite", "test-token", digest)
    return TestClient(create_app(s))


def test_health_reports_backend_pin_state(tmp_path):
    r = make(tmp_path).get("/api/health")
    assert r.status_code == 200 and r.json()["backend_pinned"] is False


def test_drone_routes_require_token(tmp_path):
    c = make(tmp_path)
    assert c.post("/api/drone/validate", json={}).status_code == 401


def test_missing_token_setting_refuses_start():
    with pytest.raises(ValueError, match="PHYSIMESH_API_TOKEN"):
        load_settings({"PHYSIMESH_DATA_ROOT": "/tmp/x"})
```

- [ ] **Step 2:** Run. Expected: FAIL. Implement with FastAPI (bearer-token dependency on every `/api/drone/*` route; `/api/health` is public). Run with `uvicorn` behind a reverse proxy in deployment, **not** Python's built-in `http.server`, which its documentation does not recommend for production (PDF §2).
- [ ] **Step 3:** `web/index.html` holds the workflow shell (Import → Assemble → Conditions → Mesh → Run → Results). Plain HTML/CSS/JavaScript, like the existing PhysiMesh UI. No React (PDF: not required).
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `git commit -m "feat(api): FastAPI shell with token auth, settings, web shell"`

---

### WP02: Schema and equations (Release A)

**Completion criterion [M§28]:** validated units, mass and atmosphere fixtures.

#### Task 2.1: Package skeleton and provenance

**Files:** Create `src/physimesh/drone/__init__.py`, `src/physimesh/drone/provenance.py`. Test: `tests/drone/test_wp02_foundations.py` (the provenance section).
**Reference:** `reference_impl/src/physimesh/drone/provenance.py`.
**Interfaces (produces):**
- `canonical_json(obj) -> str`
- `sha256_bytes(data: bytes) -> str`
- `sha256_record(obj) -> str`
- `Provenance` (frozen dataclass, fields as in §6.4) with `.blocking_for_execution() -> list[str]`

- [ ] **Step 1:** Copy the four provenance tests from the reference test file: `test_sha256_of_empty_bytes_is_standard_value`, `test_record_hash_independent_of_key_order`, `test_canonical_json_rejects_nan`, `test_null_backend_digest_blocks_execution`.
- [ ] **Step 2:** Run `python -m pytest tests/drone/test_wp02_foundations.py -k "sha256 or canonical or digest" -v`. Expected: FAIL (module missing).
- [ ] **Step 3:** Port `provenance.py` unchanged.
- [ ] **Step 4:** Re-run. Expected: 4 passed.
- [ ] **Step 5:** Commit: `git commit -m "feat(drone): provenance hashing and execution-blocking digest check"`

#### Task 2.2: Units and dimension checks

**Files:** Create `src/physimesh/drone/units.py`. Test: the units section of `test_wp02_foundations.py`.
**Interfaces (produces):** `LENGTH_TO_M`, `UnitsError`, `ConversionRecord`, `length_factor(unit|None)`, `to_si_length(values, unit) -> (ndarray, ConversionRecord)`, `parse_foam_dimensions(text) -> tuple[int,...]`, and the constants `DIM_PRESSURE_PA`, `DIM_KINEMATIC_PRESSURE`, `DIM_VELOCITY`, `DIM_DENSITY`.

- [ ] **Step 1:** Copy the tests `test_null_source_unit_is_rejected_never_inferred`, `test_mm_conversion_is_recorded`, `test_inch_is_exact`, `test_parse_foam_dimensions_pressure_and_kinematic`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Port `units.py`. Supported units are `m, mm, cm, in, ft` with exact factors. Adding another unit needs its exact definition and a test.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `git commit -m "feat(drone): explicit length units and OpenFOAM dimension parsing"`

#### Task 2.3: Frames and transforms ⚠

**Files:** Create `src/physimesh/drone/frames.py`. Test: the frames section.
**Interfaces (produces):** `MissingInput`, `rotation_matrix_zyx(yaw, pitch, roll)` (body→world, radians), `transform_points`, `transform_vectors` (polar), `transform_axial_vectors` (det-corrected), `transform_tensor`, and `RotorFrame(rotor_id, center_m, axis, signed_rpm, azimuth_zero_deg=None, phase_offset_deg=None)` with `.omega_vector()` and `.require_phase()`.

- [ ] **Step 1:** Copy the tests `test_yaw_90_maps_body_forward_to_world_north`, `test_axial_vector_flips_under_reflection_but_polar_does_not`, `test_inertia_tensor_rotation`, `test_rotor_positive_rpm_right_hand_rule`, `test_rotor_null_rpm_blocks`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Port `frames.py`. The docstring must state: "A coordinate transform applies to points, vectors, tensors, rotor axes and moment origins, not only to the rendered geometry" [M§3].
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Independent review: the reviewer re-derives Rz(90°)·(1,0,0) = (0,1,0) and the reflection of an axial vector by hand.
- [ ] **Step 6:** Commit: `git commit -m "feat(drone): world/body/rotor frames with polar vs axial transforms"`

#### Task 2.4: Atmosphere and mass ledger ⚠

**Files:** Create `src/physimesh/drone/atmosphere.py`, `src/physimesh/drone/mass.py`. Test: the atmosphere and mass sections.
**Interfaces (produces):**
- `R_AIR = 287.05`, `G0 = 9.80665`, `Atmosphere` (`.density`, `.speed_of_sound`, `.kinematic_viscosity`), `make_atmosphere(p, T, *, source, viscosity_pa_s=None, viscosity_law=None, gamma=1.4)`, `isa_troposphere(h)`, `check_altitude_pressure_consistency(h, p, rel_tol)`, `reynolds_chord`, `local_mach`, `tip_mach_screen`.
- `CATEGORIES`, `MassItem`, `MassSummary` (`.complete`), `summarize(items, *, required_payload_kg=750.0, need_inertia=False)`.

- [ ] **Step 1:** Copy the tests: `test_isa_sea_level_density_and_sound_speed`, `test_missing_pressure_blocks`, `test_inconsistent_altitude_and_pressure_rejected`, `test_tip_mach_screen_fixture`, `test_payload_weight_fixture`, `test_total_mass_cg_inertia_parallel_axis`, `test_null_mass_gives_no_total`, `test_missing_category_is_reported`, `test_payload_must_equal_requirement`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Port both modules. Required docstring caveats: "STL volume times a density is not a reliable mass estimate for a hollow assembly" [M§4], and "ISA here uses R_air = 287.05 (manifest), so values differ from published ISA tables at ~1e-5 relative."
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `git commit -m "feat(drone): atmosphere (E03-E04) and mass ledger (E01-E02)"`

#### Task 2.5: Project schema, YAML loader and readiness rules

**Files:** Create `src/physimesh/drone/models.py`, `src/physimesh/drone/schema/drone_manifest_v1.yaml` (template, Appendix A). Test: `tests/drone/test_models_readiness.py`.
**Interfaces:**
- Consumes: Tasks 2.1–2.4.
- Produces:
  - `AircraftStatus` (enum of the §4.1 strings), `ExecutionState` (§4.2), `EvidenceLevel` (§4.3), `Fidelity` (§4.5)
  - `ProjectSnapshot` (frozen; the parsed YAML groups from [M§26]: identity, units_and_frames, mission, masses, atmosphere, assembly, rotors, flow, fidelity, symmetry, domain, mesh, numerics, boundaries, convergence, postprocessing, validation, execution)
  - `load_project(path) -> ProjectSnapshot`
  - `project_from_mapping(data) -> ProjectSnapshot` (same validation as `load_project`, used by the API)
  - `ReadinessReport(purpose: str, blocking: list[str], warnings: list[str], status: AircraftStatus | None, ready: bool)`
  - `readiness(snapshot, purpose: Literal["screening", "cfd_run", "feasibility"]) -> ReadinessReport`

- [ ] **Step 1: Write the failing tests**

```python
import pathlib

import pytest

from physimesh.drone.models import AircraftStatus, load_project, readiness

TEMPLATE = pathlib.Path("src/physimesh/drone/schema/drone_manifest_v1.yaml")


def test_template_loads_and_preserves_nulls():
    snap = load_project(TEMPLATE)
    assert snap.identity["schema_version"] == "drone_manifest_v1"
    assert snap.mission["payload_mass_kg"] == 750
    assert snap.units_and_frames["source_units"] is None


def test_template_is_inputs_incomplete_for_every_purpose():
    snap = load_project(TEMPLATE)
    for purpose in ("screening", "cfd_run", "feasibility"):
        rep = readiness(snap, purpose)
        assert rep.status is AircraftStatus.INPUTS_INCOMPLETE
        assert "units_and_frames.source_units" in rep.blocking or purpose == "screening"


def test_unknown_schema_version_rejected(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text(TEMPLATE.read_text().replace("drone_manifest_v1", "drone_manifest_v9"))
    with pytest.raises(ValueError, match="schema_version"):
        load_project(p)


def test_missing_group_rejected(tmp_path):
    text = TEMPLATE.read_text()
    p = tmp_path / "x.yaml"
    p.write_text(text.replace("symmetry:", "symmetry_typo:"))
    with pytest.raises(ValueError, match="symmetry"):
        load_project(p)


def test_symmetry_execution_default_off():
    assert load_project(TEMPLATE).symmetry["execution"] == "off"


def test_cfd_run_blocked_by_null_backend_digest():
    rep = readiness(load_project(TEMPLATE), "cfd_run")
    assert "execution.backend_image_digest" in rep.blocking
```

Also required (added after the 2026-10-02 code review; see `tests/drone/test_models_readiness.py`): a **success-branch** test asserting `ready is True and status is None` for complete screening and CFD inputs; a map-only rotor written in full Appendix A record shape (blade/phase fields `null`) is screening-ready; a body component with `rotor_id: null` is CFD-ready; an invalid role, a blade naming an undeclared rotor, `requires_user_tag: true`, a zero rotor axis, and a missing `signed_rpm` for `cfd_run` each block.

- [ ] **Step 2:** Run `python -m pytest tests/drone/test_models_readiness.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement:
  - Use `yaml.safe_load` (never `yaml.load`) `[ASSUMPTION: PyYAML; reuse the checkout's YAML library if one exists]`.
  - Reject unknown `schema_version` and any missing or extra top-level group. Unknown **keys** inside a group are kept and reported as warnings, never dropped [M§26].
  - Blocking rules per purpose:
    - `screening` needs: `mission.payload_mass_kg`, a complete mass ledger (Task 2.4 `summarize(...).complete`), atmosphere p and T plus viscosity, and per rotor: count, radius and either a measured map or blade geometry with polars.
    - `cfd_run` additionally needs: `units_and_frames.source_units`, geometry revision hash, every assembly component role, rotor zone assignment, mesh request, `execution.backend_version`, `execution.backend_image_digest`, complete boundaries, and a supported pressure-dimension declaration.
    - `feasibility` additionally needs: motor limits (sustained and peak), energy system, mission duration and reserve policy.
  - **Every branch of the output is fixed (review fix, 2026-10-02):** any blocking item gives `status=AircraftStatus.INPUTS_INCOMPLETE, ready=False`. **No** blocking item gives `status=None, ready=True`. Readiness checks inputs only and must **never** return `screening_only` or any higher status, because no screening has run (§4.1, §0 rule 6).
  - **Record-shaped nulls are legal.** Appendix A record shapes (rotors, components) contain fields that only some purposes or models use. Never require every key of a record recursively. Require only the fields each purpose uses:
    - rotor (all purposes): `rotor_id`, `radius_m > 0`, `model` ∈ {measured_map, bem, actuator_disk, actuator_line, blade_resolved} if given, and `map_ref` **or** (`blade_ref` **and** `polar_ref`);
    - rotor (`cfd_run`, `feasibility`): finite `center_body_m`, finite non-zero `axis_body`, finite `signed_rpm` [M§3]. A `blade_resolved` rotor without `azimuth_zero_deg`/`phase_offset_deg` gets a **warning**, not a block. Those values are enforced when a transient case is generated (`RotorFrame.require_phase()`, Task 2.3);
    - component (`cfd_run`): `component_id`, `role` ∈ `ROLES` (Task 3.3), `rotor_id` naming a declared rotor **only** for blade/hub, and `requires_user_tag` not `true`. Static parts have `rotor_id: null` legitimately.
  - A whitespace-only string counts as missing.
  - Wire `POST /api/drone/validate` (body `{"project": {...}, "purpose": "..."}`) to `project_from_mapping` + `readiness`. Malformed project or unknown purpose gives HTTP 422. The response is `{purpose, ready, status, blocking, warnings}`.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `git commit -m "feat(drone): drone_manifest_v1 schema, loader and readiness rules"`

---

### WP03: STL and 3D assembly (Release A)

**Completion criterion [M§28]:** import diagnostics and component preview.

#### Task 3.1: Safe STL parser

**Files:** Create `src/physimesh/drone/stl_import.py`. Test: the parser section of `tests/drone/test_wp03_stl_geometry.py` plus `tests/drone/conftest.py` (cube fixture and STL writers).
**Reference:** `reference_impl/…/stl_import.py`.
**Interfaces (produces):** `StlError`, `StlMesh(triangles, file_normals, fmt, solid_names, sha256, n_bytes)`, `parse_stl(data: bytes, *, max_bytes, max_triangles) -> StlMesh`. **Triangles stay in declared file units.** Conversion to SI happens in Task 3.5 through `to_si_length` (Task 2.2).

- [ ] **Step 1:** Copy `conftest.py` and the 8 parser tests (`test_binary_roundtrip`, `test_binary_starting_with_solid_is_binary`, `test_ascii_roundtrip`, `test_truncated_binary_rejected`, `test_nan_rejected`, `test_triangle_limit_enforced`, `test_byte_limit_enforced`, `test_hash_is_of_raw_bytes`).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Port. Rules [M§11]: never `eval` or execute content. Binary is detected by an exact size match `84 + 50·N`, never by the word `solid`. Limits come from configuration (`execution.limits.max_upload_bytes`, `execution.limits.max_triangles` in the YAML).
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `git commit -m "feat(drone): bounded ASCII/binary STL parser"`

#### Task 3.2: Welding, topology diagnostics and component IDs

**Files:** Create `src/physimesh/drone/geometry.py`. Test: the topology and component-ID sections.
**Interfaces (produces):** `weld(triangles_m, tol_m) -> (verts, faces)`, `TopologyReport` (with `.closed_and_consistent`), `topology(verts, faces, area_tol_m2) -> TopologyReport`, `component_id(triangles_m, grid_m) -> str`.

- [ ] **Step 1:** Copy the 8 tests (`test_closed_cube_is_clean`, `test_missing_triangle_is_a_hole`, `test_flipped_triangle_breaks_winding`, `test_two_disjoint_cubes_are_two_shells`, `test_degenerate_and_duplicate_detected`, `test_weld_tolerance_must_be_positive`, `test_component_id_independent_of_triangle_and_vertex_order`, `test_component_id_changes_when_winding_flips`).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Port. The topology tolerance is given in metres **and** relative to geometry scale [M§11]: `tol_m = max(abs_tol_m, rel_tol × bbox_diagonal)`. Store both inputs and the resolved value.
- [ ] **Step 4:** Add one more test for thin features: a slot narrower than a declared `min_feature_m` produces a `thin_feature_below_resolution` warning. Implement it by flagging shells whose minimum bounding-box extent is below `min_feature_m` (first version; a refined check comes with meshing in Task 4.2).
- [ ] **Step 5:** Run. Expected: PASS.
- [ ] **Step 6:** Commit: `git commit -m "feat(drone): STL welding, topology diagnostics, stable component IDs"`

#### Task 3.3: Assembly tagging and rotor assignment

**Files:** Modify `src/physimesh/drone/geometry.py` (add assembly types). Test: `tests/drone/test_assembly.py`.
**Interfaces (produces):**

```python
ROLES = ("body", "blade", "hub", "landing_gear", "payload", "ground", "excluded")   # [M§11]

@dataclass(frozen=True)
class Component:
    component_id: str          # from component_id()
    source_file_sha256: str
    shell_index: int | None    # set when split from a combined STL
    role: str | None           # None until the user tags it
    rotor_id: str | None       # required for blade and hub
    requires_user_tag: bool    # True for connected/overlapping split candidates

@dataclass(frozen=True)
class Assembly:
    components: tuple[Component, ...]
    rotors: tuple[RotorFrame, ...]          # from Task 2.3
    rotation_zones: dict[str, str]          # rotor_id -> zone name

def validate_assembly(a: Assembly) -> list[str]   # human-readable blocking problems
```

- [ ] **Step 1: Write failing tests**

```python
from physimesh.drone.frames import RotorFrame
from physimesh.drone.geometry import Assembly, Component, validate_assembly


def comp(cid, role, rotor=None, tag=False):
    return Component(cid, "f" * 64, None, role, rotor, tag)


def test_blade_without_rotor_is_blocking():
    a = Assembly((comp("c1", "blade"),), (), {})
    assert any("c1" in p and "rotor" in p for p in validate_assembly(a))


def test_untagged_component_is_blocking():
    a = Assembly((comp("c1", None),), (), {})
    assert any("role" in p for p in validate_assembly(a))


def test_rotor_needs_rotation_zone_and_rpm_sign_consistency():
    r = RotorFrame("R1", (0, 0, 0), (0, 0, 1), 1000.0)
    a = Assembly((comp("b1", "blade", "R1"), comp("h1", "hub", "R1")), (r,), {})
    assert any("rotation zone" in p for p in validate_assembly(a))


def test_valid_minimal_assembly():
    r = RotorFrame("R1", (0, 0, 0), (0, 0, 1), 1000.0)
    a = Assembly((comp("body", "body"), comp("b1", "blade", "R1")), (r,), {"R1": "rotor1"})
    assert validate_assembly(a) == []


def test_split_candidate_requires_user_tag():
    a = Assembly((comp("s0", "body", tag=True),), (), {})
    assert any("user tag" in p for p in validate_assembly(a))
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `validate_assembly` with these rules [M§11]: every component has a role. Every blade and hub names an existing rotor. Every rotor has a rotation zone. Every rotor has at least one blade **or** is declared source-modelled (actuator: allowed, flagged as `rotor_source_model`). `requires_user_tag=True` blocks until the user confirms it. "Rotation metadata cannot be recovered reliably from geometry alone", so RPM sign and axis always come from user input.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `git commit -m "feat(drone): assembly roles, rotor assignment, rotation-zone validation"`

#### Task 3.4: Repair revisions (never silent)

**Files:** Modify `src/physimesh/drone/geometry.py`. Test: `tests/drone/test_repair.py`.
**Interfaces (produces):**

```python
@dataclass(frozen=True)
class GeometryRevision:
    revision_sha256: str            # sha256 over (parent, operations, resulting triangles)
    parent_sha256: str | None
    operations: tuple[str, ...]     # e.g. ("remove_degenerate", "orient_consistently")
    area_before_m2: float
    area_after_m2: float
    bounds_before_m: tuple
    bounds_after_m: tuple
    max_surface_distance_m: float   # symmetric distance before/after (symmetry.surface_distances)
    confirmed_by: str | None        # required for operations marked "major"
    triangles_m: np.ndarray

ALLOWED_OPS = {"remove_degenerate": "minor", "remove_duplicate": "minor",
               "orient_consistently": "minor"}       # hole closing / surface merging NOT offered

def repair(rev: GeometryRevision, ops: list[str], *, confirmed_by: str | None) -> GeometryRevision
```

- [ ] **Step 1: Failing tests:** (a) `orient_consistently` on a cube with one flipped triangle gives a new revision whose topology is `closed_and_consistent`, whose `parent_sha256` equals the old hash, and whose area is unchanged to 1e-12. The original triangles are unchanged (deep-compare). (b) An unknown op such as `close_holes` raises `ValueError` mentioning "not offered" [M§11]: "Do not close openings or merge surfaces purely to obtain a green mesh status". (c) Repeating the same repair gives the same `revision_sha256` (determinism).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `orient_consistently` as a breadth-first walk over each shell's face adjacency that flips neighbours to match, followed by a whole-shell flip if the signed volume is negative. Compute metrics before and after.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `git commit -m "feat(drone): logged geometry repair revisions"`

#### Task 3.5: Import endpoint, readiness output and 3D viewer

**Files:** Create `src/physimesh/drone/api.py` (FastAPI `APIRouter`, registered in `api/app.py` from Task 1.5) and browser assets under `web/js/import.js`, `web/js/viewer.js`. Tests: `tests/drone/test_api_import.py` and a manual UI checklist `docs/qa/viewer_checklist.md`.
**Interfaces (produces):** `POST /api/drone/import` [M§26]

Request (multipart): STL file(s), `source_units` (required, no default), optional transform `{scale, rotation_deg_zyx, translation_m}`.
Response (JSON) holds the readiness output fields from [M§11]:

```json
{
  "status": "read_ok | read_failed",
  "geometry_revision_sha256": "...",
  "unit_scale_to_m": 0.001,
  "conversion": {"from": "mm", "to": "m", "factor": 0.001},
  "transform": {"scale": 1.0, "rotation_deg_zyx": [0,0,0], "translation_m": [0,0,0], "sha256": "..."},
  "bounding_box_m": {"min": [..], "max": [..]},
  "triangle_count": 0, "shell_count": 0, "surface_area_m2": 0.0,
  "topology_issues": [{"kind": "boundary_edge", "count": 0, "locations_m": [[..]]}],
  "proposed_repairs": ["orient_consistently"],
  "components": [{"component_id": "cmp_...", "role": null, "requires_user_tag": true}],
  "unresolved_inputs": ["assembly.components[cmp_...].role", "rotors"],
  "note": "Import success means the file was read; it does not mean a valid CFD case was created."
}
```

- [ ] **Step 1: Failing API tests:** (a) uploading the cube in `mm` returns a bounding box of 0.001 m. (b) A missing `source_units` returns HTTP 422 naming `source_units`. (c) Binary-with-`solid` is accepted. (d) The `note` string is present verbatim. (e) Uploading the same file twice gives the same revision hash.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement the endpoint by composing Tasks 3.1–3.4 and 2.2. Persist the original file bytes with `ArtifactStore.put_bytes` (Task 1.2) [M§26]: "Retain original CAD…".
- [ ] **Step 4: Viewer** (three.js, vendored per Task 1.5). Required features [M§25]: units confirmation dialog **before** display, world and body axes gizmo (ENU z-up), component picking with role assignment, topology issues drawn at their 3D locations [M§11], rotor axis arrows with rotation-sense glyphs, symmetry plane display (read-only until WP08), clipping planes. Decimation for browser rendering must keep source component IDs and is never used for force integration [M§24].
- [ ] **Step 5:** Run the API tests (expected PASS) and complete `viewer_checklist.md` with screenshots.
- [ ] **Step 6:** Commit: `git commit -m "feat(drone): import endpoint with readiness report; 3D viewer"`

---

### WP04: Mesh and backend (Release A)

**Completion criterion [M§28]:** a reproducible stationary 3D case.

#### Task 4.1: Extend solver contracts with capabilities

**Files:** Create `src/physimesh/solver/contracts.py`. Test: `tests/solver/test_capabilities.py`.
**Interfaces (produces):**

```python
class Capability(str, Enum):          # [M§26] each is separate
    VOLUME_MESH_3D = "volume_mesh_3d"
    INCOMPRESSIBLE = "incompressible"
    COMPRESSIBLE = "compressible"
    RANS_SST = "rans_sst"
    ACTUATOR_DISK = "actuator_disk"
    ACTUATOR_LINE = "actuator_line"
    STEADY_ROTATING_FRAME = "steady_rotating_frame"
    TRANSIENT_INTERFACE = "transient_interface"
    FORCE_INTEGRATION = "force_integration"
    FIELD_EXPORT = "field_export"

@dataclass(frozen=True)
class CapabilityRecord:
    capability: Capability
    backend_version: str
    image_digest: str
    fixture_id: str           # test that proved it, e.g. "backend/test_stationary_box"
    fixture_passed_utc: str

class BackendProtocol(Protocol):                    # [M§26]
    def probe(self) -> dict: ...                    # version + capability records
    def validate(self, project) -> list[str]: ...   # unsupported settings
    def prepare_case(self, project, workdir) -> dict: ...   # generated files + translated settings
    def run(self, case, budgets) -> Iterator[dict]: ...     # lifecycle + resource events
    def parse(self, case) -> dict: ...              # dimensions, native frame, raw lineage
    def diagnose(self, case) -> dict: ...           # evidence evaluation
    def export(self, case) -> dict: ...             # results + reproducible recipes
```

- [ ] **Step 1: Failing tests:** (a) a `CapabilityRecord` with an empty `fixture_id` raises `ValueError` ("a capability must include a tested fixture") [M§26]. (b) Capability lookup for a backend whose binary exists but which has no record returns "unsupported" (never inferred from a binary) [M§26]. (c) `dimensionality` is a required field with value `3` for every record in this repository.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Field names follow this block exactly so a later merge with the legacy contracts is a mapping exercise `[LEGACY-PHYSIMESH]`.
- [ ] **Step 4:** Run the full unit suite. Expected: PASS.
- [ ] **Step 5:** Commit: `git commit -m "feat(solver): explicit tested capability records and backend protocol"`

#### Task 4.2: Mesh request contract and planners

**Files:** Create `src/physimesh/drone/meshing.py`. Test: `tests/drone/test_meshing.py`.
**Interfaces (produces):**

```python
@dataclass(frozen=True)
class LayerSpec:
    first_height_m: float | None
    growth: float              # starting 1.2 [M§32]
    count: int | None

@dataclass(frozen=True)
class MeshRequest:
    geometry_revision_sha256: str
    global_cell_m: float | None
    surface_level_by_component: dict[str, tuple[int, int]]   # (min, max) refinement level
    blade_root_tip_refinement: int | None
    edge_treatment: dict[str, str]                           # leading/trailing edge rules
    wake_refinement_regions: tuple[dict, ...]
    rotation_zones: dict[str, dict]                          # rotor_id -> {radius_m, height_m, center_m, axis}
    layers: dict[str, LayerSpec]                             # component role -> layers
    max_cells: int | None
    rotor_diameter_ref_m: float | None                       # for normalised lengths

def layer_stack_thickness(y1_m: float, growth: float, n_layers: int) -> float   # E34
def first_cell_height(y_plus_target: float, nu: float, u_tau: float) -> float    # E27
def rotation_time_step(delta_theta_deg: float, omega_rad_s: float) -> float      # E36
def blade_passing_frequency(n_blades: int, rpm: float) -> float                 # E36
def refinement_variants(req: MeshRequest, ratio: float) -> dict[str, MeshRequest]  # coarse/medium/fine
def validate_mesh_request(req: MeshRequest) -> list[str]
```

- [ ] **Step 1: Failing tests** (values from §7.3):

```python
import pytest
from physimesh.drone.meshing import (blade_passing_frequency, layer_stack_thickness,
                                     rotation_time_step)


def test_layer_stack_e34_fixture():
    assert layer_stack_thickness(1e-5, 1.2, 10) == pytest.approx(2.5958682e-4, rel=1e-7)


def test_layer_stack_unit_growth_branch():
    assert layer_stack_thickness(1e-5, 1.0, 10) == pytest.approx(1e-4)


def test_one_degree_at_1000_rpm():
    assert rotation_time_step(1.0, 1000 * 2 * 3.141592653589793 / 60) == pytest.approx(1.6666667e-4, rel=1e-7)


def test_bpf():
    assert blade_passing_frequency(3, 1200.0) == pytest.approx(60.0)
```

Also: (a) `refinement_variants` changes **only** mesh-size fields, so the geometry hash, physics and boundaries stay identical across variants [M§13]. (b) `validate_mesh_request` reports every `None` (null) field as blocking. (c) A rotation zone that intersects a non-rotating component's bounding box is reported ("Avoid blade contacts with static surfaces or rotation zone boundaries" [M§10]).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. The docstring for E34 says "A starting growth ratio of 1.15–1.25 is a mesh experiment, not proof of accuracy" [M§13].
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `git commit -m "feat(drone): 3D mesh request contract, layer/time-step planners"`

#### Task 4.3: OpenFOAM adapter: probe and case generation ⚠

**Files:** Create `src/physimesh/solver/openfoam.py` and `src/physimesh/solver/openfoam_templates/<release>/…`. Tests: `tests/solver/test_openfoam_generation.py` (unit) and `tests/backend/test_probe.py` (backend).
**Interfaces:**
- Consumes: Task 4.1 `BackendProtocol`, Task 4.2 `MeshRequest`, the pinned digest from Task 1.4.
- Produces: `OpenFoamBackend(image_digest: str, release: str)` implementing `probe()`, `validate()` and `prepare_case()`.

**Anti-hallucination rule for this task:** template files are **copied from the pinned container's own tutorials** (paths recorded in Task 1.4) and then parametrised. Do **not** type OpenFOAM dictionaries from memory. Each template file starts with a comment naming the tutorial file it came from and the release.

- [ ] **Step 1:** Write `tests/backend/test_probe.py`. It runs the container by digest, calls `probe()` and asserts that `backend_version` equals the release string from Task 1.4 and that `image_digest` matches.
- [ ] **Step 2:** Write the unit tests for `prepare_case()` on a box-in-box geometry (the cube fixture scaled to 0.1 m inside a 2 m domain):
  - (a) generated files include `system/blockMeshDict`, `system/snappyHexMeshDict`, `system/controlDict`, `system/fvSchemes`, `system/fvSolution`, `constant/transportProperties` (or the release's equivalent `[VERIFY-IN-BACKEND]`), `constant/turbulenceProperties` or `momentumTransport` `[VERIFY-IN-BACKEND]`, and `0/U`, `0/p`, `0/k`, `0/omega`, `0/nut`;
  - (b) a `translated_settings.json` maps every project setting to its dictionary location and value [M§14]: "Store translated settings and their definitions";
  - (c) a project setting with no known translation makes `validate()` return it as unsupported. Nothing is silently dropped;
  - (d) generation is byte-for-byte deterministic for identical inputs (hash compare).
- [ ] **Step 3:** Run. Expected: FAIL.
- [ ] **Step 4:** Implement. Required content (every keyword `[VERIFY-IN-BACKEND]` against the copied tutorial):
  - snappyHexMesh: `castellatedMesh`, `snap`, `addLayers`; the STL in `constant/triSurface/` **in metres** (already converted); `locationInMesh` computed from the domain (a point in the fluid, not inside a solid); layer controls from `LayerSpec`.
  - Steady incompressible: `simpleFoam`; transient: `pimpleFoam` [M§14].
  - Force function object (`forces`, `libs (forces)`, `patches`, `rho rhoInf`, `rhoInf <declared ρ>`, centre of rotation) with output every time step [M§32]; plus `yPlus` and `wallShearStress` function objects.
  - Linear solver final relative tolerance `0` where supported, `p` absolute 1e-7, `U/k/omega` absolute 1e-6 [M§32].
- [ ] **Step 5:** Run the unit tests (PASS) and then the backend probe test (PASS) in the `backend` CI job.
- [ ] **Step 6:** Commit: `git commit -m "feat(solver): OpenFOAM adapter probe and template-derived case generation"`

#### Task 4.4: Run, parse, diagnose, durable jobs

**Files:** Modify `src/physimesh/solver/openfoam.py`; use `core/jobs.py`, `core/artifacts.py`, `core/container.py` from Task 1.2 unchanged. Tests: `tests/solver/test_openfoam_parse.py` using **captured** logs, plus `tests/backend/test_run_lifecycle.py`.
**Interfaces (produces):** `run()` emits events with `state` ∈ §4.2 and resource usage. `parse()` returns `{"fields": {...with dimensions...}, "forces": <time series>, "residuals": ..., "checkmesh": {...}}`. `diagnose()` returns an evidence level (§4.3) plus reasons.

- [ ] **Step 1:** Run the Task 4.3 box case once in the container and **save the real** `log.checkMesh`, `log.simpleFoam` and `postProcessing/` output under `tests/solver/fixtures/openfoam_<release>/`. Parser tests use these captured files only. **Never invent log text.**
- [ ] **Step 2:** Write the parser tests: `checkMesh` max non-orthogonality, max skewness, min volume and "Mesh OK" flag extracted exactly as they appear in the captured file; residual histories per field; force time series with columns identified from the file's header comment `[VERIFY-IN-BACKEND: column layout differs between releases]`.
- [ ] **Step 3:** Write the lifecycle tests: cancel moves state to `cancelled` and kills the container. Exceeding a wall-time or disk budget moves to `failed` with reason `budget_exceeded`. The completion percentage is never derived from residual count [M§26].
- [ ] **Step 4:** Run. Expected: FAIL. Implement. Run. Expected: PASS.
- [ ] **Step 5:** `diagnose()` rule: a run that hits `iteration_budget` without meeting the force-drift gate is **not** `iteration_converged`. "Cap is not convergence" [M§32].
- [ ] **Step 6:** Commit: `git commit -m "feat(solver): OpenFOAM run lifecycle, parsers from captured logs, diagnostics"`

#### Task 4.5: Release A end-to-end stationary case ⚠

**Files:** `tests/backend/test_stokes_sphere.py`, `docs/validation/release_A_stationary.md`, endpoints `POST /api/drone/mesh` and `POST /api/drone/runs` in `drone/api.py`.

**Analytical fixture `[STD]`:** a sphere of radius a in uniform flow U at Re = ρU(2a)/μ ≪ 1. Stokes drag is F = 6πμUa, one third from pressure and two thirds from viscous stress. Oseen's first correction is F ≈ 6πμUa(1 + 3Re/16).

- [ ] **Step 1:** Set up a case with Re = 0.05 (choose ν, U and a and record them), laminar, steady `simpleFoam`, sphere STL tessellated finely enough that its area is within 0.1 % of 4πa².
- [ ] **Step 2:** Domain study: outer boundary at 25a, 50a and 100a. Finite domains raise the drag noticeably at low Re. Record the drag against a/L and extrapolate to a/L → 0. **Do not skip this.** A single box result is expected to be biased high.
- [ ] **Step 3:** Acceptance (proposed, lead-engineer approval required `[ASSUMPTION]`):
  - (a) our face integral (Task 5.1) reconciles with the backend `forces` output within 0.1 % plus abs tol [M§32];
  - (b) pressure:viscous ratio within 5 % of 1:2;
  - (c) domain-extrapolated drag within 3 % of the Oseen value;
  - (d) re-running from the stored hashes reproduces the force to the last stored digit.
- [ ] **Step 4:** Write `release_A_stationary.md` with the inputs, mesh stats, `checkMesh` output, results table and status. Status words come from §4. This is **software verification**, not validation of any aircraft.
- [ ] **Step 5:** Commit: `git commit -m "test(backend): Release A stationary 3D Stokes-sphere verification"`

---

### WP05: Loads and registry (Release A)

**Completion criterion [M§28]:** analytical force fixtures and native reconciliation.

#### Task 5.1: Native surface integration and rotor loads ⚠

**Files:** Create `src/physimesh/postpro/loads3d.py`. Test: `tests/postpro/test_wp05_loads.py`.
**Reference:** `reference_impl/src/physimesh/postpro/loads3d.py`.
**Interfaces (produces):** `SurfaceLoads`, `integrate_surface_loads(face_centres_m, area_vectors_solid_m2, pressure_pa, viscous_traction_pa, moment_origin_m, p_ref_pa)`, `transfer_moment(m_a, x_a, x_o, F)`, `RotorLoads`, `rotor_loads(F, M_about_center, axis, omega_vec)`, `source_reaction(f_on_fluid, volumes, centres, rotor_center)`, `solid_area_vectors_from_backend(sf)`.

- [ ] **Step 1:** Copy the mandatory fixture tests [M§16]: `test_uniform_pressure_on_closed_cube_gives_zero_force_and_moment` (CT02), `test_reference_pressure_cancels_on_closed_surface_only`, `test_pressure_on_one_planar_patch`, `test_linear_pressure_field_gives_buoyancy_like_force`, `test_known_tangential_traction_gives_shear_force`, `test_offset_load_gives_correct_moment`, `test_moment_transfer_matches_direct_integration`, `test_backend_normals_are_flipped_once`, `test_rotating_blade_torque_and_power_sign`, `test_actuator_reaction_is_opposite_to_source_on_fluid`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Port. Docstrings must state: "Do not integrate a smoothed visualisation surface" and "Moment about a rotor centre is different from moment about vehicle centre of gravity" [M§16].
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** **Backend sign check** (backend CI job): on the Task 4.5 case, read the boundary face area vectors from the mesh and confirm that `solid_area_vectors_from_backend` makes the sphere's summed `n_s dA` zero and its signed volume positive. This confirms the OpenFOAM normal convention for the pinned release. If it fails, stop: the flip is wrong for this release.
- [ ] **Step 6:** Commit: `git commit -m "feat(postpro): native 3D surface loads, rotor loads, source reactions"`

#### Task 5.2: Pressure and stress semantics ⚠

**Files:** Modify `loads3d.py`. Tests: `test_kinematic_pressure_converted_once` (CT04) and `test_p_rgh_and_bad_dimensions_refused`.
**Interfaces (produces):** `to_physical_pressure(values, dims, *, field_name, rho)`, `to_physical_stress(values, dims, *, rho)`, `SemanticsError`.

- [ ] **Step 1:** Copy the tests. Add one backend test: read `0/p` and the final-time `p` from the Task 4.5 case and check that `parse_foam_dimensions` returns the kinematic signature for an incompressible solver `[VERIFY-IN-BACKEND]`.
- [ ] **Step 2:** Run. Expected: FAIL. Port. Run. Expected: PASS.
- [ ] **Step 3: Turbulent pressure rule** [M§8]: for RANS, record whether the backend's `p` includes ⅔ρk. Add a test that a capability flag `pressure_includes_isotropic_turbulent_stress` must be explicitly `true` or `false` before any RANS force integral runs (`null` → `SemanticsError`). Never add the turbulent pressure twice.
- [ ] **Step 4:** Commit: `git commit -m "feat(postpro): dimension-driven pressure/stress conversion (CT04)"`

#### Task 5.3: Reconciliation with native backend forces

**Files:** Modify `loads3d.py`. Test: `test_reconciliation_tolerance` plus a backend test on the Task 4.5 case.
**Interfaces (produces):** `reconcile(ours, native, *, rel_tol, abs_tol) -> Reconciliation(passed, abs_error, allowed, status)`, where `status` ∈ `{"accepted", "diagnostic_only"}`.

- [ ] **Step 1:** Copy the test. Run. Expected: FAIL. Port. Run. Expected: PASS.
- [ ] **Step 2:** Wire it in: every accepted force report must hold `status == "accepted"`. Otherwise the force panel is labelled diagnostic only [M§22] (Step 7).
- [ ] **Step 3:** Commit: `git commit -m "feat(postpro): native force reconciliation gate"`

#### Task 5.4: Force ledger (no duplication)

**Files:** Modify `loads3d.py`. Tests: `test_ledger_refuses_double_counting`, `test_ledger_aero_total_excludes_gravity`.
**Interfaces (produces):** `LEDGER_CATEGORIES`, `LedgerEntry`, `ForceLedger.add()`, `.aerodynamic_total()`, `.excluded_components`.

- [ ] **Step 1:** Copy the tests. Run. Expected: FAIL. Port. Run. Expected: PASS.
- [ ] **Step 2:** Add a test that `excluded_components` appear in the report payload. "Excluded components must be visible in the report" [M§17].
- [ ] **Step 3:** Commit: `git commit -m "feat(postpro): categorised force ledger with duplication guards"`

#### Task 5.5: Field registry and derived-field dependency graph

**Files:** Create `src/physimesh/postpro/field_registry.py`. Test: `tests/postpro/test_field_registry.py`.
**Interfaces (produces):**

```python
@dataclass(frozen=True)
class FieldEntry:                  # every attribute required [M§23]
    semantic_name: str             # e.g. "traction.world_z"
    backend_source: str | None     # native field name, or None if derived
    association: str               # "wall_face" | "fluid_cell" | "rotor_zone" | "rotor_record"
    dimensions: tuple[int, ...]    # OpenFOAM order [kg m s K mol A cd]
    native_frame: str              # "world" | "body" | "rotor:<id>"
    derivation: tuple[str, ...]    # operator chain with versions
    supported_fidelities: tuple[str, ...]
    temporal: tuple[str, ...]      # "instantaneous" | "phase_average" | "time_average" | "rms"
    required_references: tuple[str, ...]   # e.g. ("p_ref", "x_cg")
    valid_domain: str
    quality_status: str

REGISTRY: dict[str, FieldEntry]   # at least the 11 entries of [M§23]
def dependencies(semantic_name: str) -> list[str]   # topologically ordered
```

- [ ] **Step 1: Failing tests:** (a) all 11 canonical fields from [M§23] exist: `pressure.static_gauge`, `traction.world_z`, `traction.rotor_axial`, `moment_density.rotor_axial`, `source.rotor_reaction`, `velocity.absolute_axial`, `velocity.relative_mach`, `wall_shear.signed`, `mesh.y_plus`, `wake.Q`, `load.thrust_history`. (b) `traction.world_z` has dimensions `(1, -1, -2, 0, 0, 0, 0)` (N/m²). (c) `dependencies("moment_density.rotor_axial")` includes the pressure traction, the viscous traction and the rotor centre. (d) `source.rotor_reaction.supported_fidelities` excludes `steady_rotating_frame` and `transient_mesh`, while `traction.rotor_axial` excludes `actuator_disk` (a source rotor has no blade surface, CT05). (e) Every entry has non-empty values for every attribute ("Names alone are insufficient" [M§23]).
- [ ] **Step 2:** Run. Expected: FAIL. Implement using the dependency graph in [M§23]: pressure + normals → pressure traction; stress + normals → viscous traction; sum → total traction; projection → signed force density (E48); lever arm × traction → moment density (E49).
- [ ] **Step 3:** Run. Expected: PASS.
- [ ] **Step 4:** Commit: `git commit -m "feat(postpro): canonical field registry and dependency graph"`

**Release A gate:** Tasks 1.1–5.5 done. Task 4.5 report accepted by the lead engineer. Full unit + backend suites green. Tag `release-A`.

---

### WP06: Rotor screening (Release B)

**Completion criterion [M§28]:** validated maps or BEM, with applicability. **Depends on rotor data from the client (§14 Q04).** The software can be built and verified without it. The client's rotor cannot be evaluated without it.

#### Task 6.1: Momentum theory and coefficients ⚠

**Files:** Create `src/physimesh/drone/propulsion.py`. Test: `tests/drone/test_wp06_rotor.py` (momentum and coefficient section).
**Reference:** `reference_impl/…/propulsion.py`.
**Interfaces (produces):** `Unavailable(reason)`, `IdealHover`, `ideal_hover(T, R, rho)`, `FigureOfMerit(value, flags)`, `figure_of_merit(P_ideal, Q, Ω)`, `Coefficients`, `propeller_coefficients(T, Q, rpm, D, rho)`, `advance_ratio_and_efficiency(V, rpm, D, T, P)`.

- [ ] **Step 1:** Copy the tests `test_ideal_hover_fixture`, `test_figure_of_merit_fixture_and_impossible_value_flagged`, `test_coefficients_fixture_and_cp_equals_2pi_cq`, `test_zero_rpm_coefficients_unavailable`.
- [ ] **Step 2:** Run. Expected: FAIL. Port. Run. Expected: PASS.
- [ ] **Step 3:** Docstring caveats: "Figure of merit uses isolated hover assumptions; it is not universal aircraft efficiency. Overlapping or coaxial rotors cannot use independent disk area sums" [M§6]. "eta_p goes to zero in hover; do not label that as zero hover capability" [M§7].
- [ ] **Step 4:** Commit: `git commit -m "feat(drone): momentum theory and propeller coefficients (E09-E10, E15-E16)"`

#### Task 6.2: Measured rotor map store

**Files:** Modify `propulsion.py`. Tests: `test_rotor_map_refuses_extrapolation` plus `tests/drone/test_rotor_map_metadata.py`.
**Interfaces (produces):** `RotorMap(rpm, v_axial_m_s, thrust_n, torque_nm, rho_test, torque_sign_convention, power_kind, metadata)` and `.lookup(rpm, v) -> (T, Q) | Unavailable`.

- [ ] **Step 1:** Copy the extrapolation test. Add a metadata test: constructing a map without the [M§7] keys (`instrumentation_uncertainty`, `fixture_geometry`, `inflow`, `blade_pitch`, `motor_thermal_state`, `interpolation_limits`) gives readiness warnings, and **without** `torque_sign_convention` or `power_kind` raises an error.
- [ ] **Step 2:** Run. Expected: FAIL. Implement. Run. Expected: PASS.
- [ ] **Step 3:** Density rescaling via coefficients is allowed **only** with the flag `similar_re_mach_assumed=True` stored in the result, and never through stall or compressibility changes [M§7].
- [ ] **Step 4:** Commit: `git commit -m "feat(drone): measured rotor maps with envelope and metadata rules"`

#### Task 6.3: BEM station solver ⚠

**Files:** Create `src/physimesh/drone/bem.py`. Test: the BEM section of `test_wp06_rotor.py`.
**Reference:** `reference_impl/…/bem.py` (includes the closed-form initial-inflow fix: starting from vᵢ = 0 puts root stations outside the polar on iteration 1, which the reference run showed).
**Interfaces (produces):** `TabulatedPolar(alpha_deg, cl, cd, source)`, `Blade(n_blades, radius_m, root_cutout_m, r_def_m, chord_m, twist_deg)`, `BemSettings(radial_stations, rel_load_residual, max_iterations, relaxation, tip_loss)`, `prandtl_tip_factor(B, R, r, φ)`, `initial_inflow(...)`, `Station`, `BemResult`, `solve_rotor(blade, rpm, v_axial, rho, mu, a_sound, polar, settings)`.

Algorithm (as implemented and tested):
1. Station midpoints of `radial_stations` equal annuli from root cut-out to tip.
2. Initial vᵢ from the closed-form linear BEMT inflow (Leishman) using the polar's own lift slope at 0°.
3. Iterate: E11 → polar lookup (refuse outside table) → E12 → E13 → loss factor F (E55, momentum side only) → momentum update vᵢ from E14 with F, swirl v_θ from angular momentum dQ = 4πρr²F(V_a+vᵢ)v_θ dr → relax with `relaxation`.
4. Converged when |dT_BE − dT_mom|/|dT_BE| < `rel_load_residual`. Negative loading, an out-of-polar α or the max-iteration limit make the station **unconverged**. Any unconverged station makes the whole result `rejected_unconverged_stations`, with T, Q and P = NaN [M§31].

- [ ] **Step 1:** Copy the tests `test_prandtl_tip_fixture`, `test_bem_hover_all_stations_converge_and_satisfy_momentum_balance`, `test_bem_power_not_below_ideal_momentum_bound`, `test_bem_station_refinement_sensitivity_is_reported`, `test_bem_rejects_when_alpha_leaves_polar`, `test_bem_zero_rpm_unavailable`, `test_bem_relaxation_has_no_silent_default`.
- [ ] **Step 2:** Run. Expected: FAIL. Port. Run. Expected: PASS.
- [ ] **Step 3:** For the record (reference run, test blade and thin-airfoil polar at 1500 RPM, ISA sea level): T = 457.52 N, Q = 30.875 N·m, P = 4849.8 W, FM = 0.727, max 12 iterations per station, 80→160-station thrust change 0.05 %. These numbers **describe the test fixture only.**
- [ ] **Step 4:** Commit: `git commit -m "feat(drone): BEM with swirl, Prandtl tip loss and strict convergence"`

#### Task 6.4: BEM applicability and validation hook

**Files:** Modify `bem.py`. Create `docs/validation/rotor_stand_plan.md`. Test: `tests/drone/test_bem_applicability.py`.
**Interfaces (produces):** `applicability(result, *, v_axial, crossflow_m_s, descent_rate_m_s, induced_velocity_m_s) -> list[str]`.

- [ ] **Step 1: Failing tests:** applicability warnings for (a) nonzero crossflow ("E14 not valid in strong crossflow"), (b) descent with |V_descent| in the vortex-ring range relative to vᵢ ("simple axial momentum estimate is inadequate in vortex ring conditions" [M§2]; the flag threshold is a configurable setting with **no** default `[OPEN-QUESTION]`), (c) any station where the local Mach exceeds the polar's Mach range.
- [ ] **Step 2:** Implement. Run. Expected: PASS.
- [ ] **Step 3:** Write `rotor_stand_plan.md` for the "Isolated rotor stand" campaign [M§27]: multiple RPM, relevant inflows, matched geometry/pitch/atmosphere/RPM/inflow/blockage, absolute and relative errors, measurement uncertainty and repeatability. Data source: **client test data preferred** (§14 Q04). If a public dataset is proposed, record its licence and say plainly that "validation on a small rotor does not by itself establish a large rotor with different Reynolds, Mach, blade flexibility or installation effects" [M§27].
- [ ] **Step 4:** Commit: `git commit -m "feat(drone): BEM applicability flags; rotor-stand validation plan"`

---

### WP07: Vehicle sources (Release B)

**Completion criterion [M§28]:** hover interference and source bookkeeping.

#### Task 7.1: Actuator-disk case generation ⚠

**Files:** Modify `solver/openfoam.py` and templates. Tests: `tests/solver/test_actuator_generation.py`, `tests/backend/test_actuator_disk.py`.
**Interfaces (produces):** `prepare_case()` supports `rotor.model == "actuator_disk"` with a loading law that is either `prescribed_thrust` (input) or `bem_distribution` (from Task 6.3).

- [ ] **Step 1:** Copy the actuator-disk source configuration from the pinned release's tutorials or documentation (`[VERIFY-IN-BACKEND]`: the OpenCFD source is documented as `actuationDiskSource`; confirm the name, options and variants in the pinned release). Record the provenance comment.
- [ ] **Step 2: Failing unit tests:** (a) every rotor modelled as a disk gets its own cell zone. (b) `translated_settings.json` records the disk direction from rotor axis aᵢ and the prescribed T. (c) `validate()` refuses a disk without a loading input ("missing rotor loading input blocks execution" [M§32]).
- [ ] **Step 3: Backend test:** a single disk in a large quiescent box. Our source-reaction integral (Task 5.1 `source_reaction`) over the disk cells must equal the prescribed T within 0.1 % ("Source spread must not change total force or torque" [M§10]). The reaction sign is upward when the source pushes air down.
- [ ] **Step 4:** Implement. Run unit tests (PASS) and the backend test (PASS).
- [ ] **Step 5:** Commit: `git commit -m "feat(solver): actuator-disk rotors with conserved source totals"`

#### Task 7.2: Prescribed-versus-predicted labelling (CT05)

**Files:** Modify `postpro/loads3d.py` (ledger). Create `src/physimesh/drone/report.py` with the labelling functions (extended in Task 12.3). Test: `tests/postpro/test_source_labels.py`.

- [ ] **Step 1: Failing tests:** (a) a ledger entry from a disk with `prescribed_thrust` carries `origin="input"`, and the report shows "Prescribed T (input, not a prediction)" [M§7], [M§33]. (b) Swirl and reaction torque from an axial-only disk are `Unavailable("axial-only disk supplies no swirl/torque")` [M§10]. (c) Blade-pressure plots for a disk rotor are listed as unavailable with their missing dependency.
- [ ] **Step 2:** Implement. Run. Expected: PASS.
- [ ] **Step 3:** Commit: `git commit -m "feat(postpro): label prescribed rotor loads; mark unavailable disk outputs"`

#### Task 7.3: Full-vehicle hover interference case

**Files:** `docs/validation/hover_interference_<case>.md`, campaign definition in `POST /api/drone/campaigns` [M§26]. Test: `tests/backend/test_hover_interference_smoke.py` (small generic geometry).

- [ ] **Step 1:** Implement `POST /api/drone/campaigns`. A campaign is a set of runs that vary **only** the declared variables. The endpoint refuses a campaign whose members differ in undeclared fields (hash compare of the snapshot minus the varied keys).
- [ ] **Step 2:** Domain study: run hover with several rotor-diameter clearances upstream, laterally and downstream. Record the thrust and body-download sensitivity. "A close boundary can constrain entrainment or distort thrust even with a good residual history" [M§13]. Hover far-field boundaries let ambient inflow and wake outflow through without a forced freestream [M§13] `[VERIFY-IN-BACKEND: boundary condition names from the pinned tutorials]`.
- [ ] **Step 3:** Outputs per run: per-rotor T and Q, body vertical force by component, total ledger, and E07 required ΣT = m g₀ + D_body,down.
- [ ] **Step 4:** The status ceiling for these results is `numerically_unverified` until Task 11.2 assesses mesh and time.
- [ ] **Step 5:** Commit: `git commit -m "feat(drone): controlled campaigns; hover interference workflow"`

---

### WP08: Symmetry (geometry in Release A/B, validation in Release C)

**Completion criterion [M§28]:** geometric tests and a full-domain comparison.

#### Task 8.1: Reflection transforms ⚠

**Files:** Create `src/physimesh/drone/symmetry.py`. Tests: `tests/drone/test_wp08_symmetry.py` (transform section).
**Reference:** `reference_impl/…/symmetry.py`.
**Interfaces (produces):** `reflection_matrix(n)`, `reflect_points(x0, n, pts)`, `reflect_triangles(x0, n, tris)`, `reflect_rotor(x0, n, rotor, new_id)`.

- [ ] **Step 1:** Copy the tests `test_reflection_matrix_properties`, `test_reflected_triangles_keep_outward_normals`, `test_reflected_rotor_flips_handedness`.
- [ ] **Step 2:** Run. Expected: FAIL. Port. Run. Expected: PASS.
- [ ] **Step 3:** Rule: "Preserve the source geometry rather than overwriting it" [M§12]. Reflected geometry is a new revision (Task 3.4 types).
- [ ] **Step 4:** Commit: `git commit -m "feat(drone): reflection of geometry and rotors (E32-E33)"`

#### Task 8.2: Geometric match and physical eligibility ⚠

**Files:** Modify `symmetry.py`. Tests: the match and eligibility sections, including the parametrised `test_reject_listed_operating_states`.
**Interfaces (produces):** `closest_point_on_triangle`, `sample_triangles`, `surface_distances`, `GeometryMatch`, `geometric_match(src, tgt, x0, n, *, abs_tol_m, rel_tol, samples_per_edge=3)`, `OperatingState`, `Eligibility`, `physical_eligibility(x0, n, rotors, state, geometry, *, pos_tol_m, rpm_tol, vel_tol_m_s)`.

- [ ] **Step 1:** Copy the tests `test_closest_point_matches_brute_force`, `test_symmetric_pair_matches_and_offset_pair_does_not`, `test_counter_rotating_pair_is_eligible`, `test_reject_single_swirling_rotor_on_plane`, `test_reject_co_rotating_pair`, `test_reject_asymmetric_rpm` and `test_reject_listed_operating_states` (6 cases).
- [ ] **Step 2:** Run. Expected: FAIL. Port. Run. Expected: PASS.
- [ ] **Step 3:** Add `POST /api/drone/symmetry` [M§26] returning both the geometry match **and** physical eligibility, with every reason listed. The UI shows "A heuristic symmetry score is not a physical eligibility result" [M§12].
- [ ] **Step 4:** Commit: `git commit -m "feat(drone): symmetry geometric match and physical eligibility"`

#### Task 8.3: Reduced-domain reconstruction and full-domain comparison ⚠

**Files:** Modify `symmetry.py`. Tests: `test_ct06_reconstruct_offset_force_and_moment`, `test_moment_origin_off_plane_refused`, plus `tests/backend/test_symmetry_vs_full.py`.
**Interfaces (produces):** `reconstruct_full_loads(F_half, M_half, x0, n, origin, *, pos_tol_m) -> (F_full, M_full)`.

- [ ] **Step 1:** Copy the tests. Run. Expected: FAIL. Port. Run. Expected: PASS.
- [ ] **Step 2:** Record the represented and the simulated blade count and area in the result [M§12].
- [ ] **Step 3: Backend comparison** (Release C): one eligible counter-rotating configuration run both full and half (OpenFOAM `symmetryPlane` boundary `[VERIFY-IN-BACKEND]`). Gate: < 1 % change with absolute scales [M§32]. Only after this passes may `symmetry.execution` be switched on **for that case family**. Store the comparison as validation evidence.
- [ ] **Step 4:** Commit: `git commit -m "feat(drone): symmetry load reconstruction; full-vs-reduced validation"`

---

### WP09: Contour automation (Release B)

**Completion criterion [M§28]:** intent rules, prerequisites and saved recipes.

#### Task 9.1: Capability manifest builder

**Files:** Create `src/physimesh/postpro/capability_manifest.py`. Test: `tests/postpro/test_capability_manifest.py`.
**Interfaces:** Consumes the `parse()` output (Task 4.4) and the field registry (Task 5.5). Produces `build_capability_manifest(parsed_case) -> CapabilityManifest` (the type is defined in Task 9.2).

- [ ] **Step 1: Failing tests:** using the **captured** Task 4.4 fixtures: blade walls are detected from assembly roles, pressure kind comes from the dimensions (never from the name `p`), `velocity_frame` is read from case metadata, `accepted_time_window=False` until Task 11.1 accepts a window, and `reference_speed_m_s=None` in hover.
- [ ] **Step 2:** Implement. Run. Expected: PASS.
- [ ] **Step 3:** Commit: `git commit -m "feat(postpro): capability manifest from parsed case (step 2)"`

#### Task 9.2: Deterministic evidence selection ⚠

**Files:** Create `src/physimesh/postpro/contour_rules.py`. Tests: the contour-rule section of `tests/postpro/test_wp09_wp11_postpro.py`.
**Reference:** `reference_impl/…/contour_rules.py`.
**Interfaces (produces):** `INTENTS` (10 intents from [M§22]), `CapabilityManifest`, `PlotSpec`, `Missing`, `EvidencePlan` (with `.complete`), `select_evidence(intent, cap, *, requested=(), time_mode="mean")`.

- [ ] **Step 1:** Copy the tests `test_payload_lift_with_blade_walls`, `test_payload_lift_with_disks_never_invents_blade_pressure` (CT05), `test_rotor_power_selects_axial_moment_and_signed_power`, `test_ct03_cp_rejected_at_zero_reference`, `test_ct03_cp_allowed_with_declared_tip_speed`, `test_unknown_pressure_semantics_blocks_traction`, `test_ct07_unaccepted_window_blocks_mean_plots`, `test_yplus_rejected_for_laminar`.
- [ ] **Step 2:** Run. Expected: FAIL. Port. Run. Expected: PASS.
- [ ] **Step 3:** Add the remaining [M§33] table rows as tests: crosswind interference selects signed rotor-axial slices plus per-rotor load deltas and rejects mirror reduction without eligibility. Separated region selects signed shear plus vectors and rejects unsigned shear magnitude. Two designs get matched planes with shared limits. An unconverged transient gets diagnostic instantaneous plots with status, and no accepted mean thrust figure.
- [ ] **Step 4:** Natural-language intent mapping comes **after** this engine and only through a reviewable classifier whose output is a list of intents. Deterministic rules then select the evidence [M§22]. The LLM never selects plots directly.
- [ ] **Step 5:** Commit: `git commit -m "feat(postpro): deterministic evidence selection (steps 3-4)"`

#### Task 9.3: Location, time, display policy, reconciliation and recipe persistence

**Files:** Create `src/physimesh/postpro/recipes.py`. Modify `contour_rules.py` (`compute_range`). Tests: `test_ct01_equal_fields_on_different_meshes_share_legend`, `test_ct08_percentile_clipping_reports_extrema_and_fraction`, `test_nans_counted_not_hidden`, plus `tests/postpro/test_recipes.py`.
**Interfaces (produces):** `RangeRecord`, `compute_range(policy, fields, *, weights=None, percentile=None)`, `wake_planes(center, axis, radius, s_over_r=(-0.25, -0.5, -1, -2))` (E54), `PlotRecipe` (frozen dataclass of everything in [M§22] step 8), `save_recipe(recipe) -> sha256`, `replay(recipe_sha256) -> (figures, integral_table)`.

- [ ] **Step 1:** Copy the three range tests. Write recipe tests: (a) a replay on the same data gives an identical integral table and identical range numbers (CT08 final sentence). (b) User overrides are stored under `overrides` and cannot create a field with missing physical data [M§22]. (c) Wake planes for axis (0,0,1), centre (0,0,1) and R = 1 have plane offsets z = 0.75, 0.5, 0.0, −1.0. (d) The colour-map choice is sequential for non-negative magnitudes and diverging centred at zero for signed fields [M§24]. (e) The caption contains run ID, field, units, component/plane, frame, time treatment, colour range, fidelity and validation status [M§18].
- [ ] **Step 2:** Run. Expected: FAIL. Implement. Run. Expected: PASS.
- [ ] **Step 3:** Rendering: ParaView `pvpython` scripts generated from the recipe (fixed transfer-function ranges, out-of-range and NaN colours [R8]). No automatic per-frame rescaling. Mesh decimation for display keeps component IDs [M§24].
- [ ] **Step 4:** Commit: `git commit -m "feat(postpro): range policy, wake planes, persistent replayable plot recipes"`

#### Task 9.4: Plot endpoint and acceptance tests

**Files:** `drone/api.py` (`POST /api/drone/plots`, `GET /api/drone/runs/{id}`). Test: `tests/drone/test_api_plots.py`.

- [ ] **Step 1: Failing tests:** the response contains `figures`, `plot_recipe.json`, `integral_table` and `unmet_prerequisites` [M§23]. A plot whose integral (recomputed from its own source data) differs from the official load beyond tolerance is returned with `status="diagnostic_only"` [M§24]. Badges for numerical quality and validation status are present on exports [M§24].
- [ ] **Step 2:** Add the integration-seam export (§2.5): `GET /api/drone/runs/{id}/export` returns a ZIP with `load_cases.json`, `propulsion_map.json`, recipes and hashes. Contract test: the JSON validates against `src/physimesh/drone/schema/export_v1.schema.json` (written in this step), every force carries `units`, `frame`, `origin_m`, `status` and `provenance`, and a run with status `diagnostic_only` exports with that status, never as accepted.
- [ ] **Step 3:** Implement. Run. Expected: PASS.
- [ ] **Step 4:** Commit: `git commit -m "feat(drone): plot, run-detail and export endpoints with acceptance checks"`

**Release B gate:** WP06, WP07, WP09 complete. CT01–CT08 all pass (CT02, CT04 and CT06 are covered in WP05/WP08). One disk-based hover interference study is documented with status ≤ `numerically_unverified`. Tag `release-B`.

---

### WP10: Explicit blades (Release C)

**Completion criterion [M§28]:** a rotating case and a measured comparison.

#### Task 10.1: Steady rotating frame (MRF) case ⚠

**Files:** `solver/openfoam.py`, templates. Tests: `tests/solver/test_mrf_generation.py`, `tests/backend/test_mrf_isolated_rotor.py`.

- [ ] **Step 1:** Template source: the pinned release's MRF tutorial files `[VERIFY-IN-BACKEND]` (`constant/MRFProperties` with cell zone, origin, axis and omega in the OpenCFD layout; confirm).
- [ ] **Step 2: Unit tests:** (a) the MRF ω sign equals the rotor's `omega_vector()` (Task 2.3), **including handedness**. (b) Non-rotating patches inside the zone are listed explicitly. (c) The rotation zone does not intersect static geometry (Task 4.2 check).
- [ ] **Step 3: Backend fixture:** a wall-velocity sign test. On a rotating blade patch, the sampled wall velocity at a point r from the axis equals Ω × (x − centre) in the absolute frame [M§9]. The test samples it and compares.
- [ ] **Step 4:** Isolated rotor at several RPMs. Compare with the rotor-stand data (Task 6.4) once the client supplies them. Report absolute and relative errors and uncertainty. Status at most `validation_pending` until the comparison passes the agreed targets (e.g. 5 % thrust / 10 % torque, **proposed** [M§15]).
- [ ] **Step 5:** Commit: `git commit -m "feat(solver): steady rotating-frame blade-resolved rotors"`

#### Task 10.2: Transient sliding-interface (AMI) case ⚠

**Files:** `solver/openfoam.py`, templates. Tests: `tests/backend/test_ami_rotor.py`.

- [ ] **Step 1:** Template source: the pinned release's rotating AMI tutorial (from the Task 1.4 search; the manifest's [R2] points at a rotating-fan AMI example) `[VERIFY-IN-BACKEND]`: dynamic mesh solid-body rotation of a cell zone plus cyclicAMI patch pairs.
- [ ] **Step 2:** Time step from `rotation_time_step(1°, Ω)` and Courant target 0.8. The smaller of the two wins [M§14], [M§32].
- [ ] **Step 3:** Record the interface diagnostics: AMI weights and sums, flux imbalance, donor quality [M§10]. A test fails the run if AMI weight sums leave the configured band `[OPEN-QUESTION: band value, no manifest default]`.
- [ ] **Step 4:** Geometric conservation check (E30) via `diagnose()`.
- [ ] **Step 5:** Commit: `git commit -m "feat(solver): transient AMI blade-resolved rotors"`

---

### WP11: Transient evidence (Release C)

**Completion criterion [M§28]:** time and phase validation.

#### Task 11.1: Windows, drift, GCI ⚠

**Files:** Create `src/physimesh/postpro/statistics.py`. Tests: the statistics section of `test_wp09_wp11_postpro.py`.
**Reference:** `reference_impl/…/statistics.py`.
**Interfaces (produces):** `WindowStats`, `window_stats(t, f, t1, t2)`, `revolution_windows(t, f, period, *, discard_revs, revs_per_window)`, `drift(windows, abs_scale)`, `GridConvergence`, `grid_convergence(f1, f2, f3, r, fs=1.25)`, `effective_refinement_ratio(V, n_coarse, n_fine)`.

- [ ] **Step 1:** Copy the tests `test_window_mean_and_rms_of_sinusoid`, `test_revolution_windows_and_drift`, `test_gci_fixture`, `test_oscillatory_convergence_not_forced_into_gci`, `test_effective_ratio_3d`.
- [ ] **Step 2:** Run. Expected: FAIL. Port. Run. Expected: PASS.
- [ ] **Step 3:** Add the mass-balance diagnostic E38 with an explicit `m_dot_scale` argument and **no** default. Test that passing the net hover boundary flux as the scale is refused when its magnitude is below 1e-3 of the gross flux (the threshold is configurable) [M§15].
- [ ] **Step 4:** Commit: `git commit -m "feat(postpro): revolution windows, drift gate, GCI (E37-E40)"`

#### Task 11.2: Mesh and time campaigns

**Files:** `docs/validation/mesh_time_<case>.md`. Campaign definitions through Task 7.3.

- [ ] **Step 1:** Generate coarse, medium and fine meshes with `refinement_variants` (Task 4.2) and a constant effective ratio. Do not change geometry, models or boundaries [M§13].
- [ ] **Step 2:** For transients: run 1°, 0.5° and 0.25° per step on the chosen mesh.
- [ ] **Step 3:** Compute GCI for the decision quantities (T, Q, body download). Gate < 2 % change [M§32]. Inspect local blade loading too.
- [ ] **Step 4:** Promote the evidence to `mesh_assessed` / `time_assessed` only through a function that checks these records exist (test: promotion without records raises).
- [ ] **Step 5:** Commit: `git commit -m "feat(drone): mesh/time assessment campaigns and evidence promotion"`

#### Task 11.3: Phase averaging and peak events (CT07)

**Files:** `postpro/statistics.py`. Test: `tests/postpro/test_phase.py`.

- [ ] **Step 1: Failing tests:** (a) phase binning uses **each rotor's own** phase reference. Asking to phase-average two rotors at different RPM with one reference raises [M§21]. (b) The mean of vector magnitudes is not the magnitude of the mean vector, so both are computed and labelled [M§21]. (c) A peak outside the accepted window is returned as an instantaneous event with its time and can never feed the mean load (CT07). (d) Startup discard, retained revolutions, bin width and sample counts are stored.
- [ ] **Step 2:** Implement. Run. Expected: PASS.
- [ ] **Step 3:** Commit: `git commit -m "feat(postpro): per-rotor phase averaging and peak-event handling"`

**Release C gate:** an MRF and an AMI isolated rotor compared against the agreed dataset, mesh and time assessed, symmetry full-vs-reduced comparison passed for at least one family, reconciliation still green. Tag `release-C`.

---

### WP12: Trim and mission (Release D)

**Completion criterion [M§28]:** a coupled feasibility report with constraints.

#### Task 12.1: Hover allocation and trim residuals ⚠

**Files:** Create `src/physimesh/drone/allocation.py` and `src/physimesh/drone/trim.py`. Tests: `tests/drone/test_wp12_trim_mission.py` (allocation section).
**Reference:** `reference_impl/…/allocation.py`.
**Interfaces (produces):** `AllocRotor(rotor_id, position_body_m, axis_body, spin_sign, k_thrust, k_torque, omega_max_rad_s, failed=False)`, `effectiveness_matrix(rotors, cg)`, `AllocationResult` (ε_F, ε_M, residual components, active constraints, feasible, status ∈ {trimmed, unreachable}), `allocate_hover(rotors, mass_kg, cg, l_ref_m, body_force_n=(0,0,0), body_moment_nm=(0,0,0), *, tol_force, tol_moment)`.

- [ ] **Step 1:** Copy the tests `test_quad_hover_trim_fixture`, `test_body_download_raises_required_thrust`, `test_sustained_speed_limit_makes_hover_unreachable`, `test_motor_loss_quad_cannot_trim_all_axes`.
- [ ] **Step 2:** Run. Expected: FAIL. Port. Run. Expected: PASS.
- [ ] **Step 3:** Report components as well as norms: "A small overall norm must not conceal an unacceptable yaw moment" [M§5]. Add a test that a 1e-6 force residual together with a large yaw residual gives `feasible=False`.
- [ ] **Step 4:** Commit: `git commit -m "feat(drone): bounded hover allocation with honest unreachable reporting"`

#### Task 12.2: Map-based nonlinear allocation (E56) and fault cases

**Files:** Modify `allocation.py`. Test: `tests/drone/test_allocation_nonlinear.py`.

- [ ] **Step 1:** Replace `k_thrust·Ω²` with the rotor model from WP06/WP10 (map, BEM or CFD-calibrated) through a callable `rotor_model(rotor_id, command) -> (T, Q)`. Solve E56 with bounds (SciPy `minimize`, method `SLSQP` or `trust-constr` `[ASSUMPTION]`) starting from the linear solution. Commands are RPM or pitch **only if physically available** [M§31].
- [ ] **Step 2: Tests:** (a) with a quadratic rotor model it reproduces the Task 12.1 answer to 1e-6 relative. (b) The `λ P(c)` term at λ > 0 lowers total power without breaking the force tolerance. (c) Fault masks: each single-rotor loss for the given layout is reported as trimmed or unreachable with its active constraints, never with "sufficient summed thrust" logic [M§5].
- [ ] **Step 3:** Commit: `git commit -m "feat(drone): nonlinear constrained allocation (E56) and fault cases"`

#### Task 12.3: Mission energy and the decision report ⚠

**Files:** Create `src/physimesh/drone/mission.py`; extend `src/physimesh/drone/report.py` (from Task 7.2). Tests: the mission section of `test_wp12_trim_mission.py` plus `tests/drone/test_decision_report.py`.
**Reference:** `reference_impl/…/mission.py`.
**Interfaces (produces):** `electrical_power(...)` (E46), `MissionResult`, `size_battery(m_without_battery, p_elec_of_mass, *, duration_s, e_pack_wh_per_kg, f_usable, reserve_fraction, rel_tol, max_iterations, divergence_mass_kg)`, `build_decision_report(snapshot, results) -> DecisionReport`.

- [ ] **Step 1:** Copy the tests `test_electrical_power_eq46`, the three parametrised `test_coupled_mass_energy_toy_cases` and `test_null_energy_density_blocks`.
- [ ] **Step 2:** Write the report tests:
  - `test_margin_uses_sustained_limit_same_case`: margin = (available − required)/required with the denominator documented; available thrust comes from the **sustained** limit at the **same** density and electrical state; asking for a margin from a peak limit raises [M§5].
  - `test_report_refuses_mixed_cases`: thrust from case A with efficiency from case B raises [M§17].
  - `test_report_order`: the report starts with mass, condition, thrust, power, margin and evidence status [M§29], then answers the seven decision questions [M§2].
  - `test_status_ceiling`: the report's aircraft status is the minimum allowed by every contributing result's evidence (§4.1 rules). A diverged mission sizing gives `requirement_not_met`.
- [ ] **Step 3:** Run. Expected: FAIL. Implement. Run. Expected: PASS.
- [ ] **Step 4:** Commit: `git commit -m "feat(drone): coupled mass-energy sizing and decision report"`

**Release D gate:** the decision report is produced for the client configuration with an honest status. Fault and derating cases are reported. The report is reviewed against §13 by a human. Tag `release-D`.

---

## §11 Validation campaigns and acceptance fixtures

### 11.1 Campaigns [M§27]

| Campaign | Purpose | Minimum retained evidence | Plan tasks |
|---|---|---|---|
| Geometry fixtures | Units, topology, transforms | Known bounds, area, normals | 2.2, 2.3, 3.1–3.4, 8.1 |
| Force fixtures | Pressure, stress and moment signs | Analytical vs computed loads | 5.1–5.3, 4.5 |
| Isolated rotor stand | Rotor T, Q, power validity | Multiple RPM and relevant inflows | 6.4, 10.1 |
| Mesh and time series | Discretisation assessment | Matched physical cases + refinement logs | 11.2 |
| Full vehicle hover | Body download, rotor interference | Component loads; wake measurements where available | 7.3 |
| Symmetry comparison | Reduction eligibility | Paired field and load differences | 8.3 |
| Off-design operation | Applicability limits | Density, crosswind, clearance, descent cases | 6.4, 7.3, 12.3 |
| Fault and derating | Feasibility under defined faults | Allocation residuals, actuator limits | 12.2 |

### 11.2 Fixture index (every fixture is an executable test)

| ID | Statement (manifest source) | Test |
|---|---|---|
| F-FORCE-1 | Uniform pressure on closed cube → zero net force [M§16] | `test_uniform_pressure_on_closed_cube_gives_zero_force_and_moment` |
| F-FORCE-2 | Pressure on one planar patch → predicted normal force | `test_pressure_on_one_planar_patch` |
| F-FORCE-3 | Linear pressure → expected result | `test_linear_pressure_field_gives_buoyancy_like_force` |
| F-FORCE-4 | Known tangential traction → shear force | `test_known_tangential_traction_gives_shear_force` |
| F-FORCE-5 | Offset load → correct moment | `test_offset_load_gives_correct_moment` |
| F-FORCE-6 | Rotating blade torque sign | `test_rotating_blade_torque_and_power_sign` |
| F-FORCE-7 | Actuator reaction check | `test_actuator_reaction_is_opposite_to_source_on_fluid` |
| F-FORCE-8 | Backend normal convention (pinned release) | Task 5.1 Step 5 backend test |
| F-STOKES | 3D stationary verification | Task 4.5 |
| CT01 | Equal fields → same legend under shared recipe | `test_ct01_equal_fields_on_different_meshes_share_legend` |
| CT02 | Uniform face pressure on closed surface → zero integrated load | = F-FORCE-1 |
| CT03 | Zero hover freestream → reject freestream Cp | `test_ct03_cp_rejected_at_zero_reference` (+ `_allowed_with_declared_tip_speed`) |
| CT04 | Kinematic pressure/stress converted through density once | `test_kinematic_pressure_converted_once` |
| CT05 | Source-only rotor → source records; blade plots unavailable; prescribed T labelled input | `test_payload_lift_with_disks_never_invents_blade_pressure`, Task 7.2 tests |
| CT06 | Reflect offset force and axial moment; verify totals and cancellation | `test_ct06_reconstruct_offset_force_and_moment` |
| CT07 | Peak outside window stays an instantaneous event; phase alignment before moving-blade diffs | `test_ct07_unaccepted_window_blocks_mean_plots`, Task 11.3 tests |
| CT08 | Missing-sample mask; unclipped extrema + clipped fraction; recipe reproduces | `test_ct08_…`, `test_nans_counted_not_hidden`, Task 9.3 replay test |

### 11.3 Regression protection [M§27]

Numerical regression tests protect transformations, conservative source totals, force integrals, temporal averaging and deterministic plot selection. **End-to-end acceptance needs an actual backend run, not just configuration generation.** Reference outputs are stored with their provenance (§6.4) and the pinned image digest.

---

## §12 Risk register [M§29]

| # | Risk | Consequence | Required response | Owning tasks |
|---|---|---|---|---|
| K01 | Coarse or defective STL | Incorrect blade loading | Geometry fidelity and repair evidence | 3.2, 3.4 |
| K02 | Incorrect unit or torque sign | Orders of magnitude off, or wrong power | Dimensions and analytical fixtures | 2.2, 5.1, 5.2 |
| K03 | Prescribed thrust mistaken for prediction | False payload feasibility | Source labels and fidelity rules | 7.2, 9.2 |
| K04 | Rotor interaction omitted | Wrong thrust or download | Full installation studies | 7.3 |
| K05 | Symmetry wrongly imposed | Suppressed moments or wake modes | Physical eligibility + full-domain tests | 8.2, 8.3 |
| K06 | Wrong pressure semantics | Wrong traction and forces | Backend field definition + reconciliation | 5.2, 5.3 |
| K07 | Auto-scaled colours | Misleading design comparison | Shared ranges and saved recipes | 9.3 |
| K08 | Inadequate time window | Biased means or hidden peaks | Complete intervals and sensitivity | 11.1, 11.3 |
| K09 | Unmodelled structural deformation | Real aerodynamic shape differs | Load export + structural coupling plan | §2.3 extension interface |
| K10 | Energy–mass feedback ignored | Infeasible sizing | Coupled mass–power iteration | 12.3 |
| K11 | *(plan-specific)* LLM invents an API, constant or OpenFOAM keyword | Silent wrong code | §0 protocol, `[VERIFY-*]` tags, captured-fixture rule, cross-model review | all |
| K12 | *(plan-specific)* Greenfield deviates from the manifest's "extend existing PhysiMesh"; the client may require integration | Rework at merge time | Same language, package name, paths and platform patterns; export seam (§2.5); client sign-off (Q01) | 1.1, §2.5 |
| K14 | *(plan-specific)* 3D/transient CFD exceeds the existing 4 vCPU / 16 GB server | Release C blocked, or the temptation to shrink meshes | Measured sizing and decision gate (Task 1.4); never reduce fidelity to fit | 1.4 |
| K13 | *(plan-specific)* Client rotor/mass data arrive late | Software can be verified, aircraft cannot be evaluated | Keep status `inputs_incomplete`; continue on fixtures [M§28] | §14 |

---

## §13 Client communication

### 13.1 Claims allowed [M§29]

State the field, the model, the condition, the numerical evidence and the applicability. Template:

> *"Predicted mean rotor thrust of **{T} N** at **{RPM} RPM** under **{atmosphere}**, from **{fidelity}**, with mesh sensitivity **{GCI or change %}** and validation comparison **{dataset, error}**. Aircraft status: **{status}**."*

Every accepted plot points to the exact load table it explains.

### 13.2 Claims blocked [M§29] (never write these)

- Guaranteed 750 kg flight capability from a contour.
- Perfect first execution.
- **Zero hallucination.**
- Validated accuracy for every STL.
- Flight certification from CFD.
- Lower power inferred from smoother wake imagery.
- Motor-loss safety from summed remaining thrust alone.
- GPU acceleration [M§14].
- Any number the decision report did not produce.

**What we can honestly tell the client about AI use [M§28]:** "AI drafts code, setup proposals and explanations. Deterministic checks validate units, schemas, capabilities and provenance. Numerical solvers and validated engineering models produce every physical output. No thrust number exists without an analytical calculation, measured source or retained run."

### 13.3 Decision report template (generated by Task 12.3)

```text
PHYSICORE DRONE DECISION REPORT        study: {id}      software: {release tag} ({commit})
Aircraft status: {inputs_incomplete | screening_only | numerically_unverified |
                  validation_pending | within_validated_envelope | requirement_not_met}

1. Mass            payload 750 kg (requirement) | total {m_TO} kg ± {u} | CG {x_cg} m
2. Condition       {hover/climb/...} | rho {ρ} kg/m³ ({source}) | T {T} K | wind {…}
3. Thrust          required ΣT = m g + D_body = {…} N | predicted {…} N ({fidelity}, {applicability})
4. Power           shaft {…} kW | electrical {…} kW (η: {…}) | same case as row 3
5. Margin          (available_sustained − required)/required = {…} % (denominator: required)
6. Body download / moments   D_body,down {…} N | M_CG {…} N·m about {origin}
7. Trim            {trimmed | unreachable} | ε_F {…} ε_M {…} | active constraints {…}
8. Energy          E_mission {…} Wh | battery screen {…} kg | sizing {converged|diverged}
9. Uncertainty     iterative / discretisation / model / measurement / input, listed separately
10. Evidence       run ids, hashes, recipe ids, reconciliation status, validation campaigns
Missing inputs / blocked items: {list}  (never omitted)
```

---

## §14 Open questions and required external inputs

The manifest lists the required external inputs [M§28]: actual source repository, component STL files, rotor count and geometry or maps, mass ledger, payload position, energy system, motor limits, mission duration and environment. **Without them, the schema and fixtures can be developed, but the customer design cannot be evaluated.**

| ID | Question | Blocks | Owner |
|---|---|---|---|
| Q01 | **Client sign-off for greenfield.** The manifest says to extend the existing PhysiMesh; we build a new repository with an integration seam (§2.1, §2.5). Does the client accept this, and will they later supply the legacy source for the merge? | Contract wording; merge plan | Client |
| Q02 | Confirm the OpenFOAM distribution and release (recommendation: OpenCFD v2606) and container policy | Task 1.4 → WP04+ | Client + lead |
| Q03 | Component STL files with declared units, pitch state, separate blade/body files | WP03 real data, all CFD | Client |
| Q04 | Rotor count, geometry or measured maps (with the metadata in Task 6.2), airfoil polars | WP06, WP10 | Client |
| Q05 | Mass ledger by category, CG, inertia, uncertainty; payload position(s) | 2.4 real data, WP12 | Client |
| Q06 | Energy system (pack specific energy, usable fraction, reserve policy), motor and inverter maps, sustained/peak limits, thermal limits | WP12 | Client |
| Q07 | Mission profile: duration, segments, environment envelope (temperature, density, crosswind, ground clearance) [M§2] | WP07, WP12 | Client |
| Q08 | Validation data: rotor stand measurements or an approved public dataset (licence) | 6.4, 10.1, Release C | Client + lead |
| Q09 | Tolerances with no manifest value: BEM induction relaxation, vortex-ring flag threshold, AMI weight-sum band, Stokes-fixture acceptance (proposed 5 %/3 %) | 6.3, 6.4, 10.2, 4.5 | Lead engineer |
| Q10 | The manifest refers to a "companion YAML template" [M§0] that was **not supplied**. Appendix A is a reconstruction. Please send the original so it can be reconciled. | 2.5 | Client |
| Q11 | ~~Existing frameworks~~: **resolved** by the greenfield stack (§6.0). Remaining: which git host and CI the client wants | 1.1 | Client |
| Q12 | Compute for 3D and transient campaigns. The existing server is 4 vCPU / 16 GB / 50 GB, sized for 2D. Task 1.4 measures the real need; the client decides whether to add a compute host before Release C | 1.4 gate, WP10–11 | Client |

---

## §15 Traceability matrix

| Requirement [M§2] | Acceptance evidence (manifest) | Tasks | Fixture/test |
|---|---|---|---|
| REQ01 Treat 750 kg as payload | Mass ledger, total mass with units | 2.4, 2.5, 12.3 | `test_payload_must_equal_requirement`, `test_payload_weight_fixture` |
| REQ02 Import ASCII and binary STL | Unit/geometry fixtures + 3D preview | 3.1, 3.2, 3.5 | parser tests, viewer checklist |
| REQ03 Separate stationary and rotating parts | Tagged assembly, rotor-zone validation | 3.3, 4.2, 10.1 | `test_rotor_needs_rotation_zone…`, rotation-zone intersection test |
| REQ04 Predict thrust and shaft torque | Measured map or validated rotor model | 6.1–6.4, 10.1–10.2 | BEM tests, rotor-stand campaign |
| REQ05 Full-vehicle aero loads | Body, rotor, total forces without duplication | 5.1–5.4, 7.3 | ledger tests, hover interference |
| REQ06 Detect and execute valid symmetry | Transformation tests + full-domain comparison | 8.1–8.3 | symmetry tests, backend comparison |
| REQ07 Power and mission energy | Component limits + energy balance | 12.1–12.3 | mission toy cases, report tests |
| REQ08 Mesh and time sensitivity | Controlled refinement campaigns | 4.2, 11.1, 11.2 | GCI tests, campaigns |
| REQ09 Physically relevant plots | Field, unit, time, capability checks | 5.5, 9.1–9.4 | CT01–CT08 |
| REQ10 Reproducibility | Input, geometry, mesh, backend, recipe hashes | 2.1, 4.3, 9.3 | provenance tests, recipe replay |
| REQ11 Preserve 2D behaviour | Existing regression checks → **adapted:** legacy product untouched; integration only via export seam | 1.1, §2.5 | Separate repository; export-format contract test (Task 9.4) |
| REQ12 Report failed/unsupported work honestly | Explicit statuses, blocked claims | 2.5, 4.4, 9.2, 12.3, §13 | status-ceiling tests, `Unavailable` paths |

### Manifest section coverage check

§1 → §2 (incl. §2.5–2.6), WP01. §2 → §4, §15, Task 12.3. §3 → Task 2.3, §3. §4 → Task 2.4. §5 → Tasks 12.1–12.2. §6–§7 → WP06. §8–§9 → backend rows of §7, Task 5.2 Step 3, Task 4.3. §10 → Tasks 7.1, 10.1, 10.2. §11 → WP03. §12 → WP08. §13 → Tasks 4.2, 7.3. §14 → Tasks 4.3, 10.2. §15 → WP11. §16–§17 → WP05, Task 12.3. §18–§24 → WP09, Task 5.5. §25 → §6.2. §26 → Tasks 2.5, 4.1, endpoints in 3.5/4.5/7.3/8.2/9.4. §27 → §9, §11. §28 → §1.5, §9.2, §14. §29 → §12, §13. §30 → §7, references. §31–§32 → §8. §33 → §11.2.

---

## Appendix A: Draft project YAML `drone_manifest_v1`

> **Reconstructed** from the required groups in [M§26] and the settings registers in [M§31]–[M§32], because the manifest's companion template was not supplied (Q10). `null` = required data not supplied; it blocks the dependent run or decision. This is an **application contract**, not an OpenFOAM or SU2 input deck [M§0].

```yaml
identity:
  schema_version: drone_manifest_v1
  study_id: null
  description: null
  created_utc: null

units_and_frames:
  source_units: null              # m | mm | cm | in | ft  -- never inferred
  world_frame: ENU_z_up
  body_frame: x_forward_y_left_z_up
  solid_normal: outward_into_fluid
  cad_transform: {scale: 1.0, rotation_deg_zyx: [0, 0, 0], translation_m: [0, 0, 0]}

mission:
  payload_mass_kg: 750
  payload_positions_body_m: null  # list of candidate CGs for payload
  cases:                          # [M§2] required environmental cases
    - {name: hover_nominal, kind: hover, velocity_world_m_s: [0, 0, 0], attitude_deg_zyx: [0, 0, 0],
       acceleration_target_m_s2: [0, 0, 0], ground_clearance_m: null, mass_state: max}
  duration_s: null
  reserve_policy: null            # e.g. {kind: fraction, value: null}

masses:
  items: []                       # {name, category, mass_kg, cg_body_m, inertia_own_cg_body_kgm2, uncertainty_kg, state}

atmosphere:
  source: null                    # "ISA troposphere" | "measured ..." (provenance text)
  altitude_m: null
  pressure_pa: null
  temperature_k: null
  viscosity: null                 # {law: sutherland} or {value_pa_s: ...}
  humidity_assumption: null
  gamma: 1.4

assembly:
  geometry_revision_sha256: null
  components: []                  # {component_id, role, rotor_id, requires_user_tag}
  topology_tolerance: {abs_m: null, rel: null}
  min_feature_m: null

rotors: []                        # {rotor_id, center_body_m, axis_body, signed_rpm, pitch_deg, n_blades,
                                  #  radius_m, root_cutout_m, azimuth_zero_deg, phase_offset_deg,
                                  #  model: measured_map|bem|actuator_disk|actuator_line|blade_resolved,
                                  #  map_ref, blade_ref, polar_ref, sustained_limits, peak_limits}

flow:
  compressibility: null           # decided from local blade Mach (capability decision)
  turbulence_model: null          # pinned backend SST variant for RANS tests
  pressure_includes_isotropic_turbulent_stress: null
  ambient_turbulence: {intensity: null, length_scale_m: null, reference_speed_m_s: null}

fidelity:
  initial: null                   # measured_map | bem
  requested_question: null        # engineering intent driving fidelity selection
  bem: {radial_stations: 80, relative_load_residual: 1.0e-4, max_iterations: 200,
        induction_relaxation: null, loss_model: prandtl_tip, loss_applies_to: momentum,
        polar_extrapolation: reject}

symmetry:
  execution: "off"                # quoted: bare off is boolean false in YAML 1.1
  plane: {x0_m: null, normal: null}
  match_tolerance: {abs_m: null, rel: null}

domain:
  bounds_m: null
  clearances_in_rotor_diameters: null

mesh:
  global_cell_m: null
  surface_levels: {}
  wake_refinement: []
  rotation_zones: {}
  layers: {first_layer_yplus_target: 1, growth: 1.2, count: null, first_height_m: null}
  max_cells: null

numerics:
  steady: {coupling: SIMPLE_or_backend_equivalent, iteration_budget: 3000}
  transient: {coupling: PIMPLE_or_backend_equivalent, rotation_per_step_deg: 1, target_courant: 0.8,
              outer_correctors: 2, pressure_correctors: 2}
  linear: {final_rel_tol: 0, p_abs_tol: 1.0e-7, u_turb_abs_tol: 1.0e-6}
  relaxation: null                # conservative initial values, versioned

boundaries:
  far_field: null
  outlet: null
  ground_model: null              # explicit per case
  walls: null

convergence:
  startup_discard_revs: 5
  averaging_window_revs: 10
  force_drift_gate: 0.005
  continuity_target: 0.001
  m_dot_scale: null

postprocessing:
  load_history_cadence: every_time_step
  full_field_cadence_deg: 5
  intents: []

validation:
  native_force_reconciliation: {rel: 0.001, abs_n: null}
  mesh_time_change_target: 0.02
  symmetry_change_target: 0.01
  experimental_targets: {thrust_rel: 0.05, torque_rel: 0.10}   # proposed, not demonstrated [M§15]

execution:
  backend_name: null
  backend_version: null
  backend_image_digest: null
  cpu_cores: null
  memory_gb: null
  disk_gb: null
  wall_time_limit_s: null
  limits: {max_upload_bytes: null, max_triangles: null}
```

---

## Appendix B: Role prompts [M§28]

The manifest defines five roles. "Responsibilities describe tasks, not independent certification." Put the role prompt at the top of the model session, before the task prompt in §1.2.

### B.1 Physics role

```text
ROLE: Physics. You define equations and assumptions. For every formula you use, cite plan.md §7 ID
([M-Exx]) and state its validity limits from the manifest. You must not introduce an equation, constant
or coefficient that is not in plan.md §7, the manifest, or a cited standard ([STD]) with its exact value.
List every assumption separately and mark it [ASSUMPTION].
```

### B.2 Numerical role

```text
ROLE: Numerical. You check discretisation, convergence and uncertainty. Separate iterative,
discretisation, model, measurement and input uncertainty. A resource cap is not convergence. A small GCI
does not establish physical accuracy. Refuse to promote evidence level without the records in plan.md §4.3.
```

### B.3 Geometry role

```text
ROLE: Geometry. You preserve CAD. Never close holes, merge surfaces or delete parts to make a mesh pass.
Every change is a new GeometryRevision with metrics. Units are never inferred. Rotation metadata never comes
from geometry alone.
```

### B.4 Software role

```text
ROLE: Software. You implement contracts exactly as specified in the task's Interfaces block. Before editing
an existing file, quote the lines you will change. If the real code differs from the plan, stop and report
under BLOCKED / QUESTIONS. Tests first; paste real command output. Do not add dependencies that are not
listed in the task.
```

### B.5 Critic role (mandatory for ⚠ tasks)

```text
ROLE: Critic. Assume the diff is wrong until shown otherwise. Check:
1. Every constant/formula has a source tag and matches plan.md §7 / §7.3 values.
2. Signs: normals (solid->fluid), torque (aero resisting vs shaft), axial vs polar vectors.
3. Units: kinematic vs Pa pressure converted exactly once; SI everywhere.
4. No null replaced by a default; no status upgraded without its gate.
5. Tests: did expected values change? (If yes, reject unless a human approved the derivation.)
6. Unsupported claims in docstrings, logs or report text (plan.md §13.2).
Output: APPROVE or REJECT with numbered findings, each with file:line and a concrete failure scenario.
```

---

## Appendix C: Glossary

| Term | Meaning |
|---|---|
| AMI | Arbitrary Mesh Interface: OpenFOAM sliding interface between rotating and static mesh regions. Not a mirror boundary [M§10] |
| BEM | Blade Element Momentum theory (E11–E14) |
| Body download | Downward aerodynamic force on the airframe from the rotor wake, which raises the thrust required (E07) |
| CG | Centre of gravity |
| Cp | Pressure coefficient (E50). Undefined in hover with a freestream reference |
| FM | Figure of merit (E10). Isolated-hover metric only |
| GCI | Grid Convergence Index (E40) |
| MRF | Multiple Reference Frame: steady rotating-frame approximation ("frozen rotor") |
| Native face data | The solver's own boundary-face values, before any interpolation or smoothing |
| Prescribed vs predicted | An actuator disk's thrust that was *given* as input vs thrust *computed* by a model |
| RANS / SST | Reynolds-Averaged Navier–Stokes / Shear Stress Transport k-ω turbulence model |
| Reconciliation | Comparing our face integral with the backend's own force output (0.1 % + abs) |
| Recipe | Stored, hashable description of a plot, enough to reproduce it exactly |
| y⁺ | Dimensionless wall distance of the first cell (E27) |

---

## Self-review record (performed while writing)

1. **Spec coverage:** every manifest section 1–33 maps to a task (§15 coverage check). REQ01–REQ12 are each traced.
2. **Placeholder scan:** no "TBD" or "implement later". Real unknowns are `null`, `[OPEN-QUESTION]` (listed in §14) or `[VERIFY-*]` with the exact verification procedure.
3. **Type consistency:** names in the Interfaces blocks match `reference_impl/` (checked by running its 118 tests).
4. **Review focus:** the five §5 failure modes each have a test in their owning task.
5. **Numbers:** every number in §7.3 and in the reference tests was computed by executing code on 2026-10-02, not written from memory.

---

## References (copied from the manifest [M§30])

- **R1** OpenCFD snappyHexMesh documentation: STL surface-based volume meshing. https://doc.openfoam.com/2606/tools/pre-processing/mesh/generation/snappyhexmesh/
- **R2** OpenCFD rotating fan tutorial: rotating mesh and arbitrary mesh interface example. https://doc.openfoam.com/2212/examples/tutorials/incompressible/pimpleFoam/ami-rotating-fan/
- **R3** SU2 actuator disk variable load tutorial. https://su2code.github.io/tutorials/ActuatorDisk_VariableLoad/
- **R4** W. Johnson, NDARC NASA Design and Analysis of Rotorcraft, Theory Appendix 1, NASA/TP-2015-218751. https://ntrs.nasa.gov/citations/20160012474
- **R5** Bangura, Melega, Naldi, Mahony, *Aerodynamics of Rotor Blades for Quadrotors*, 2016. https://arxiv.org/abs/1601.00733
- **R6** NASA NPARC Alliance, *Examining Spatial Grid Convergence*. https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html
- **R7** OpenCFD forces function documentation (density and pressure handling must be verified against the selected release). https://www.openfoam.com/documentation/guides/latest/doc/guide-fos-forces-forces.html
- **R8** ParaView reference manual: colour maps and transfer functions. https://docs.paraview.org/en/latest/ReferenceManual/colorMapping.html

Additional standard sources used in this plan, tagged `[STD]`: standard gravity 9.80665 m/s²; ISA troposphere (288.15 K, 101325 Pa, 0.0065 K/m); Sutherland's law for air (μ_ref 1.716e-5 Pa·s, T_ref 273.15 K, S 110.4 K); Stokes/Oseen sphere drag; Ericson's closest-point-on-triangle algorithm (*Real-Time Collision Detection*, §5.1.5); Leishman's closed-form BEMT inflow (*Principles of Helicopter Aerodynamics*), used only as an iteration starting point.
