# Independent physics review: 3-day MVP (sphere pipeline + labelled screening)

| Item | Value |
|---|---|
| Repository | `/Users/bhupeshcholake/Desktop/Claude Codes/physicore drone` |
| Branch / commit | `mvp/3day` @ `6dd6dfc19690a595844dc2b30fff844d07684879` (working tree clean except two `.DS_Store` files) |
| Reviewer | Claude Opus 5.5 (`claude-opus-5-5`), Anthropic: a different model family from the implementing GPT agent, as `plan.md` §1.5 requires |
| Date | 2026-10-03 |
| Authorization | Explicit user request. Write-only scope: this file. No code, solver-input, evidence-status, merge, tag or push changes were made |
| Scope | Bounded sphere Re = 100 verification pipeline (run group `.backend/demo-load-history/run_group.json`, package `.backend/demo-final/results/acd1b8716144aeaa`) and the labelled illustrative payload screening. **Not** aircraft validation, rotor CFD, or human engineering certification |

**Independence disclosure.** In earlier sessions the same reviewer authored `plan.md`, the 3-day plan, and `reference_impl/` (from which `loads3d.py`, `statistics.py` and `contour_rules.py` were ported). Review of that ported code is therefore not fully independent. To compensate, the key load results were re-derived with a **separate, newly written parser and integrator that does not import `physimesh`** (§2.1), and sign/area conventions were checked against the **OpenFOAM v2606 source code** in the retained vendor archive rather than against my earlier code or memory. A human engineer's review remains advisable for certification-level use.

---

## 1. Verdict

**CONDITIONAL PASS** for the bounded scope: the sphere pipeline as a *software verification demonstration*, and the screening panel as a *labelled illustrative calculation*.

- **No Critical or High findings.** Units, frames, sign conventions, pressure/density handling, native-face integration, reconciliation, drift windows, unequal-ratio GCI arithmetic, slice-caveat figures, the screening minimum and missing-case refusal all reproduce independently.
- **Conditions before showing to the client** (Medium findings F1–F3):
  1. **F1:** present the GCI with a conservative bound at formal order, not only the 0.11 % value from the observed order 4.33.
  2. **F2:** gate supplied electrical power against the isolated ideal-hover lower bound, or label clearly that the power figures are unchecked supplied data.
  3. **F3:** correct the stop-rule description in two documents.
- Evidence status should remain `unverified`. This review does not upgrade any status, and none of the checks below justify a higher one.

---

## 2. Checks actually performed

### 2.1 Native loads: independent re-derivation (all three meshes)

A new script (scratch, not committed) parsed `constant/polyMesh/{points,faces,owner,boundary}`, final-time `p` and `wallShearStress` directly. It computed face areas and centres, converted kinematic → physical with ρ = 1, applied the solid-normal and shear sign conventions, and integrated force and origin moment. Results versus the native `forces`/`forceCoeffs` final rows:

| Mesh | Cells | Sphere faces | Area / πD² − 1 | Cd (independent) | Cd (native) | max rel. err Fₓ | max abs err M (N·m) |
|---|---:|---:|---:|---:|---:|---:|---:|
| coarse | 80,473 | 1,784 | −0.198 % | 1.1468925753 | 1.146892575342 | 1.9e-13 | 1.1e-14 |
| medium | 251,192 | 3,960 | −0.110 % | 1.1249130055 | 1.124913005521 | 1.1e-13 | 3.8e-15 |
| fine | 804,280 | 8,832 | −0.068 % | 1.1206201832 | 1.120620183217 | 3.9e-14 | 2.7e-15 |

- Closure |Σ Sf| ≤ 1.2e-15 m² on all meshes (closed surface).
- Fine-mesh split: Cd_pressure 0.52446, Cd_viscous 0.59616 (independent), matching the solver log (`0.524455905674`, `0.596164277542`).
- The published package `results.json` Cd values equal these to within floating-point rounding.

### 2.2 Conventions checked against OpenFOAM v2606 source (vendor archive SHA-256 `2a1310e3…294d`)

| Convention | Source evidence | Code | Verdict |
|---|---|---|---|
| Face area and centre | `primitiveMeshTools::makeFaceCentresAndAreas`: triangles direct; polygons fan about the point average, weight `a = mag(n)`, `Sf = 0.5 ΣN` | `solver/foam_ascii.py:206-226` | Matches exactly |
| Boundary Sf direction | out of the fluid domain (into the solid) | negated once, `loads3d.solid_area_vectors_from_backend` | Correct |
| `wallShearStress` sign | `ssp = (-Sfp/magSfp) & Reffp` with `devReff` (`wallShearStress.C:77`) ⇒ equals the negative of the viscous traction on the solid | negated once, `postpro/results.py:90` | Correct; also independently confirmed by viscous-force reconciliation |
| Pressure dimensions | `p`, `wallShearStress` = `[0 2 -2 0 0 0 0]` (kinematic) on all meshes | ×ρ once, dimensions-driven (`loads3d.to_physical_pressure`) | Correct |
| zeroGradient wall pressure | patch value = owner-cell internal value | `foam_ascii.py:185-200` | Correct, and consistent with the native force |
| p_ref = 0 | closed surface, so the constant cancels | `results.py:90` | Correct for a closed patch |

### 2.3 Case definition (fine-mesh dictionaries read directly; all three cases checked for U, ν)
- Freestream `(1 0 0)` m/s, ν = 0.01 m²/s, D = 1 m ⇒ **Re = 100** on all three meshes.
- `forceCoeffs`: ρ∞ = 1, magUInf = 1, Aref = π/4, dragDir (1 0 0), CofR origin. These are consistent with the Cd definition used in `results.py:102`.
- BCs: inlet fixedValue U / zeroGradient p; outlet inletOutlet U / fixedValue p = 0; lateral `slip`; sphere `noSlip`. Laminar, `simpleFoam` steady.
- Schemes: `bounded Gauss linearUpwindV grad(U)` with `cellLimited Gauss linear 1` gradient; linear corrected Laplacian ⇒ **formal order ≤ 2**.
- Mesh: blockMesh 64/96/144 × (½)² background, snappy surface level (4 4), `addLayers false`.

### 2.4 Convergence and drift
- Final residuals ≤ ~1.2e-7 initial / ~1.5e-8 final for p and U components (all meshes).
- Drift gate: windows 412–612 and 612–812 (201 samples each; they share the 612 sample). Drift 2.6e-9 / 8.5e-11 / 3.4e-10, gate 0.5 %. Reproduced from the stored windows. The `forceCoeffs` running mean at iteration 400 already equals the final Cd to 9 significant figures, so the acceptance windows sit well inside a converged plateau.
- Stop logic read from `system/runTimeControls`, the solver log and the v2606 source. See **F3**.

### 2.5 Mesh study (unequal ratios)
Re-implemented Celik et al. (ASME JFE) iterative order solution independently, with h ∝ N^(−1/3):

| Quantity | Independent | Package |
|---|---|---|
| r₂₁ / r₃₂ | 1.473897069 / 1.461454181 | same |
| observed order p | 4.326944948 | 4.3269449477 |
| f_ext | 1.119634987 | 1.1196349868 |
| GCI_fine (Fs 1.25) | 0.001098941 | 0.0010989410 |

Additional calculations (not in the package): GCI_fine with p capped at formal order 2 is **0.408 %**; with p = 2 and Fs = 3 it is **0.98 %**; with p = 1 it is 1.01 %. The Celik asymptotic indicator GCI₃₂/(r^p GCI₂₁) = 0.996. That indicator is nearly an identity when p is fitted from the same three values, so it is **not** independent evidence of the asymptotic range.

### 2.6 Correlation comparison
- Schiller–Naumann at Re = 100: Cd = 1.09173 (recomputed).
- Fine Cd is +2.646 % above it; f_ext is +2.556 % above it.
- Even the most conservative discretization bound above (≈ 1 %) does not account for the gap.
- **No domain-size, blockage, outlet-distance, surface-faceting or correlation-scatter study was run, so the cause of the gap is not established.** I searched the docs, web and src for any attribution of the gap to domain size and found none. Only the planned blockage ratio (0.196 %, a geometric fact) is stated.

### 2.7 Interpolation versus native integration; slice caveat
- Loads are integrated only from native face data (`results.py:83-90`). The 3D surface uses native face-constant values on a display triangulation (`scripts/demo_surface.py:41-56`). Slices use OpenFOAM `cellPoint`-interpolated cutting-plane samples, then linear `griddata` (`postpro/plots.py:168-193`), labelled "visualization only".
- Independently measured max |y| on the y = 0 raw samples: 2.5326e-6 / 9.2787e-6 / 4.7022e-6 m (coarse/medium/fine). This matches `sphere_re100_plot_review.md`. Deviations are smaller away from the body (≤ 2.8e-6 m at r > 0.6 D). Cause not established; see F7.

### 2.8 Screening (illustrative, `screening_only`)
- Hand recomputation of the headline:
  - empty mass = 65 kg;
  - **hover**: (4·350 − 40) N / 9.80665 = 138.68 kg supported → margin 73.68 kg;
  - **climb**: (4·320 − 60) N / (9.80665 + 0.6) = 117.23 kg supported → margin **52.23 kg**;
  - minimum = climb, which matches the API's 52.232730994 kg.
- Power: 24.0 / 22.4 kW ≤ 28 kW available, and each rotor ≤ 7 kW sustained. Energy: 7.20 / 4.03 MJ ≤ usable 11.52 MJ (= 20 kg × 250 Wh/kg × 0.8 × 0.8 × 3600).
- The minimum is taken across **all** declared cases (`screening.py:96-221`). A missing declared case → blocking with no headline (`screening.py:127-129`). Undeclared inputs, duplicates, unbound hashes, snapshot mismatch, and acceleration/duration/power mismatches all block (`api/screening.py:48-127`). A negative margin gives `requirement_not_met` with a 0 kg display (`screening.py:216-218`). Tests `test_lowest_case_governs_capacity`, `test_missing_mission_case_blocks_headline` and their API counterparts exist and pass.
- Mass ledger: `mission.payload_mass_kg` must match the ledger payload when supplied (`models.py:211-234`). Empty mass = total − installed payload (`mass.py:43-47`). No STL-derived mass.
- Diagnostics recomputed: tip Mach 0.300 (1500 RPM, R = 0.65 m, ISA). Isolated ideal-hover power 3631 W at 350 N against 6000 W supplied, so the implied FM·η is 0.605. These are physically plausible for the example.
- Separate battery-loop fixtures reproduce `plan.md` §7.3 exactly: A converged 10 iterations, 1442.1503 kg; B converged 107 iterations, 3066.9058 kg; C diverged at iteration 6. They are labelled as separate from the four-rotor example (`demo_screening.py:67-91`, `results.html` "A separate battery-sizing exercise").

### 2.9 UI and published claims (visible text of `web/results.html`, dynamic strings in `web/js/results.js`, package `results.json`)
- Banners present: "VERIFICATION CASE: sphere at Re=100. No aircraft result."; "Illustrative example inputs, not the client's aircraft."; "Independent physics review is pending. This sphere case does not validate drone performance."; "Reading an STL does not create a valid CFD case."
- The mesh text includes "This is not a total accuracy claim" and the qualification string.
- Package limitations list: GCI excludes domain, boundary, model and geometric errors; the asymptotic range is not demonstrated.
- No "validated", "accurate", "certified", "can carry" or fixed 750 kg claims found in the page text. No 750 kg target appears in screening (ADR-0002).

### 2.10 Package integrity and tests
- `hashes.json`: 33/33 files match their SHA-256.
- `run_group_sha256` prefix = package ID `acd1b8716144aeaa`.
- Re-ran locally: `pytest -q -m "not backend"` gave **285 passed, 3 deselected**; `ruff check .` passed.

### 2.11 Not performed by this reviewer (relied on project records only)
- Backend (Docker/OpenFOAM) tests were not re-run.
- The fresh clone was not reproduced.
- The GitHub Linux CI runs (37047628955) were not accessed.
- The browser UI was not exercised interactively.
- The ZIP download in a browser was not tested.

These are recorded in `docs/qa/fresh_clone_reproduction.md` and `results_page_checklist.md` and are **not** independently confirmed here.

---

## 3. Findings

Severity scale: Critical (wrong physics reaches a user), High (likely wrong result or claim), Medium (credible risk of misleading a technical client; fix before demo), Low (accuracy, robustness or wording improvement).

| ID | Severity | Location | Finding | Recommendation |
|---|---|---|---|---|
| **F1** | **Medium** | `web/js/results.js:15`; `postpro/interpretation.py` mesh sentence; `results.json` `mesh_study` | The headline uncertainty "fine GCI 0.110 %" uses observed order p = 4.33, more than twice the formal order (≤ 2) of the schemes used. A GCI with p capped at 2 is 0.41 % (0.98 % with Fs = 3). The qualification text is present but the optimistic number dominates. A technical client is likely to challenge it. | Show the GCI at p = min(p_obs, 2) as the primary figure (or alongside), and state that p_obs exceeds formal order. No solver change needed. |
| **F2** | **Medium** | `drone/screening.py:169-198`; `drone/screening_diagnostics.py:45-48` | Supplied electrical power is checked against sustained limits and energy, but not against physics. Electrical power below the isolated ideal-hover lower bound (momentum theory) would be physically impossible, yet would pass the power and energy gates, making an infeasible energy case look operable. The bound is already computed as a diagnostic, but it doesn't gate. The example passes (6000 W > 3631 W). | For hover cases, block or flag `physically_inconsistent_power` when P_elec < P_ideal (as `figure_of_merit` already flags FM > 1). Otherwise label the power and energy gates as "supplied data, not physics-checked". |
| **F3** | **Medium** (documentation accuracy) | `docs/technical/mvp-code-and-physics-guide.md:335-337`; `docs/validation/sphere_re100_runs.md:9-10`; `system/runTimeControls` | The docs say the controller waits for "a 400-step drag-average window within an absolute range of 1e-3". The v2606 source (`averageCondition.C:57,77`, `valueAverageBaseTemplates.C:153`) shows it checks `delta = |running mean − current Cd| < 1e-3` after `nIterStartUp` (default 10). The log shows it satisfied at iteration 412 (delta 7.1e-10), 12 iterations after `timeStart 400`, so all three meshes stop at 812. Acceptance is unaffected (the independent drift gate and residuals pass), but the stated procedure is not what ran. | Correct both documents to the actual criterion. If a 400-iteration range criterion is wanted, it needs a different controller. |
| F4 | Low | `postpro/results.py:109-112` | The moment reconciliation uses `abs_tol = 1e-6 N·m`, which is about the size of the sphere's origin moments (1e-10 to 4e-6 N·m). That gate cannot detect even 100 % moment errors. Actual agreement is ~1e-15, so the published claim is true, but the gate isn't discriminating. | Scale abs_tol for moments to the problem (e.g. 1e-9·|F|·D) and report achieved errors. |
| F5 | Low | `drone/screening.py:192-198, 212-215` | When the stated limit point exceeds available power or usable energy, the report status is `inputs_incomplete`. It fails safe (no capacity shown), but a reader may take that to mean missing data rather than "infeasible at the supplied operating point". | Use a distinct reason or status such as `operating_point_infeasible`, keeping no headline. |
| F6 | Low | `drone/demo_screening.py:29-30, 61` | The illustrative climb case pairs velocity 2 m/s with a sustained vertical acceleration of 0.6 m/s² for 180 s (implying Δv = 108 m/s). The force balance is instantaneous, so the arithmetic is right, but the case is not a physically consistent mission segment, and it is the limiting case on screen. | Recast it as a short acceleration-margin case, or give steady climb a_z = 0 with its own duration. Keep the label. |
| F7 | Low | `scripts/demo_plots.py:52-54`; `postpro/plots.py:182` | The slice tolerance 1e-5 D was set after observing the data. The medium mesh uses 93 % of it (9.28e-6 m). The cause of the off-plane coordinates is not established. Visual only, with no effect on loads. | Record the tolerance as post hoc, and fail on regression rather than widening it. |
| F8 | Low | `api/screening.py:62-64` | `usable_energy_j` is accepted from `energy_system` without a cross-check against the ledger's energy-category mass × pack Wh/kg × usable fraction × (1 − reserve). The example happens to be consistent (11.52 MJ). The reserve convention (fraction of usable pack energy) differs from `plan.md` E47 (reserve as a fraction of mission energy) and is not stated on screen. | Add a consistency check or explicit derivation; state the reserve convention. |
| F9 | Low | `postpro/interpretation.py:24` | Drift is printed with `:.2%`, so "0.00 % change" displays for drifts of 1e-10. True, but it can read as exactly zero. | Use scientific formatting for small values. |
| F10 | Low | `postpro/result_contract.py:40,85` | The package status `numerical_checks_passed` is a new term outside `plan.md` §4. Evidence correctly remains `unverified`, but the label could be read as a positive evidence level. | Document the term in §4 or rename it, e.g. `software_checks_passed`. |
| F11 | Low (scope limit) | `drone/screening.py:200-204` | Capacity uses only the world-z force balance. Horizontal force and moment balance (trim) are not checked, so tilted rotors or side force would go unnoticed. This is documented in the docstring and assumptions. | Keep it labelled. Trim belongs to master-plan WP12. |

No findings on: SI/frame conventions; kinematic pressure conversion (applied exactly once); solid-normal and shear sign; face area/centre algorithm; zeroGradient wall value; Cd definition; window construction; unequal-ratio GCI arithmetic; minimum-across-all-cases logic; missing-case refusal; source-hash binding; ledger payload semantics after ADR-0002; separation of the battery fixtures from the four-rotor example.

---

## 4. Unresolved limits (true regardless of fixes)

1. **The +2.6 % gap to Schiller–Naumann is unexplained.** No domain, blockage, outlet, surface-faceting or correlation-uncertainty study was run. Its cause must not be stated. The correlation is an empirical comparison, not ground truth.
2. **Asymptotic convergence is not demonstrated.** Three meshes with p_obs = 4.33 and fixed surface levels can't establish it. Near-wall resolution is modest: no prism layers, and the fine level-4 surface cells are ≈ D/58. The viscous drag share is 53 %.
3. **This is a steady laminar verification case.** It says nothing about rotors, turbulence, transients or a drone.
4. **Screening uses synthetic supplied performance points.** The rotor performance, body force and energy values are examples. No real rotor map, geometry or mass data exist. 52.23 kg is a labelled illustrative `screening_only` number, not an aircraft capacity.
5. **Not independently confirmed by this reviewer:** backend re-runs, fresh-clone reproduction, Linux CI, interactive browser behaviour and ZIP download (§2.11).
6. **Partial independence:** see the disclosure at the top. A human engineer's sign-off is still advised before any external engineering use.

---

## 5. Explicit scoped verdict

| Scope item | Verdict |
|---|---|
| Native load integration, sign/pressure/density conventions, reconciliation with OpenFOAM | **PASS** |
| Convergence evidence (residuals, drift gate) | **PASS**; stop-rule documentation incorrect (F3) |
| Unequal-ratio GCI arithmetic | **PASS** |
| GCI presentation and high-order qualification | **CONDITIONAL** (F1) |
| Interpolation vs native separation; slice caveat | **PASS** (F7 low) |
| Screening arithmetic, minimum across all declared cases, missing-case refusal | **PASS** |
| Screening physical-consistency gates (power/energy) | **CONDITIONAL** (F2; F5, F8 low) |
| Battery-loop fixtures (separate, labelled) | **PASS** |
| UI and package claims | **PASS** (banners and limitations present; F9, F10 low) |
| **Overall, bounded MVP scope** | **CONDITIONAL PASS**: resolve F1–F3 (or explicitly disclose them) before client presentation. Evidence remains `unverified`. Not an aircraft validation or certification. |

---

## 6. Follow-up review, 2026-10-03: candidate `f19cbebddffaf788df76f8a5cd35adf8b99d3cea`

| Item | Value |
|---|---|
| Candidate | `mvp/3day` @ `f19cbebddffaf788df76f8a5cd35adf8b99d3cea` (one commit after reviewed `6dd6dfc`: "fix(mvp): address independent physics review conditions"); working tree clean except `.DS_Store` |
| Reviewer | Claude Opus 5.5 (`claude-opus-5-5`) |
| New package | `.backend/demo-reviewed/results/acd1b8716144aeaa` |
| Scope | Verify F1–F3 and F9 fixes and the documentation clarifications. Write-only: this section. No code, solver, input, status, merge, tag or push changes. Not aircraft validation |

### 6.1 Integrity of this review file
The candidate commit adds this file for the first time. Its committed content (170 lines, SHA-256 `359339749f1f…93fc80`) is byte-identical to the file as I wrote it. Nothing was altered by the implementing agent.

### 6.2 Checks performed
1. `git diff 6dd6dfc f19cbeb` read in full for `src/`, `scripts/`, `web/` and `tests/`, plus the changed lines in `docs/technical`, `docs/validation`, `docs/plans` and `README.md`. Eighteen files changed. No changes to the solver case generator, native readers, load integration, runner or any retained run input or output.
2. **F1 numbers recomputed independently** from cell counts and Cd: r₂₁ = 1.4738970688, p_used = min(4.3269449, 2) = 2, Fs = 1.25, giving GCI_fine = **0.004084405348574** (0.408440535 %). Package value: 0.004084405348580 (agrees to 6e-15). `order_capped_gci` (`postpro/statistics.py:92-108`) implements 1.25·|(f₁−f₂)/f₁|/(r₂₁^p − 1) via `expm1`, with explicit validation and no defaults for the cap or safety factor. The analytical test f(h) = 100 + h⁴ checks that a high observed order cannot reduce the capped estimate.
3. **New package** `demo-reviewed/…/acd1b8716144aeaa`:
   - `hashes.json` 33/33 SHA-256 match.
   - Status `numerical_checks_passed`, evidence `unverified` and `independent_review: pending` are all unchanged (no status upgrade).
   - Per-mesh Cd, reconciliation status, drift and `source_sha256` of all native inputs are identical to the original package (native runs unchanged).
   - `mesh_study` retains the observed-order GCI 0.0010989410 and adds `order_capped_gci_fine`, `gci_order_used = 2`, `nominal_order_cap = 2`, `gci_safety_factor = 1.25`, the cap source and the estimator code hash.
   - The original package `demo-final/…/acd1b8716144aeaa` still verifies 33/33 and is unmodified (no cap fields).
4. **Mesh chart** `plots/mesh_cd.png` inspected visually. The fine bar carries a small error bar (expected ±1.1206 × 0.0040844 = ±0.00458). The caption reads "Error bar uses order-capped GCI (nominal cap 2, safety factor 1.25); qualified mesh sensitivity, not total uncertainty or a proven error bound." The code source is `scripts/demo_plots.py:128-131`.
5. **UI text** `web/js/results.js:15`: the order-capped GCI is shown first, followed by the observed order and observed-order GCI, ending with "These estimates are not total accuracy or proven error bounds." Interpretation sentence in the package: "order-capped GCI 0.408% at order 2.000; observed order 4.327, observed-order GCI 0.110%. …".
6. **F2 label:**
   - `web/results.html:13`: "Power and energy checks use supplied data. Their physical validity is not assessed."
   - `api/screening.py` assumptions (rendered under every capacity result): "Electrical power and usable energy are supplied data, not physically validated; limit checks alone do not prove operability." and "Isolated ideal-hover power is a diagnostic; ground effect and rotor interference are not modelled."
   - This is the allowed alternative in F2 (labelling instead of a physics gate). The capacity arithmetic is unchanged.
7. **F3 wording** in `docs/technical/mvp-code-and-physics-guide.md` (§9) and `docs/validation/sphere_re100_runs.md` checked against the v2606 source and log evidence in §2.4/F3: start 400, `window=400`, `windowType=exact`, default `nIterStartUp=10`, test `|running mean Cd − current Cd| < 1e−3` (no full-window or range test), trigger at 412, then 400 further iterations to 812. **Accurate.** Both documents state that no retained input or output was changed.
8. **F9:** `postpro/interpretation.py:24` formats drifts in (0, 5e-5) as `x.xxe-yy%`. Package sentences now read 2.64e-07 %, 8.52e-09 % and 3.37e-08 %, which equal 100 × the stored drifts. The load table in `results.js:14` also uses `toExponential(2)`.
9. **Clarifications** (`docs/technical/mvp-code-and-physics-guide.md`):
   - Screening reserve is a fraction of usable pack energy, distinct from the battery exercise's `(1 + reserve_fraction)` mission-energy convention.
   - Usable energy is accepted as declared, not derived from pack mass.
   - The example's a_z is an instantaneous force margin.
   - The 180 s duration checks constant-point energy only.
   These resolve the disclosure aspects of F6 and F8.
10. **Re-ran locally:** unit suite **290 passed**, 3 backend deselected; `reference_impl` **118 passed**; `ruff check .` passed; `node --check web/js/results.js` passed.
11. **Not performed by this reviewer:** backend/Docker re-runs, browser interaction, refusal-button and export-download behaviour in a browser, Linux CI. These rely on the project records in `docs/qa/mvp_gates.md` and `docs/qa/results_page_checklist.md`.

### 6.3 Finding status

| ID | Was | Now | Evidence |
|---|---|---|---|
| F1 | Medium | **Resolved** | Capped GCI 0.40844 % (cap 2, Fs 1.25) is primary in the UI, interpretation and chart error bar; observed-order 0.10989 % retained and qualified; independently recomputed |
| F2 | Medium | **Resolved (by allowed labelling alternative)** | Explicit "supplied data, not physically validated" text on the page and in every capacity result. A physics gate is still absent, so the residual risk is disclosed, not removed |
| F3 | Medium | **Resolved** | Both docs now describe the actual v2606 test, startup 10, trigger 412 and stop 812 |
| F9 | Low | **Resolved** | Scientific display of tiny drifts in the interpretation and load table |
| F6 | Low | **Partially resolved (disclosed)** | Instantaneous-a_z / constant-point-energy meaning documented; the example case itself is unchanged |
| F8 | Low | **Partially resolved (disclosed)** | Reserve conventions and the declared (not derived) usable energy documented; no consistency check added |
| F4, F5, F7, F10, F11 | Low | **Open** (unchanged) | Moment abs_tol not discriminating; power/energy infeasibility reported as `inputs_incomplete`; post-hoc slice tolerance; `numerical_checks_passed` vocabulary; z-only force balance (documented scope limit) |

**New, Low:**

| ID | Severity | Location | Finding | Recommendation |
|---|---|---|---|---|
| N1 | Low | `.backend/demo-final/results/acd1b8716144aeaa` vs `.backend/demo-reviewed/results/acd1b8716144aeaa` | Two packages with different contents (pre- and post-review) share the identifier `acd1b8716144aeaa`, because the ID is the run-group hash, not the package content hash. They live under separate data roots and both verify, but a presenter or export consumer could load or cite the superseded one, which shows only the 0.110 % GCI. | Demo only from `demo-reviewed`. Consider including a package-content hash or revision in the visible ID. |

### 6.4 Follow-up verdict

**PASS for the bounded MVP scope at `f19cbeb`.** The required conditions F1–F3 are cleared, and F9 is resolved.

The sphere pipeline is accepted as a software-verification demonstration. The screening panel is accepted as a labelled illustrative `screening_only` calculation, whose power and energy inputs are explicitly unchecked supplied data.

Remaining Low findings (F4, F5, F7, F10, F11, N1; F6/F8 partially) do not block a client presentation, provided the presenter:
- uses the `demo-reviewed` package, and
- keeps to the claim limits in §4 and `plan.md` §13.

All §4 unresolved limits still apply. In particular:
- the +2.6 % gap to Schiller–Naumann is unexplained and must not be attributed;
- asymptotic convergence is not demonstrated;
- evidence remains `unverified`.

This is not aircraft validation, rotor CFD evidence or human certification. Product sign-off, two full timed rehearsals and a playable backup recording remain pending and are outside this review.
